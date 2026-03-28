import json
import os
import re
from copy import deepcopy
from pathlib import Path

from dotenv import load_dotenv

from src.reasoning.constants import PREREQ_PARSER_PROMPT_FILE, SUPPORTED_NODE_TYPES

try:
    from langchain_groq import ChatGroq
except Exception:
    ChatGroq = None


class PrerequisiteParser:
    def __init__(self, prompt_path: Path = PREREQ_PARSER_PROMPT_FILE) -> None:
        load_dotenv()
        self.prompt_text = prompt_path.read_text(encoding="utf-8").strip()
        self.api_key = os.getenv("GROQ_API_KEY")
        self.client = None
        self._cache: dict[str, dict | None] = {}

        if self.api_key and ChatGroq is not None:
            self.client = ChatGroq(
                api_key=self.api_key,
                model="llama-3.3-70b-versatile",
                temperature=0,
            )

    def parse(self, text: str | None) -> dict | None:
        return parse_prerequisite_text(text, self)


def parse_prerequisite_text(text: str | None, parser: PrerequisiteParser | None = None) -> dict | None:
    cleaned = preclean_prerequisite_text(text)
    if cleaned is None:
        return None

    if parser is None:
        parser = PrerequisiteParser()

    if cleaned in parser._cache:
        cached = parser._cache[cleaned]
        return deepcopy(cached) if cached is not None else None

    if parser.client is None:
        raise RuntimeError("GROQ_API_KEY is required for Phase 3 prerequisite parsing")

    prompt = parser.prompt_text.replace("{{PREREQUISITE_TEXT}}", cleaned)
    response = parser.client.invoke(prompt)
    content = response.content
    if isinstance(content, list):
        content = "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )

    parsed = json.loads(_extract_json_text(str(content)))
    validated = validate_parsed_prereq(parsed)
    parser._cache[cleaned] = deepcopy(validated)
    return validated


def attach_parsed_prereqs(courses: list[dict], parser: PrerequisiteParser | None = None) -> list[dict]:
    parser = parser or PrerequisiteParser()
    enriched_courses: list[dict] = []

    for course in courses:
        enriched = dict(course)
        prereq_text = course.get("prerequisites")
        if prereq_text is None:
            enriched["parsed_prereq"] = None
        else:
            try:
                enriched["parsed_prereq"] = parse_prerequisite_text(prereq_text, parser)
            except Exception:
                enriched["parsed_prereq"] = {
                    "type": "UNKNOWN",
                    "value": preclean_prerequisite_text(prereq_text),
                }
        enriched_courses.append(enriched)

    return enriched_courses


def validate_parsed_prereq(node: dict | None) -> dict | None:
    if node is None:
        return None
    if not isinstance(node, dict):
        raise ValueError("Parsed prerequisite must be a JSON object")

    node_type = str(node.get("type", "")).upper().strip()
    if node_type not in SUPPORTED_NODE_TYPES:
        raise ValueError(f"Unsupported node type: {node_type}")

    if node_type in {"AND", "OR"}:
        raw_conditions = node.get("conditions")
        if not isinstance(raw_conditions, list) or not raw_conditions:
            raise ValueError(f"{node_type} node must contain non-empty conditions")
        return {
            "type": node_type,
            "conditions": [validate_parsed_prereq(child) for child in raw_conditions],
        }

    if node_type == "COURSE":
        course_code = _normalize_course_code(node.get("course") or node.get("value"))
        if course_code is None:
            raise ValueError("COURSE node must include a course code")
        normalized = {"type": "COURSE", "course": course_code}
        min_grade = _normalize_grade(node.get("min_grade") or node.get("grade"))
        if min_grade is not None:
            normalized["min_grade"] = min_grade
        return normalized

    if node_type == "ASSESSMENT":
        assessment = _normalize_assessment_name(node.get("assessment") or node.get("value"))
        min_score = _normalize_min_score(node.get("min_score") or node.get("score"))
        if assessment is None or min_score is None:
            raise ValueError("ASSESSMENT node must include assessment and min_score")
        return {
            "type": "ASSESSMENT",
            "assessment": assessment,
            "min_score": min_score,
        }

    if node_type == "NON_ENFORCEABLE":
        reason = _normalize_text(node.get("reason") or node.get("value"))
        if reason is None:
            raise ValueError("NON_ENFORCEABLE node must include reason")
        return {"type": "NON_ENFORCEABLE", "reason": reason}

    if node_type in {"EXCEPTION", "UNKNOWN"}:
        value = _normalize_text(node.get("value"))
        if value is None:
            raise ValueError(f"{node_type} node must include value")
        if _looks_non_enforceable(value):
            return {
                "type": "NON_ENFORCEABLE",
                "reason": value,
            }
        return {"type": node_type, "value": value}

    raise ValueError(f"Unhandled node type: {node_type}")


