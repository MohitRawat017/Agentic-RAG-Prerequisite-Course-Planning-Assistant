from src.planning.engine import build_course_plan
from src.planning.intake import parse_planning_request


def test_parse_planning_request_normalizes_payload_and_target_course() -> None:
    request = parse_planning_request(
        None,
        {
            "student": {
                "completed_courses": ["comp 1120", "COMP1130"],
                "grades": {"COMP 1120": "B", "COMP1130": "A"},
            },
            "query": "Can I take COMP2145?",
            "max_credits": "8",
        },
    )

    assert request["completed_courses"] == ["COMP1120", "COMP1130"]
    assert request["grades"] == {"COMP1120": "B", "COMP1130": "A"}
    assert request["max_credits"] == 8
    assert request["target_program"] == "AAS_INFORMATION_SYSTEMS"
    assert request["target_course"] == "COMP2145"
    assert request["intent"] == "course_eligibility"


def test_build_course_plan_prioritizes_core_courses_under_credit_limit() -> None:
    request = {
        "intent": "course_planning",
        "target_course": None,
        "completed_courses": ["COMP1120", "COMP1130"],
        "grades": {"COMP1120": "B", "COMP1130": "A"},
        "assessments": {},
        "max_credits": 8,
        "target_program": "AAS_INFORMATION_SYSTEMS",
        "include_general_education": False,
        "query": "Help me plan my next semester",
    }

    plan = build_course_plan(request, _sample_courses(), _sample_program(), [])

    assert plan["mode"] == "full_plan"
    assert plan["recommended_courses"] == ["COMP1140", "COMP1200"]
    assert plan["total_credits"] == 7
    assert "COMP1360" in plan["alternative_courses"]


def test_build_course_plan_missing_max_credits_returns_best_next() -> None:
    request = {
        "intent": "course_planning",
        "target_course": None,
        "completed_courses": ["COMP1120", "COMP1130"],
        "grades": {"COMP1120": "B", "COMP1130": "A"},
        "assessments": {},
        "max_credits": None,
        "target_program": "AAS_INFORMATION_SYSTEMS",
        "include_general_education": False,
        "query": "Help me plan my next semester",
    }

    plan = build_course_plan(request, _sample_courses(), _sample_program(), [])

    assert plan["mode"] == "best_next"
    assert plan["recommended_courses"] == ["COMP1140"]
    assert plan["clarifying_questions"] == ["What is your maximum credit load for next semester?"]


def test_build_course_plan_no_history_returns_single_entry_level_course() -> None:
    request = {
        "intent": "course_planning",
        "target_course": None,
        "completed_courses": [],
        "grades": {},
        "assessments": {},
        "max_credits": 8,
        "target_program": "AAS_INFORMATION_SYSTEMS",
        "include_general_education": False,
        "query": "Plan my semester",
    }

    plan = build_course_plan(request, _sample_courses(), _sample_program(), [])

    assert plan["mode"] == "best_next"
    assert plan["recommended_courses"] == ["COMP1120"]


def test_direct_course_query_falls_back_to_best_foundational_course() -> None:
    request = {
        "intent": "course_eligibility",
        "target_course": "COMP2145",
        "completed_courses": ["COMP1120", "COMP1130"],
        "grades": {"COMP1120": "B", "COMP1130": "A"},
        "assessments": {},
        "max_credits": None,
        "target_program": "AAS_INFORMATION_SYSTEMS",
        "include_general_education": False,
        "query": "Can I take COMP2145?",
    }

    plan = build_course_plan(request, _sample_courses(), _sample_program(), [])

    assert plan["mode"] == "direct_course_check"
    assert plan["direct_course_result"]["course_id"] == "COMP2145"
    assert plan["direct_course_result"]["decision"] == "Not Eligible"
    assert plan["recommended_courses"] == ["COMP1140"]
    assert any(item.startswith("COMP1140:") for item in plan["citations"])


def test_direct_course_query_with_instructor_permission_surfaces_approval() -> None:
    request = {
        "intent": "course_eligibility",
        "target_course": "COMP2145",
        "completed_courses": [],
        "grades": {},
        "assessments": {},
        "max_credits": None,
        "target_program": "AAS_INFORMATION_SYSTEMS",
        "include_general_education": False,
        "query": "Can I take COMP2145 with instructor permission?",
    }

    plan = build_course_plan(request, _sample_courses(), _sample_program(), [])

    assert plan["mode"] == "direct_course_check"
    assert plan["recommended_courses"] == []
    assert plan["direct_course_result"]["decision"] == "Needs Approval"
    assert plan["clarifying_questions"] == ["Do you have instructor approval for COMP2145?"]


