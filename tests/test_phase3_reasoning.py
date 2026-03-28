from src.reasoning.evaluator import evaluate_prereq
from src.reasoning.parser import preclean_prerequisite_text, validate_parsed_prereq


def test_preclean_compacts_course_codes() -> None:
    assert preclean_prerequisite_text("READ 0080 and READ 0090") == "READ0080 and READ0090"


def test_validate_prereq_tree_normalizes_grade_course_and_assessment() -> None:
    parsed = validate_parsed_prereq(
        {
            "type": "OR",
            "conditions": [
                {
                    "type": "AND",
                    "conditions": [
                        {"type": "course", "course": "comp 1140", "min_grade": "c or better"},
                        {"type": "course", "course": "COMP1130", "grade": "C"},
                    ],
                },
                {"type": "assessment", "assessment": "accuplacer_reading", "score": "78"},
            ],
        }
    )

    assert parsed == {
        "type": "OR",
        "conditions": [
            {
                "type": "AND",
                "conditions": [
                    {"type": "COURSE", "course": "COMP1140", "min_grade": "C"},
                    {"type": "COURSE", "course": "COMP1130", "min_grade": "C"},
                ],
            },
            {"type": "ASSESSMENT", "assessment": "ACCUPLACER_READING", "min_score": 78},
        ],
    }


def test_evaluate_prereq_handles_and_grade_logic() -> None:
    node = {
        "type": "OR",
        "conditions": [
            {
                "type": "AND",
                "conditions": [
                    {"type": "COURSE", "course": "COMP1140", "min_grade": "C"},
                    {"type": "COURSE", "course": "COMP1130", "min_grade": "C"},
                ],
            },
            {"type": "EXCEPTION", "value": "instructor permission"},
        ],
    }

    student = {
        "completed_courses": ["COMP1130", "COMP1140"],
        "grades": {"COMP1130": "B", "COMP1140": "C"},
        "exceptions": [],
    }

    result = evaluate_prereq(node, student)
    assert result["decision"] == "Eligible"
    assert result["manual_review"] is False


def test_evaluate_prereq_requests_missing_grade() -> None:
    node = {"type": "COURSE", "course": "READ0090", "min_grade": "C"}
    student = {"completed_courses": ["READ0090"], "grades": {}}

    result = evaluate_prereq(node, student)
    assert result["decision"] == "Need more info"
    assert "grade for READ0090" in result["missing"]


def test_skill_only_text_becomes_none() -> None:
    text = "(Skill) - Basic Windows navigation; Click, Double-click, etc."
    assert preclean_prerequisite_text(text) is None


def test_unknown_working_knowledge_becomes_non_enforceable() -> None:
    parsed = validate_parsed_prereq(
        {
            "type": "UNKNOWN",
            "value": "a working knowledge of at least one programming language",
        }
    )

    assert parsed == {
        "type": "NON_ENFORCEABLE",
        "reason": "a working knowledge of at least one programming language",
    }
