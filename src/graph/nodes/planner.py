from __future__ import annotations

from src.graph.state import GraphState
from src.planning.engine import build_course_plan


def planner_node(state: GraphState) -> GraphState:
    plan = build_course_plan(
        state["request"],
        state["courses"],
        state["program"],
        state["policies"],
    )
    return {
        **state,
        "plan": plan,
    }
