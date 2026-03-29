from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from src.graph.nodes.formatter import formatter_node
from src.graph.nodes.intake import intake_node
from src.graph.nodes.planner import planner_node
from src.graph.nodes.retriever import retriever_node
from src.graph.nodes.verifier import verifier_node
from src.graph.state import GraphState


def build_planning_graph():
    graph = StateGraph(GraphState)
    graph.add_node("intake", intake_node)
    graph.add_node("retriever", retriever_node)
    graph.add_node("planner", planner_node)
    graph.add_node("verifier", verifier_node)
    graph.add_node("formatter", formatter_node)

    graph.add_edge(START, "intake")
    graph.add_edge("intake", "retriever")
    graph.add_edge("retriever", "planner")
    graph.add_edge("planner", "verifier")
    graph.add_edge("verifier", "formatter")
    graph.add_edge("formatter", END)
    return graph.compile()
