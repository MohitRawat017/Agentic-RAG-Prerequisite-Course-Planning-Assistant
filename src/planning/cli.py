from __future__ import annotations

import argparse

from src.graph.graph import build_graph
from src.graph.state import build_initial_state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pure RAG + LangGraph course planning CLI")
    parser.add_argument("--query", required=True, help="User query for the course planning assistant")
    parser.add_argument(
        "--rebuild-index",
        action="store_true",
        help="Rebuild the Chroma index before retrieval",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    graph = build_graph()
    result = graph.invoke(build_initial_state(query=args.query, rebuild_index=args.rebuild_index))
    print(result["final_response"])


if __name__ == "__main__":
    main()

