import argparse
import json
from pathlib import Path

from src.reasoning.constants import DEFAULT_COURSE_INPUT, DEFAULT_COURSE_OUTPUT
from src.reasoning.evaluator import evaluate_prereq
from src.reasoning.explainer import build_explanation
from src.reasoning.parser import PrerequisiteParser, attach_parsed_prereqs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 3 prerequisite reasoning engine")
    subparsers = parser.add_subparsers(dest="command", required=True)

    enrich = subparsers.add_parser("enrich", help="Attach parsed prerequisite logic to all courses")
    enrich.add_argument("--input", type=Path, default=DEFAULT_COURSE_INPUT)
    enrich.add_argument("--output", type=Path, default=DEFAULT_COURSE_OUTPUT)

    evaluate = subparsers.add_parser("evaluate", help="Evaluate one course against a student payload")
    evaluate.add_argument("--input", type=Path, default=DEFAULT_COURSE_OUTPUT)
    evaluate.add_argument("--course-id", required=True)
    evaluate.add_argument("--student-file", type=Path)
    evaluate.add_argument("--student-json")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "enrich":
        run_enrich(args.input, args.output)
        return

    if args.command == "evaluate":
        run_evaluate(args.input, args.course_id, args.student_file, args.student_json)
        return

    raise ValueError(f"Unknown command: {args.command}")


def run_enrich(input_path: Path, output_path: Path) -> None:
    courses = json.loads(input_path.read_text(encoding="utf-8"))
    parser = PrerequisiteParser()
    enriched = attach_parsed_prereqs(courses, parser)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(enriched, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Enriched {len(enriched)} courses")
    print(f"Saved to: {output_path}")


def run_evaluate(input_path: Path, course_id: str, student_file: Path | None, student_json: str | None) -> None:
    courses = json.loads(input_path.read_text(encoding="utf-8"))
    course = next((item for item in courses if item.get("course_id") == course_id.upper()), None)
    if course is None:
        raise ValueError(f"Course not found: {course_id}")

    student = _load_student_payload(student_file, student_json)
    evaluation = evaluate_prereq(course.get("parsed_prereq"), student)
    print(build_explanation(course, evaluation))


def _load_student_payload(student_file: Path | None, student_json: str | None) -> dict:
    if student_file is not None:
        return json.loads(student_file.read_text(encoding="utf-8"))
    if student_json is not None:
        return json.loads(student_json)
    raise ValueError("Provide either --student-file or --student-json")


if __name__ == "__main__":
    main()
