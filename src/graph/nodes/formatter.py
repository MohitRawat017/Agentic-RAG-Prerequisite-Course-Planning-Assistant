from __future__ import annotations

from src.graph.state import GraphState
from src.utils.constants import NONE_TEXT


def formatter_node(state: GraphState) -> GraphState:
    payload = state.get("verified_output") or _build_fallback_payload(state)
    citation_map = {item["chunk_id"]: item for item in state.get("retrieved_chunks", [])}

    lines = [
        "Answer / Plan:",
        payload.get("answer_plan", "").strip() or NONE_TEXT,
        "",
        "Why (requirements/prereqs satisfied):",
    ]
    lines.extend(_format_list(payload.get("why", [])))
    lines.extend(["", "Citations:"])
    lines.extend(_format_citations(payload.get("citations", []), citation_map))
    lines.extend(["", "Clarifying questions (if needed):"])
    lines.extend(_format_list(payload.get("clarifying_questions", [])))
    lines.extend(["", "Assumptions / Not in catalog:"])
    lines.extend(_format_list(payload.get("assumptions_not_in_catalog", [])))

    return {
        **state,
        "final_response": "\n".join(lines).strip(),
    }


def _build_fallback_payload(state: GraphState) -> dict[str, list[str] | str]:
    clarifying_questions = state.get("clarifying_questions", [])
    if clarifying_questions:
        answer_plan = "Need more info to answer this from the catalog."
    else:
        answer_plan = "I do not have that information in the provided catalog/policies."

    assumptions = []
    if state.get("critical_missing_fields"):
        assumptions.append(
            "The request is missing a required target course or program identifier."
        )

    return {
        "answer_plan": answer_plan,
        "why": [],
        "citations": [],
        "clarifying_questions": clarifying_questions,
        "assumptions_not_in_catalog": assumptions,
    }


def _format_list(items: list[str]) -> list[str]:
    values = [" ".join(str(item).split()) for item in items if " ".join(str(item).split())]
    if not values:
        return [NONE_TEXT]
    return [f"- {item}" for item in values]


def _format_citations(citation_ids: list[str], citation_map: dict[str, dict]) -> list[str]:
    if not citation_ids:
        return [NONE_TEXT]

    rendered: list[str] = []
    for chunk_id in citation_ids:
        chunk = citation_map.get(chunk_id)
        if chunk is None:
            continue
        metadata = chunk.get("metadata", {})
        title = metadata.get("title") or chunk_id
        source_url = metadata.get("source_url") or "No source URL"
        rendered.append(f"- {chunk_id} | {title} | {source_url}")
    return rendered or [NONE_TEXT]

