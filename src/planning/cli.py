import argparse
import json
from pathlib import Path

from src.agents.retriever_agent import retrieve_plan_evidence
from src.planning.constants import DEFAULT_COURSE_FILE, DEFAULT_PLAN_OUTPUT_FILE, DEFAULT_POLICY_FILE, DEFAULT_PROGRAM_FILE
from src.planning.engine import build_course_plan
from src.planning.explainer import build_plan_explanation
from src.planning.intake import parse_planning_request
from src.planning.loader import load_planning_assets
from src.rag.retriever import build_chunk_documents, get_or_create_vectorstore, index_documents


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
    payload = _load_payload(args.request_file, args.request_json)
    request = parse_planning_request(args.query, payload)
    courses, program, policies = load_planning_assets(args.courses, args.program, args.policies)
    plan = build_course_plan(request, courses, program, policies)
    vectorstore = get_or_create_vectorstore(rebuild=args.rebuild_index)
    index_documents(vectorstore, build_chunk_documents(courses, program, policies), rebuild=args.rebuild_index)
    retrieved_chunks = retrieve_plan_evidence(request, plan, vectorstore)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved plan to: {args.output}")

    if args.print_explanation:
        courses_by_id = {course["course_id"]: course for course in courses}
        print(build_plan_explanation(plan, request, courses_by_id, retrieved_chunks))


def _load_payload(request_file: Path | None, request_json: str | None) -> dict | None:
    if request_file is not None:
        return json.loads(request_file.read_text(encoding="utf-8"))
    if request_json is not None:
        return json.loads(request_json)
    return None


if __name__ == "__main__":
    main()
