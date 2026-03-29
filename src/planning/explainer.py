import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

from src.planning.constants import EXPLANATION_PROMPT_FILE

try:
    from langchain_groq import ChatGroq
except Exception:
    ChatGroq = None


ABSTAIN_TEXT = "I don't have that information in the provided catalog or policies."


def build_plan_explanation(
    plan: dict,
    request: dict,
    courses_by_id: dict[str, dict],
    retrieved_chunks: list[dict],
) -> str:
    grounded = _build_grounded_response(plan, request, courses_by_id, retrieved_chunks)

    load_dotenv()
    use_llm = bool(os.getenv("PHASE5_USE_LLM_FORMATTER"))
    api_key = os.getenv("GROQ_API_KEY")
    if use_llm and api_key and ChatGroq is not None:
        prompt = Path(EXPLANATION_PROMPT_FILE).read_text(encoding="utf-8").strip()
        prompt = prompt.replace("{{GROUNDED_RESPONSE_JSON}}", json.dumps(grounded, indent=2))
        client = ChatGroq(
            api_key=api_key,
            model="llama-3.3-70b-versatile",
            temperature=0,
        )
        response = client.invoke(prompt)
        content = response.content
        if isinstance(content, list):
            content = "".join(
                item.get("text", "") if isinstance(item, dict) else str(item)
                for item in content
            )
        normalized = _normalize_explanation_sections(str(content).strip())
        if _looks_like_grounded_response(normalized):
            return normalized

    return _render_grounded_response(grounded)


def _build_grounded_response(
    plan: dict,
    request: dict,
    courses_by_id: dict[str, dict],
    retrieved_chunks: list[dict],
) -> dict:
    if request.get("greeting_query"):
        return {
            "answer": ["Hello! How can I help you with your course planning today?"],
            "why": ["This is a greeting and does not contain a course-related query."],
            "citations": ["None"],
            "clarifying_questions": list(plan.get("clarifying_questions", [])),
            "assumptions": list(plan.get("assumptions", [])),
        }
    if request.get("unsupported_query"):
        return _abstain_response(plan, request, retrieved_chunks)

    evidence_index = _index_evidence(retrieved_chunks)
    answer_lines, answer_citations = _build_answer_lines(plan, courses_by_id, evidence_index)
    why_lines, why_citations = _build_why_lines(plan, evidence_index, answer_citations)
    used_citations = _unique(answer_citations + why_citations)

    if not used_citations:
        return _abstain_response(plan, request, retrieved_chunks)

    return {
        "answer": answer_lines or [ABSTAIN_TEXT],
        "why": why_lines or [ABSTAIN_TEXT],
        "citations": [_format_citation(item) for item in used_citations],
        "clarifying_questions": list(plan.get("clarifying_questions", [])),
        "assumptions": list(plan.get("assumptions", [])),
    }


