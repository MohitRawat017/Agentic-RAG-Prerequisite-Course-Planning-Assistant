from __future__ import annotations

from src.graph.state import GraphState
from src.planning.explainer import build_plan_explanation


def formatter_node(state: GraphState) -> GraphState:
    response_text = build_plan_explanation(
        state["plan"],
        state["request"],
        state["courses_by_id"],
        state.get("retrieved_chunks", []),
    )
    return {
        **state,
        "response_text": response_text,
    }