def preclean_prerequisite_text(text: str | None) -> str | None:
    if text is None:
        return None

    cleaned = _normalize_text(text)
    if cleaned is None or cleaned.lower() in {"none", "null"}:
        return None

    cleaned = re.sub(r"\b([A-Za-z]{3,4})\s+(\d{3,4})\b", lambda m: f"{m.group(1).upper()}{m.group(2)}", cleaned)
    cleaned = re.sub(r"\s*\.\s*$", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\bOR above\b", "OR higher", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bwith a\b", "with grade", cleaned, flags=re.IGNORECASE)
    cleaned = _strip_single_course_title(cleaned)

    if _is_skill_only_text(cleaned):
        return None

    course_codes = re.findall(r"\b[A-Z]{3,4}\d{3,4}\b", cleaned)
    if len(course_codes) == 2 and " AND " not in cleaned and " OR " not in cleaned:
        if cleaned == f"{course_codes[0]} {course_codes[1]}":
            cleaned = f"{course_codes[0]} AND {course_codes[1]}"

    return cleaned


def _extract_json_text(text: str) -> str:
    fenced_match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced_match:
        return fenced_match.group(1)

    raw_match = re.search(r"(\{.*\})", text, re.DOTALL)
    if raw_match:
        return raw_match.group(1)

    raise ValueError("Parser response did not contain JSON")


def _normalize_course_code(value: str | None) -> str | None:
    if value is None:
        return None
    match = re.search(r"([A-Za-z]{3,4})\s*(\d{3,4})", str(value))
    if not match:
        return None
    return f"{match.group(1).upper()}{match.group(2)}"


def _normalize_grade(value: str | None) -> str | None:
    if value is None:
        return None
    match = re.search(r"([ABCDF][+-]?)", str(value).upper())
    return match.group(1) if match else None


def _normalize_assessment_name(value: str | None) -> str | None:
    text = _normalize_text(value)
    if text is None:
        return None
    normalized = text.upper().replace(" ", "_")
    return normalized


def _normalize_min_score(value: str | int | None) -> int | None:
    if value is None:
        return None
    match = re.search(r"\d+", str(value))
    return int(match.group(0)) if match else None


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", str(value)).strip()
    return cleaned or None


def _strip_single_course_title(text: str) -> str:
    course_codes = re.findall(r"\b[A-Z]{3,4}\d{3,4}\b", text)
    if len(course_codes) != 1:
        return text

    first_code = course_codes[0]
    if not text.startswith(first_code):
        return text

    trailing = text[len(first_code):].strip()
    if not trailing:
        return text

    blockers = (
        "grade",
        "permission",
        "knowledge",
        "score",
        "accuplacer",
        "working",
        "successful",
        "skill",
    )
    if any(token in trailing.lower() for token in blockers):
        return text

    return first_code


def _is_skill_only_text(text: str) -> bool:
    lowered = text.lower()
    return "(skill)" in lowered and "accuplacer" not in lowered and not re.search(r"\b[A-Z]{3,4}\d{3,4}\b", text)


def _looks_non_enforceable(text: str) -> bool:
    lowered = text.lower()
    markers = (
        "working knowledge",
        "equivalent experience",
        "informal skill",
        "skill requirement",
    )
    return any(marker in lowered for marker in markers)