def _build_answer_lines(plan: dict, courses_by_id: dict[str, dict], evidence_index: dict) -> tuple[list[str], list[dict]]:
    recommended = plan.get("recommended_courses", [])
    direct = plan.get("direct_course_result")
    answer_citations: list[dict] = []

    if direct is not None:
        target_course = direct["course_id"]
        target_evidence = _find_course_evidence(target_course, evidence_index)
        if target_evidence is None:
            target_evidence = _first_available_evidence(evidence_index)

        if direct["decision"] == "Eligible":
            if target_evidence is not None:
                answer_citations.append(target_evidence)
            return [f"You can take {_course_label(target_course, courses_by_id)}."], answer_citations

        if direct["decision"] == "Needs Approval":
            if target_evidence is not None:
                answer_citations.append(target_evidence)
            return [f"You may be able to take {_course_label(target_course, courses_by_id)} with instructor approval."], answer_citations

        if recommended:
            fallback_evidence = _find_course_evidence(recommended[0], evidence_index)
            if fallback_evidence is None:
                fallback_evidence = _first_available_evidence(evidence_index)
            if target_evidence is not None:
                answer_citations.append(target_evidence)
            if fallback_evidence is not None and fallback_evidence is not target_evidence:
                answer_citations.append(fallback_evidence)
            return [
                f"You cannot take {_course_label(target_course, courses_by_id)} yet. "
                f"You should take {_course_label(recommended[0], courses_by_id)}."
            ], answer_citations

        if target_evidence is not None:
            answer_citations.append(target_evidence)
        return [f"You cannot take {_course_label(target_course, courses_by_id)} yet."], answer_citations

    if not recommended:
        return [ABSTAIN_TEXT], []

    answer_lines = []
    for course_id in recommended:
        evidence = _find_course_evidence(course_id, evidence_index)
        if evidence is None:
            evidence = _first_available_evidence(evidence_index)
        if evidence is not None:
            answer_citations.append(evidence)

    course_labels = [_course_label(course_id, courses_by_id) for course_id in recommended]
    if len(course_labels) == 1:
        answer_lines.append(f"You should take {course_labels[0]}.")
    else:
        answer_lines.append(f"You should take {', '.join(course_labels[:-1])}, and {course_labels[-1]}.")
    return answer_lines, answer_citations


def _build_why_lines(plan: dict, evidence_index: dict, answer_citations: list[dict]) -> tuple[list[str], list[dict]]:
    why_lines: list[str] = []
    citations: list[dict] = []

    for justification in plan.get("justification", []):
        support = _supporting_evidence_for_text(justification, evidence_index)
        if not support:
            support = _fallback_support_for_justification(justification, evidence_index, answer_citations)
        if not support:
            continue
        why_lines.append(justification)
        citations.extend(support)

    return why_lines, citations


def _abstain_response(plan: dict, request: dict, retrieved_chunks: list[dict]) -> dict:
    del request
    return {
        "answer": [ABSTAIN_TEXT],
        "why": [ABSTAIN_TEXT],
        "citations": _abstain_citations(retrieved_chunks),
        "clarifying_questions": list(plan.get("clarifying_questions", [])),
        "assumptions": list(plan.get("assumptions", [])),
    }


def _index_evidence(retrieved_chunks: list[dict]) -> dict:
    index = {
        "course": {},
        "program": [],
        "policy": [],
    }
    for item in retrieved_chunks:
        metadata = item.get("metadata", {})
        item_type = metadata.get("type")
        if item_type == "course" and metadata.get("course_id"):
            index["course"].setdefault(metadata["course_id"], []).append(item)
        elif item_type == "program":
            index["program"].append(item)
        elif item_type == "policy":
            index["policy"].append(item)
    return index


def _find_course_evidence(course_id: str, evidence_index: dict) -> dict | None:
    items = evidence_index["course"].get(course_id, [])
    return items[0] if items else None


def _first_available_evidence(evidence_index: dict) -> dict | None:
    if evidence_index["program"]:
        return evidence_index["program"][0]
    if evidence_index["policy"]:
        return evidence_index["policy"][0]
    for chunks in evidence_index["course"].values():
        if chunks:
            return chunks[0]
    return None


def _supporting_evidence_for_text(text: str, evidence_index: dict) -> list[dict]:
    course_ids = re.findall(r"\b[A-Z]{3,4}\d{3,4}\b", text)
    supporting: list[dict] = []

    for course_id in course_ids:
        item = _find_course_evidence(course_id, evidence_index)
        if item is None:
            continue
        supporting.append(item)

    lowered = text.lower()
    if any(marker in lowered for marker in ("core program requirement", "program elective", "general education")):
        if evidence_index["program"]:
            supporting.append(evidence_index["program"][0])

    if "policy" in lowered or "grade" in lowered:
        if evidence_index["policy"]:
            supporting.append(evidence_index["policy"][0])

    return _unique(supporting)