def test_missing_grade_returns_clarification_only() -> None:
    request = {
        "intent": "course_eligibility",
        "target_course": "COMP2145",
        "completed_courses": ["COMP1120", "COMP1130", "COMP1140"],
        "grades": {},
        "assessments": {},
        "max_credits": None,
        "target_program": "AAS_INFORMATION_SYSTEMS",
        "include_general_education": False,
        "query": "Can I take COMP2145?",
    }

    plan = build_course_plan(request, _sample_courses(), _sample_program(), [])

    assert plan["mode"] == "clarification_only"
    assert plan["recommended_courses"] == []
    assert "What grade did you receive in COMP1130 so we can check eligibility for COMP2145?" in plan["clarifying_questions"]
    assert "What grade did you receive in COMP1140 so we can check eligibility for COMP2145?" in plan["clarifying_questions"]


def test_unsupported_query_abstains() -> None:
    request = parse_planning_request("When is COMP2145 offered?", None)

    plan = build_course_plan(request, _sample_courses(), _sample_program(), [])

    assert plan["mode"] == "clarification_only"
    assert plan["recommended_courses"] == []
    assert plan["justification"] == ["I don't have that information in the provided catalog or policies."]


def test_greeting_query_does_not_trigger_planning() -> None:
    request = parse_planning_request("hii", None)

    plan = build_course_plan(request, _sample_courses(), _sample_program(), [])

    assert request["greeting_query"] is True
    assert plan["mode"] == "clarification_only"
    assert plan["recommended_courses"] == []
    assert plan["justification"] == ["This is a greeting and does not contain a course-related query."]
    assert plan["clarifying_questions"] == ["What would you like help with? (e.g., checking prerequisites, planning courses)"]


def test_non_enforceable_prereq_is_treated_as_non_blocking() -> None:
    request = {
        "intent": "course_planning",
        "target_course": None,
        "completed_courses": ["COMP1120", "COMP1130", "COMP1140", "COMP1200", "COMP1360"],
        "grades": {"COMP1120": "B", "COMP1130": "A", "COMP1140": "C", "COMP1200": "B", "COMP1360": "B"},
        "assessments": {},
        "max_credits": 8,
        "target_program": "AAS_INFORMATION_SYSTEMS",
        "include_general_education": False,
        "query": "Help me plan my next semester",
    }

    plan = build_course_plan(request, _sample_courses(), _sample_program(), [])

    assert "COMP2312" in plan["recommended_courses"]
    assert not any("COMP2312" in question for question in plan["clarifying_questions"])


def _sample_courses() -> list[dict]:
    return [
        {
            "course_id": "COMP1120",
            "course_title": "Foundations of Computing",
            "credits": "3",
            "source_url": "https://example.com/1120",
            "parsed_prereq": None,
        },
        {
            "course_id": "COMP1130",
            "course_title": "Programming Logic",
            "credits": "3",
            "source_url": "https://example.com/1130",
            "parsed_prereq": {
                "type": "COURSE",
                "course": "COMP1120",
            },
        },
        {
            "course_id": "COMP1140",
            "course_title": "Web for Business",
            "credits": "3",
            "source_url": "https://example.com/1140",
            "parsed_prereq": {
                "type": "COURSE",
                "course": "COMP1130",
            },
        },
        {
            "course_id": "COMP1200",
            "course_title": "Hardware and Software Essentials",
            "credits": "4",
            "source_url": "https://example.com/1200",
            "parsed_prereq": None,
        },
        {
            "course_id": "COMP1360",
            "course_title": "Networking Basics",
            "credits": "4",
            "source_url": "https://example.com/1360",
            "parsed_prereq": {
                "type": "COURSE",
                "course": "COMP1130",
            },
        },
        {
            "course_id": "COMP2145",
            "course_title": "Web Programming",
            "credits": "4",
            "source_url": "https://example.com/2145",
            "parsed_prereq": {
                "type": "OR",
                "conditions": [
                    {
                        "type": "AND",
                        "conditions": [
                            {"type": "COURSE", "course": "COMP1130", "min_grade": "C"},
                            {"type": "COURSE", "course": "COMP1140", "min_grade": "C"},
                        ],
                    },
                    {"type": "EXCEPTION", "value": "instructor permission"},
                ],
            },
        },
        {
            "course_id": "COMP2312",
            "course_title": "Programming in Java",
            "credits": "4",
            "source_url": "https://example.com/2312",
            "parsed_prereq": {
                "type": "NON_ENFORCEABLE",
                "reason": "a working knowledge of at least one programming language",
            },
        },
    ]


def _sample_program() -> dict:
    return {
        "program_id": "AAS_INFORMATION_SYSTEMS",
        "core_courses": ["COMP1120", "COMP1130", "COMP1140", "COMP1200", "COMP1360"],
        "electives": ["COMP2145", "COMP2312", "COMP2150", "COMP2300"],
        "general_education": [],
        "source_url": "https://example.com/program",
    }
