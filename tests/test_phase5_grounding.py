import os

from src.planning.explainer import build_plan_explanation
from src.rag.retriever import build_chunk_documents


os.environ.pop("PHASE5_USE_LLM_FORMATTER", None)


def test_build_chunk_documents_includes_course_program_and_policy_metadata() -> None:
    documents = build_chunk_documents(_sample_courses(), _sample_program(), _sample_policies())

    chunk_ids = {document.metadata["chunk_id"] for document in documents}
    assert any(chunk_id.startswith("course_COMP1140") for chunk_id in chunk_ids)
    assert any(chunk_id.startswith("program_AAS_INFORMATION_SYSTEMS") for chunk_id in chunk_ids)
    assert any(chunk_id.startswith("policy_GRADING_POLICY") for chunk_id in chunk_ids)


def test_build_plan_explanation_uses_grounded_citations() -> None:
    plan = {
        "mode": "full_plan",
        "recommended_courses": ["COMP1140"],
        "total_credits": 3,
        "direct_course_result": None,
        "justification": ["COMP1140 (Web for Business) is a core program requirement and is eligible."],
        "risks": [],
        "clarifying_questions": [],
        "assumptions": [],
        "alternative_courses": [],
    }
    request = {
        "query": "Plan my next semester",
        "target_program": "AAS_INFORMATION_SYSTEMS",
    }

    explanation = build_plan_explanation(plan, request, _courses_by_id(), _grounded_chunks())

    assert "Answer / Plan:" in explanation
    assert "Why (requirements/prereqs satisfied):" in explanation
    assert "Citations:" in explanation
    assert "COMP1140: https://example.com/1140 (course_COMP1140_1)" in explanation
    assert "AAS_INFORMATION_SYSTEMS: https://example.com/program (program_AAS_INFORMATION_SYSTEMS_1)" in explanation


def test_build_plan_explanation_abstains_without_evidence() -> None:
    plan = {
        "mode": "full_plan",
        "recommended_courses": ["COMP1140"],
        "total_credits": 3,
        "direct_course_result": None,
        "justification": ["COMP1140 (Web for Business) is a core program requirement and is eligible."],
        "risks": [],
        "clarifying_questions": [],
        "assumptions": [],
        "alternative_courses": [],
    }
    request = {
        "query": "Plan my next semester",
        "target_program": "AAS_INFORMATION_SYSTEMS",
    }

    explanation = build_plan_explanation(plan, request, _courses_by_id(), [])

    assert "I don't have that information in the provided catalog or policies." in explanation


def _sample_courses() -> list[dict]:
    return [
        {
            "course_id": "COMP1140",
            "course_title": "Web for Business",
            "description": "Covers web tools for business.",
            "prerequisites": "COMP1130",
            "corequisites": None,
            "credits": "3",
            "notes": None,
            "source_url": "https://example.com/1140",
        },
    ]


def _sample_program() -> dict:
    return {
        "program_id": "AAS_INFORMATION_SYSTEMS",
        "program_name": "Information Systems AAS",
        "total_credits_required": 60,
        "core_courses": ["COMP1140"],
        "electives": [],
        "general_education": [],
        "capstone": "COMP2496",
        "rules": ["Students must complete core courses"],
        "source_url": "https://example.com/program",
    }


def _sample_policies() -> list[dict]:
    return [
        {
            "policy_id": "GRADING_POLICY",
            "policy_name": "Grading Policy",
            "rules": ["Minimum grade of C or better is required for prerequisite courses"],
            "source_url": "https://example.com/policy",
        },
    ]


def _courses_by_id() -> dict[str, dict]:
    courses = _sample_courses()
    return {course["course_id"]: course for course in courses}


def _grounded_chunks() -> list[dict]:
    return [
        {
            "text": "Course COMP1140: Web for Business. Prerequisites: COMP1130.",
            "metadata": {
                "type": "course",
                "course_id": "COMP1140",
                "chunk_id": "course_COMP1140_1",
                "source_url": "https://example.com/1140",
                "page_number": None,
            },
        },
        {
            "text": "Program AAS_INFORMATION_SYSTEMS. Core courses: COMP1140.",
            "metadata": {
                "type": "program",
                "program_id": "AAS_INFORMATION_SYSTEMS",
                "chunk_id": "program_AAS_INFORMATION_SYSTEMS_1",
                "source_url": "https://example.com/program",
                "page_number": None,
            },
        },
    ]