def _fallback_support_for_justification(text: str, evidence_index: dict, answer_citations: list[dict]) -> list[dict]:
    supporting = list(answer_citations)
    lowered = text.lower()

    if any(marker in lowered for marker in ("core program requirement", "program elective", "general education")):
        if evidence_index["program"]:
            supporting.append(evidence_index["program"][0])

    if "policy" in lowered or "grade" in lowered:
        if evidence_index["policy"]:
            supporting.append(evidence_index["policy"][0])

    return _unique(supporting)


def _course_label(course_id: str, courses_by_id: dict[str, dict]) -> str:
    course = courses_by_id.get(course_id, {})
    title = course.get("course_title")
    return f"{course_id} ({title})" if title else course_id


def _format_citation(item: dict) -> str:
    metadata = item.get("metadata", {})
    label = metadata.get("course_id") or metadata.get("program_id") or metadata.get("policy_id") or metadata.get("chunk_id")
    source_url = metadata.get("source_url") or "Unknown source"
    page_number = metadata.get("page_number")
    chunk_id = metadata.get("chunk_id")
    if page_number is not None:
        return f"{label}: {source_url} (page {page_number}; {chunk_id})"
    return f"{label}: {source_url} ({chunk_id})"


def _render_grounded_response(grounded: dict) -> str:
    lines = ["Answer / Plan:"]
    lines.extend(grounded["answer"] or ["None"])
    lines.extend(["", "Why (requirements/prereqs satisfied):"])
    lines.extend([f"- {item}" for item in grounded["why"]] if grounded["why"] != ["None"] else ["None"])
    lines.extend(["", "Citations:"])
    lines.extend([f"- {item}" for item in grounded["citations"]] if grounded["citations"] != ["None"] else ["None"])
    lines.extend(["", "Clarifying questions (if needed):"])
    lines.extend([f"- {item}" for item in grounded["clarifying_questions"]] if grounded["clarifying_questions"] else ["None"])
    lines.extend(["", "Assumptions / Not in catalog:"])
    lines.extend([f"- {item}" for item in grounded["assumptions"]] if grounded["assumptions"] else ["None"])
    return "\n".join(lines)


def _abstain_citations(retrieved_chunks: list[dict]) -> list[str]:
    if not retrieved_chunks:
        return ["None"]
    return [_format_citation(item) for item in _unique(retrieved_chunks)]


def _normalize_explanation_sections(text: str) -> str:
    headings = [
        "Answer / Plan:",
        "Why (requirements/prereqs satisfied):",
        "Citations:",
        "Clarifying questions (if needed):",
        "Assumptions / Not in catalog:",
    ]
    sections: dict[str, list[str]] = {heading: [] for heading in headings}
    current_heading: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        matched_heading = next((heading for heading in headings if line.strip() == heading), None)
        if matched_heading is not None:
            current_heading = matched_heading
            continue
        if line.strip().endswith(":"):
            current_heading = None
            continue
        if current_heading is not None:
            sections[current_heading].append(line)

    if not any(sections.values()):
        return text

    normalized_lines: list[str] = []
    for heading in headings:
        normalized_lines.append(heading)
        body = [line for line in sections[heading] if line.strip()]
        if body:
            normalized_lines.extend(body)
        else:
            normalized_lines.append("None")
        normalized_lines.append("")

    return "\n".join(normalized_lines).strip()


def _looks_like_grounded_response(text: str) -> bool:
    required = [
        "Answer / Plan:",
        "Why (requirements/prereqs satisfied):",
        "Citations:",
        "Clarifying questions (if needed):",
        "Assumptions / Not in catalog:",
    ]
    return all(token in text for token in required)


def _unique(values: list[dict]) -> list[dict]:
    result: list[dict] = []
    seen: set[str] = set()
    for value in values:
        metadata = value.get("metadata", {})
        key = metadata.get("chunk_id") or json.dumps(metadata, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
