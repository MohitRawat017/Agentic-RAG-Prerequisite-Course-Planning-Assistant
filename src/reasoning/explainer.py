def build_explanation(course: dict, evaluation: dict) -> str:
    citations = course.get("source_url") or "Not available"
    clarifying_questions = _build_clarifying_questions(evaluation)
    assumptions = _build_assumptions(evaluation)

    lines = [
        "Answer / Plan:",
        evaluation["decision"],
        "",
        "Why:",
    ]

    for reason in evaluation.get("reason", []):
        lines.append(f"- {reason}")

    lines.extend(
        [
            "",
            "Citations:",
            f"- {citations}",
            "",
            "Clarifying questions:",
        ]
    )

    if clarifying_questions:
        for item in clarifying_questions:
            lines.append(f"- {item}")
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "Assumptions / Not in catalog:",
        ]
    )

    if assumptions:
        for item in assumptions:
            lines.append(f"- {item}")
    else:
        lines.append("- None")

    return "\n".join(lines)


def _build_clarifying_questions(evaluation: dict) -> list[str]:
    questions: list[str] = []
    for item in evaluation.get("missing", []):
        if item.startswith("grade for "):
            course_code = item.replace("grade for ", "", 1)
            questions.append(f"What grade did the student earn in {course_code}?")
        elif item.endswith(" score"):
            assessment = item.replace(" score", "", 1)
            questions.append(f"What is the student's {assessment} score?")
    return questions


def _build_assumptions(evaluation: dict) -> list[str]:
    assumptions: list[str] = []
    if evaluation.get("manual_review"):
        assumptions.append("One or more prerequisite clauses require manual review.")
    return assumptions
