from __future__ import annotations

from src.agents.retriever_agent import retrieve_plan_evidence
from src.graph.state import GraphState


def verifier_node(state: GraphState) -> GraphState:
    plan_evidence = retrieve_plan_evidence(state["request"], state["plan"], state["vectorstore"])
    merged_chunks = _merge_chunks(state.get("retrieved_chunks", []), plan_evidence)
    verification = {
        "has_retrieved_chunks": bool(merged_chunks),
        "recommended_course_ids": list(state["plan"].get("recommended_courses", [])),
        "direct_course_id": (state["plan"].get("direct_course_result") or {}).get("course_id"),
        "chunk_count": len(merged_chunks),
    }
    return {
        **state,
        "retrieved_chunks": merged_chunks,
        "verification": verification,
    }


def _merge_chunks(existing: list[dict], additional: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen_chunk_ids: set[str] = set()
    for item in existing + additional:
        chunk_id = item.get("metadata", {}).get("chunk_id")
        key = chunk_id or str(item.get("metadata", {}))
        if key in seen_chunk_ids:
            continue
        seen_chunk_ids.add(key)
        merged.append(item)
    return merged
