from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.graph.graph import build_graph
from src.graph.state import build_initial_state


DEFAULT_TESTS_PATH = PROJECT_ROOT / "tests" / "testing.md"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "test_run_outputs.md"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the markdown-based evaluation suite.")
    parser.add_argument(
        "--tests-path",
        type=Path,
        default=DEFAULT_TESTS_PATH,
        help="Path to the markdown file containing the test questions.",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Path to the markdown file where outputs should be written.",
    )
    parser.add_argument(
        "--rebuild-index",
        action="store_true",
        help="Rebuild the Chroma index before the first test run.",
    )
    return parser


def parse_questions(markdown_path: Path) -> list[str]:
    lines = markdown_path.read_text(encoding="utf-8").splitlines()
    questions: list[str] = []

    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line.startswith("## Test"):
            index += 1
            continue

        index += 1
        while index < len(lines):
            candidate = lines[index].strip()
            if not candidate or candidate == "---":
                index += 1
                continue
            questions.append(candidate)
            break
        index += 1

    return questions


def run_questions(questions: list[str], rebuild_index: bool) -> list[dict[str, str]]:
    graph = build_graph()
    results: list[dict[str, str]] = []

    for position, question in enumerate(questions):
        state = build_initial_state(query=question, rebuild_index=rebuild_index and position == 0)
        response = graph.invoke(state)["final_response"]
        results.append(
            {
                "question": question,
                "response": response,
            }
        )

    return results


def write_markdown(output_path: Path, results: list[dict[str, str]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Test Run Outputs",
        "",
        f"Total tests run: {len(results)}",
        "",
    ]

    for index, result in enumerate(results, start=1):
        payload = json.dumps(result, indent=2, ensure_ascii=False)
        lines.extend(
            [
                f"## Test {index}",
                "",
                "```json",
                payload,
                "```",
                "",
            ]
        )

    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    args = build_parser().parse_args()
    questions = parse_questions(args.tests_path)
    if not questions:
        raise ValueError(f"No test questions were found in {args.tests_path}")

    results = run_questions(questions, rebuild_index=args.rebuild_index)
    write_markdown(args.output_path, results)
    print(f"Wrote {len(results)} test outputs to {args.output_path}")


if __name__ == "__main__":
    main()
