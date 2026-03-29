from src.reasoning.constants import GRADE_ORDER


def evaluate_prereq(node: dict | None, student: dict) -> dict:
    if node is None:
        return {
            "decision": "Eligible",
            "missing": [],
            "manual_review": False,
            "reason": ["No prerequisites listed"],
        }

    result = _evaluate_node(node, student)
    decision = _decision_from_result(result)
    return {
        "decision": decision,
        "missing": result["missing"],
        "manual_review": result["manual_review"],
        "reason": result["reason"],
    }


def _evaluate_node(node: dict, student: dict) -> dict:
    node_type = node["type"]

    if node_type == "AND":
        child_results = [_evaluate_node(child, student) for child in node["conditions"]]
        missing = _merge_lists(*(child["missing"] for child in child_results))
        reasons = _merge_lists(*(child["reason"] for child in child_results))
        manual_review = any(child["manual_review"] for child in child_results)
        needs_more_info = any(child["needs_more_info"] for child in child_results)
        passed = all(child["passed"] for child in child_results) and not manual_review and not needs_more_info
        return {
            "passed": passed,
            "missing": missing,
            "reason": reasons,
            "manual_review": manual_review,
            "needs_more_info": needs_more_info,
        }

    if node_type == "OR":
        child_results = [_evaluate_node(child, student) for child in node["conditions"]]
        passing_child = next((child for child in child_results if child["passed"]), None)
        if passing_child is not None:
            return passing_child

        missing = _merge_lists(*(child["missing"] for child in child_results))
        reasons = _merge_lists(*(child["reason"] for child in child_results))
        manual_review = any(child["manual_review"] for child in child_results)
        needs_more_info = any(child["needs_more_info"] for child in child_results)
        return {
            "passed": False,
            "missing": missing,
            "reason": reasons,
            "manual_review": manual_review,
            "needs_more_info": needs_more_info,
        }

    if node_type == "COURSE":
        return _evaluate_course_node(node, student)

    if node_type == "ASSESSMENT":
        return _evaluate_assessment_node(node, student)

    if node_type == "NON_ENFORCEABLE":
        label = node.get("reason") or node.get("value") or "non-enforceable prerequisite"
        return {
            "passed": True,
            "missing": [],
            "reason": [f"Informal prerequisite noted but not enforced: {label}"],
            "manual_review": False,
            "needs_more_info": False,
        }

    if node_type in {"EXCEPTION", "UNKNOWN"}:
        label = node.get("value") or node.get("reason")
        return {
            "passed": False,
            "missing": [label],
            "reason": [f"Manual review required for {label}"],
            "manual_review": True,
            "needs_more_info": True,
        }

    raise ValueError(f"Unsupported node type during evaluation: {node_type}")


def _evaluate_course_node(node: dict, student: dict) -> dict:
    course_code = node["course"]
    completed_courses = set(student.get("completed_courses", []))
    grades = student.get("grades", {})

    if course_code not in completed_courses:
        return {
            "passed": False,
            "missing": [course_code],
            "reason": [f"{course_code} not completed"],
            "manual_review": False,
            "needs_more_info": False,
        }

    min_grade = node.get("min_grade")
    if min_grade is None:
        return {
            "passed": True,
            "missing": [],
            "reason": [f"{course_code} satisfied"],
            "manual_review": False,
            "needs_more_info": False,
        }

    grade_value = grades.get(course_code)
    if grade_value is None:
        return {
            "passed": False,
            "missing": [f"grade for {course_code}"],
            "reason": [f"Missing grade for {course_code}"],
            "manual_review": False,
            "needs_more_info": True,
        }

    if _grade_meets_minimum(grade_value, min_grade):
        return {
            "passed": True,
            "missing": [],
            "reason": [f"{course_code} satisfied with grade {grade_value}"],
            "manual_review": False,
            "needs_more_info": False,
        }

    return {
        "passed": False,
        "missing": [f"{course_code} with grade {min_grade} or better"],
        "reason": [f"{course_code} grade {grade_value} does not meet minimum {min_grade}"],
        "manual_review": False,
        "needs_more_info": False,
    }


def _evaluate_assessment_node(node: dict, student: dict) -> dict:
    assessment = node["assessment"]
    min_score = node["min_score"]
    assessments = student.get("assessments", {})
    current_score = assessments.get(assessment)

    if current_score is None:
        return {
            "passed": False,
            "missing": [f"{assessment} score"],
            "reason": [f"Missing {assessment} score"],
            "manual_review": False,
            "needs_more_info": True,
        }

    if int(current_score) >= int(min_score):
        return {
            "passed": True,
            "missing": [],
            "reason": [f"{assessment} satisfied with score {current_score}"],
            "manual_review": False,
            "needs_more_info": False,
        }

    return {
        "passed": False,
        "missing": [f"{assessment} >= {min_score}"],
        "reason": [f"{assessment} score {current_score} is below required {min_score}"],
        "manual_review": False,
        "needs_more_info": False,
    }


def _grade_meets_minimum(actual: str, required: str) -> bool:
    actual_score = GRADE_ORDER.get(str(actual).upper())
    required_score = GRADE_ORDER.get(str(required).upper())
    if actual_score is None or required_score is None:
        return False
    return actual_score >= required_score


def _decision_from_result(result: dict) -> str:
    if result["passed"]:
        return "Eligible"
    if result["manual_review"] or result["needs_more_info"]:
        return "Need more info"
    return "Not Eligible"


def _merge_lists(*values: list[str]) -> list[str]:
    merged: list[str] = []
    for items in values:
        for item in items:
            if item not in merged:
                merged.append(item)
    return merged
