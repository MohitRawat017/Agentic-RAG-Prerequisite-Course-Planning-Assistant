import argparse
import json
from pathlib import Path

from src.graph.graph import build_planning_graph
from src.graph.state import GraphState
from src.planning.constants import DEFAULT_COURSE_FILE, DEFAULT_PLAN_OUTPUT_FILE, DEFAULT_POLICY_FILE, DEFAULT_PROGRAM_FILE


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 4 course planning engine")
    parser.add_argument("--courses", type=Path, default=DEFAULT_COURSE_FILE)
    parser.add_argument("--program", type=Path, default=DEFAULT_PROGRAM_FILE)
    parser.add_argument("--policies", type=Path, default=DEFAULT_POLICY_FILE)
    parser.add_argument("--request-file", type=Path)
    parser.add_argument("--request-json")
    parser.add_argument("--query")
    parser.add_argument("--output", type=Path, default=DEFAULT_PLAN_OUTPUT_FILE)
    parser.add_argument("--print-explanation", action="store_true")
    parser.add_argument("--rebuild-index", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    graph = build_planning_graph()
    result = graph.invoke(
        GraphState(
            query=args.query,
            request_file=args.request_file,
            request_json=args.request_json,
            courses_path=args.courses,
            program_path=args.program,
            policies_path=args.policies,
            output_path=args.output,
            rebuild_index=args.rebuild_index,
            print_explanation=args.print_explanation,
        )
    )
    plan = result["plan"]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved plan to: {args.output}")

    if args.print_explanation:
        print(result["response_text"])


if __name__ == "__main__":
    main()
