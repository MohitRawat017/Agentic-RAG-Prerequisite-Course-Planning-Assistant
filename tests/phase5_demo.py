import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agents.retriever_agent import retrieve_plan_evidence
from src.planning.constants import DEFAULT_RAG_DEMO_OUTPUT_FILE
from src.planning.engine import build_course_plan
from src.planning.explainer import build_plan_explanation
from src.planning.intake import parse_planning_request
from src.planning.loader import load_planning_assets
from src.rag.retriever import build_chunk_documents, get_or_create_vectorstore, index_documents


def main() -> None:
    courses, program, policies = load_planning_assets()
    vectorstore = get_or_create_vectorstore()
    index_documents(vectorstore, build_chunk_documents(courses, program, policies))
    courses_by_id = {course["course_id"]: course for course in courses}

    queries = [
        "I have completed COMP1120 and COMP1130. I want to plan my next semester with a maximum of 8 credits.",
        "Can I take COMP2145?",
        "Can I take COMP2145 with instructor permission?",
        "I completed COMP1120, COMP1130, and COMP1140. Can I take COMP2145?",
        "When is COMP2145 offered?",
    ]

    outputs = []
    for query in queries:
        request = parse_planning_request(
            None,
            {
                "query": query,
                "completed_courses": _completed_courses_for_query(query),
                "grades": _grades_for_query(query),
                "max_credits": _max_credits_for_query(query),
            },
        )
        plan = build_course_plan(request, courses, program, policies)
        retrieved_chunks = retrieve_plan_evidence(request, plan, vectorstore)
        explanation = build_plan_explanation(plan, request, courses_by_id, retrieved_chunks)
        outputs.append(
            {
                "query": query,
                "recommended_courses": plan.get("recommended_courses", []),
                "citations": [item["metadata"].get("chunk_id") for item in retrieved_chunks],
                "explanation": explanation,
            }
        )
        print(f"\nQUERY: {query}\n")
        print(explanation)

    output_path = Path(DEFAULT_RAG_DEMO_OUTPUT_FILE)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(outputs, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved Phase 5 demo output to: {output_path}")


def _completed_courses_for_query(query: str) -> list[str]:
    lowered = query.lower()
    if "completed comp1120 and comp1130" in lowered:
        return ["COMP1120", "COMP1130"]
    if "completed comp1120, comp1130, and comp1140" in lowered:
        return ["COMP1120", "COMP1130", "COMP1140"]
    return []


def _grades_for_query(query: str) -> dict[str, str]:
    lowered = query.lower()
    if "completed comp1120, comp1130, and comp1140" in lowered:
        return {"COMP1130": "B", "COMP1140": "C"}
    if "completed comp1120 and comp1130" in lowered:
        return {"COMP1120": "B", "COMP1130": "A"}
    return {}


def _max_credits_for_query(query: str) -> int | None:
    if "maximum of 8 credits" in query.lower():
        return 8
    return None


if __name__ == "__main__":
    main()
