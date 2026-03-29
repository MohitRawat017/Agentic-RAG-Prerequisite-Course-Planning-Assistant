from src.reasoning.evaluator import evaluate_prereq


CREDIT_LIMIT_QUESTION = "What is your maximum credit load for next semester?"


def build_course_plan(request: dict, courses: list[dict], program: dict, policies: list[dict]) -> dict:
    del policies

    target_program = request["target_program"] or program.get("program_id")
    target_course = request.get("target_course")
    completed = set(request.get("completed_courses", []))
    max_credits = request.get("max_credits")
    include_gen_ed = request.get("include_general_education", False)
    query_text = (request.get("query") or "").lower()

    plan = _empty_plan(target_program)
    if request.get("unsupported_query"):
        plan["justification"] = ["I don't have that information in the provided catalog or policies."]
        return plan

    courses_by_id = {course["course_id"]: course for course in courses}
    program_groups = _build_program_groups(program, include_gen_ed)
    program_order = _build_program_order(program, include_gen_ed)
    relevant_course_ids = set(program_groups["core"]) | set(program_groups["electives"]) | set(program_groups["general_education"])
    missing_program_courses = sorted(code for code in program_groups["all_program_courses"] if code not in courses_by_id)
    for course_code in missing_program_courses:
        plan["assumptions"].append(f"{course_code} is referenced in the program JSON but missing from the course catalog dataset.")

    reverse_dependencies = _build_reverse_dependency_graph(courses)
    eligible_rows: list[dict] = []
    blocked_rows: list[dict] = []
    ineligible_rows: list[dict] = []
    rows_by_id: dict[str, dict] = {}

    for course in courses:
        course_id = course["course_id"]
        if course_id in completed:
            continue
        if relevant_course_ids and course_id not in relevant_course_ids and course_id != target_course:
            continue

        evaluation = _evaluate_for_planning(course.get("parsed_prereq"), request)
        plan["course_evaluations"][course_id] = evaluation
        row = {
            "course": course,
            "evaluation": evaluation,
            "priority_group": _priority_group(course_id, program_groups),
            "program_rank": program_order.get(course_id, 999),
            "unlock_count": len(reverse_dependencies.get(course_id, set())),
            "credits": _credits_as_int(course.get("credits")),
            "score": _score_course(course_id, program_groups, reverse_dependencies),
            "has_exception": _has_approval_path(course.get("parsed_prereq")),
        }
        rows_by_id[course_id] = row

        if row["credits"] <= 0:
            plan["assumptions"].append(f"{course_id} is missing a usable credit value and was excluded from automatic planning.")
            continue

        if evaluation["decision"] == "Eligible":
            eligible_rows.append(row)
        elif evaluation["decision"] == "Need more info":
            blocked_rows.append(row)
        else:
            ineligible_rows.append(row)

    eligible_rows.sort(key=_row_sort_key)
    blocked_rows.sort(key=_row_sort_key)
    ineligible_rows.sort(key=_row_sort_key)

    if target_course is not None:
        return _build_direct_course_plan(
            plan,
            request,
            rows_by_id,
            eligible_rows,
            blocked_rows,
            program,
            program_groups,
            query_text,
        )

    if not completed:
        best_row = _pick_entry_level_row(eligible_rows)
        if best_row is not None:
            return _build_best_next_plan(
                plan,
                best_row,
                program,
                program_groups,
                include_credit_question=max_credits is None,
            )
        if max_credits is None:
            plan["clarifying_questions"].append(CREDIT_LIMIT_QUESTION)
        return _finalize_empty_plan(plan, blocked_rows)

    if max_credits is None:
        best_row = _pick_best_row(eligible_rows)
        if best_row is not None:
            return _build_best_next_plan(
                plan,
                best_row,
                program,
                program_groups,
                include_credit_question=max_credits is None,
            )
        if max_credits is None:
            plan["clarifying_questions"].append(CREDIT_LIMIT_QUESTION)
        return _finalize_empty_plan(plan, blocked_rows)

    return _build_full_plan(plan, eligible_rows, blocked_rows, program, program_groups, max_credits)


def _empty_plan(target_program: str | None) -> dict:
    return {
        "mode": "clarification_only",
        "recommended_courses": [],
        "total_credits": 0,
        "direct_course_result": None,
        "justification": [],
        "risks": [],
        "clarifying_questions": [],
        "assumptions": [],
        "alternative_courses": [],
        "target_program": target_program,
        "course_evaluations": {},
        "citations": [],
    }


def _build_direct_course_plan(
    plan: dict,
    request: dict,
    rows_by_id: dict[str, dict],
    eligible_rows: list[dict],
    blocked_rows: list[dict],
    program: dict,
    program_groups: dict,
    query_text: str,
) -> dict:
    target_course = request["target_course"]
    row = rows_by_id.get(target_course)
    if row is None:
        plan["assumptions"].append(f"{target_course} was requested but is not present in the course catalog dataset.")
        return _finalize_empty_plan(plan, blocked_rows)

    evaluation = row["evaluation"]
    plan["direct_course_result"] = {
        "course_id": target_course,
        "decision": evaluation["decision"],
        "missing": evaluation.get("missing", []),
        "reason": evaluation.get("reason", []),
    }

    if evaluation["decision"] == "Eligible":
        plan["mode"] = "direct_course_check"
        plan["recommended_courses"] = [target_course]
        plan["total_credits"] = row["credits"]
        plan["justification"] = _build_justification([row], program_groups, direct_target=target_course)
        plan["risks"] = _build_risks([row], row["credits"], request.get("max_credits"))
        plan["citations"] = _build_citations([row], program, include_program=False)
        return plan

    if row["has_exception"] and "instructor permission" in query_text:
        plan["mode"] = "direct_course_check"
        plan["direct_course_result"]["decision"] = "Needs Approval"
        plan["clarifying_questions"].append(f"Do you have instructor approval for {target_course}?")
        plan["justification"] = [f"{target_course} may be taken with instructor permission if approval is granted."]
        plan["citations"] = _build_citations([row], program, include_program=False)
        return plan

    if _has_missing_grade(evaluation):
        plan["mode"] = "clarification_only"
        plan["clarifying_questions"] = _clarifying_questions_for_course(row["course"], evaluation)
        if row["has_exception"]:
            plan["justification"] = [
                f"{target_course} is not confirmed yet because prerequisite grades are missing.",
                f"{target_course} may also be possible with instructor permission.",
            ]
        return plan

    missing_prereq = _pick_missing_prerequisite(row, rows_by_id, eligible_rows)
    if missing_prereq is not None:
        plan["mode"] = "direct_course_check"
        plan["direct_course_result"]["decision"] = "Not Eligible"
        plan["recommended_courses"] = [missing_prereq["course"]["course_id"]]
        plan["total_credits"] = missing_prereq["credits"]
        plan["justification"] = [
            f"{target_course} is not currently eligible.",
            *_build_justification([missing_prereq], program_groups),
        ]
        if row["has_exception"]:
            plan["justification"].append(f"{target_course} may also be possible with instructor permission.")
        plan["risks"] = _build_risks([missing_prereq], missing_prereq["credits"], request.get("max_credits"))
        plan["citations"] = _build_citations([missing_prereq, row], program, include_program=True)
        plan["alternative_courses"] = _build_alternatives(eligible_rows, excluded={missing_prereq["course"]["course_id"], target_course})
        return plan

    fallback_candidates = [item for item in eligible_rows if item["course"]["course_id"] != target_course]
    if request.get("completed_courses"):
        fallback_row = _pick_best_row(fallback_candidates)
    else:
        fallback_row = _pick_entry_level_row(fallback_candidates)
    if fallback_row is not None:
        plan["mode"] = "direct_course_check"
        plan["direct_course_result"]["decision"] = "Not Eligible"
        plan["recommended_courses"] = [fallback_row["course"]["course_id"]]
        plan["total_credits"] = fallback_row["credits"]
        plan["justification"] = [
            f"{target_course} is not currently eligible.",
            *_build_justification([fallback_row], program_groups),
        ]
        if row["has_exception"]:
            plan["justification"].append(f"{target_course} may also be possible with instructor permission.")
        plan["risks"] = _build_risks([fallback_row], fallback_row["credits"], request.get("max_credits"))
        plan["citations"] = _build_citations([fallback_row, row], program, include_program=True)
        plan["alternative_courses"] = _build_alternatives(eligible_rows, excluded={fallback_row["course"]["course_id"], target_course})
        return plan

    return _finalize_empty_plan(plan, blocked_rows, direct_row=row)


def _build_best_next_plan(
    plan: dict,
    best_row: dict,
    program: dict,
    program_groups: dict,
    include_credit_question: bool,
) -> dict:
    plan["mode"] = "best_next"
    plan["recommended_courses"] = [best_row["course"]["course_id"]]
    plan["total_credits"] = best_row["credits"]
    plan["justification"] = _build_justification([best_row], program_groups)
    plan["risks"] = _build_risks([best_row], best_row["credits"], None)
    if include_credit_question:
        plan["clarifying_questions"].append(CREDIT_LIMIT_QUESTION)
    plan["citations"] = _build_citations([best_row], program, include_program=True)
    return plan


def _build_full_plan(
    plan: dict,
    eligible_rows: list[dict],
    blocked_rows: list[dict],
    program: dict,
    program_groups: dict,
    max_credits: int,
) -> dict:
    total_credits = 0
    selected_rows: list[dict] = []
    remaining_rows: list[dict] = []

    for row in eligible_rows:
        credits = row["credits"]
        if total_credits + credits <= max_credits:
            selected_rows.append(row)
            total_credits += credits
        else:
            remaining_rows.append(row)

    if not selected_rows:
        return _finalize_empty_plan(plan, blocked_rows)

    plan["mode"] = "full_plan"
    plan["recommended_courses"] = [row["course"]["course_id"] for row in selected_rows]
    plan["total_credits"] = total_credits
    plan["justification"] = _build_justification(selected_rows, program_groups)
    plan["risks"] = _build_risks(selected_rows, total_credits, max_credits)
    plan["clarifying_questions"] = _select_clarifying_questions(blocked_rows, max_credits, total_credits)
    plan["alternative_courses"] = _build_alternatives(remaining_rows, excluded=set())
    plan["citations"] = _build_citations(selected_rows, program, include_program=True)
    return plan


def _finalize_empty_plan(plan: dict, blocked_rows: list[dict], direct_row: dict | None = None) -> dict:
    plan["mode"] = "clarification_only"
    plan["clarifying_questions"] = _select_clarifying_questions(blocked_rows, None, None)
    if direct_row is not None and _has_approval_path(direct_row["course"].get("parsed_prereq")):
        plan["clarifying_questions"].append(f"Do you have instructor approval for {direct_row['course']['course_id']}?")
        plan["citations"] = _build_citations([direct_row], {}, include_program=False)
    plan["clarifying_questions"] = _unique(plan["clarifying_questions"])
    return plan


def _build_program_groups(program: dict, include_gen_ed: bool) -> dict:
    core = set(program.get("core_courses", []))
    electives = set(program.get("electives", []))
    general_education: set[str] = set()

    if include_gen_ed:
        for item in program.get("general_education", []):
            if isinstance(item, str):
                general_education.add(item)
            elif isinstance(item, dict):
                general_education.update(item.get("options", []))

    return {
        "core": core,
        "electives": electives,
        "general_education": general_education,
        "all_program_courses": core | electives | general_education,
    }


def _build_program_order(program: dict, include_gen_ed: bool) -> dict[str, int]:
    ordered_codes: list[str] = []
    ordered_codes.extend(program.get("core_courses", []))
    ordered_codes.extend(program.get("electives", []))
    if include_gen_ed:
        for item in program.get("general_education", []):
            if isinstance(item, str):
                ordered_codes.append(item)
            elif isinstance(item, dict):
                ordered_codes.extend(item.get("options", []))

    order: dict[str, int] = {}
    for index, code in enumerate(ordered_codes):
        if code not in order:
            order[code] = index
    return order


def _build_reverse_dependency_graph(courses: list[dict]) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    for course in courses:
        current_id = course["course_id"]
        for dependency in _collect_course_dependencies(course.get("parsed_prereq")):
            graph.setdefault(dependency, set()).add(current_id)
    return graph


def _collect_course_dependencies(node: dict | None) -> set[str]:
    if node is None:
        return set()
    node_type = node["type"]
    if node_type == "COURSE":
        return {node["course"]}
    dependencies: set[str] = set()
    for child in node.get("conditions", []):
        dependencies.update(_collect_course_dependencies(child))
    return dependencies


def _priority_group(course_id: str, program_groups: dict) -> int:
    if course_id in program_groups["core"]:
        return 1
    if course_id in program_groups["electives"]:
        return 3
    if course_id in program_groups["general_education"]:
        return 4
    return 5


def _credits_as_int(value: str | None) -> int:
    if value is None:
        return 0
    return int(float(value))


def _row_sort_key(row: dict) -> tuple[int, int, int, int, str]:
    return (
        -row["score"],
        row["credits"],
        row["program_rank"],
        row["course"]["course_id"],
    )


def _pick_best_row(rows: list[dict]) -> dict | None:
    return rows[0] if rows else None


def _pick_entry_level_row(rows: list[dict]) -> dict | None:
    if not rows:
        return None
    core_rows = [row for row in rows if row["priority_group"] == 1]
    if core_rows:
        return min(core_rows, key=lambda row: (row["program_rank"], row["credits"], row["course"]["course_id"]))
    return min(rows, key=lambda row: (row["program_rank"], row["priority_group"], row["credits"], row["course"]["course_id"]))


def _select_clarifying_questions(
    blocked_rows: list[dict],
    max_credits: int | None,
    total_credits: int | None,
) -> list[str]:
    questions: list[str] = []
    for row in blocked_rows:
        if max_credits is not None and total_credits is not None and total_credits > 0 and total_credits + row["credits"] > max_credits:
            continue
        questions.extend(_clarifying_questions_for_course(row["course"], row["evaluation"]))
    return _unique(questions)


def _clarifying_questions_for_course(course: dict, evaluation: dict) -> list[str]:
    questions: list[str] = []
    for item in evaluation.get("missing", []):
        if item.startswith("grade for "):
            course_code = item.replace("grade for ", "", 1)
            questions.append(f"What grade did you receive in {course_code} so we can check eligibility for {course['course_id']}?")
        elif item.endswith(" score"):
            assessment = item.replace(" score", "", 1)
            questions.append(f"What is your {assessment} score so we can check eligibility for {course['course_id']}?")
        elif _is_approval_label(item):
            questions.append(f"Do you have instructor approval for {course['course_id']}?")
    return _unique(questions)


def _build_justification(selected_rows: list[dict], program_groups: dict, direct_target: str | None = None) -> list[str]:
    items: list[str] = []
    for row in selected_rows:
        course = row["course"]
        course_id = course["course_id"]
        title = course["course_title"]
        evaluation = row["evaluation"]

        if direct_target == course_id:
            items.append(f"{course_id} ({title}) is eligible based on your current record.")
        elif course_id in program_groups["core"]:
            items.append(f"{course_id} ({title}) is a core program requirement and is eligible.")
        elif course_id in program_groups["electives"]:
            items.append(f"{course_id} ({title}) is an eligible program elective.")
        elif course_id in program_groups["general_education"]:
            items.append(f"{course_id} ({title}) satisfies a general education option and is eligible.")
        else:
            items.append(f"{course_id} ({title}) is eligible under your current record.")

        for reason in evaluation.get("reason", []):
            if reason != "No prerequisites listed":
                items.append(f"{course_id}: {reason}.")

    return _unique(items)


def _build_risks(selected_rows: list[dict], total_credits: int, max_credits: int | None) -> list[str]:
    risks: list[str] = []
    technical_courses = [row for row in selected_rows if row["course"]["course_id"].startswith("COMP")]
    if len(technical_courses) >= 2:
        risks.append("This plan includes multiple technical courses, which may create a heavier workload.")
    if max_credits is not None and total_credits >= max_credits:
        risks.append("This plan uses your full credit limit, so there is little room for schedule changes.")
    for row in selected_rows:
        if row["unlock_count"] > 0:
            risks.append(f"Future course options depend on completing {row['course']['course_id']}.")
    return _unique(risks)


def _build_citations(selected_rows: list[dict], program: dict, include_program: bool) -> list[str]:
    citations = [
        f"{row['course']['course_id']}: {row['course'].get('source_url')}"
        for row in selected_rows
        if row["course"].get("source_url")
    ]
    if include_program and program.get("source_url") and selected_rows:
        citations.append(f"{program['program_id']}: {program['source_url']}")
    return _unique(citations)


def _build_alternatives(rows: list[dict], excluded: set[str]) -> list[str]:
    alternatives: list[str] = []
    for row in rows:
        course_id = row["course"]["course_id"]
        if course_id not in excluded:
            alternatives.append(course_id)
        if len(alternatives) == 3:
            break
    return alternatives


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _contains_node_type(node: dict | None, target_type: str) -> bool:
    if node is None:
        return False
    if node["type"] == target_type:
        return True
    return any(_contains_node_type(child, target_type) for child in node.get("conditions", []))


def _has_approval_path(node: dict | None) -> bool:
    return _contains_node_type(node, "EXCEPTION")


def _is_approval_label(value: str) -> bool:
    lowered = value.strip().lower()
    return "permission" in lowered or "approval" in lowered


def _evaluate_for_planning(node: dict | None, request: dict) -> dict:
    cleaned = _remove_exception_nodes(node)
    return evaluate_prereq(cleaned, request)


def _remove_exception_nodes(node: dict | None) -> dict | None:
    if node is None:
        return None
    node_type = node["type"]
    if node_type == "EXCEPTION":
        return None
    if node_type not in {"AND", "OR"}:
        return node

    children = []
    for child in node.get("conditions", []):
        cleaned = _remove_exception_nodes(child)
        if cleaned is not None:
            children.append(cleaned)

    if not children:
        return None
    if len(children) == 1:
        return children[0]
    return {"type": node_type, "conditions": children}


def _score_course(course_id: str, program_groups: dict, reverse_dependencies: dict[str, set[str]]) -> int:
    score = 0
    if course_id in program_groups["core"]:
        score += 10
    if reverse_dependencies.get(course_id):
        score += 20
    return score


def _pick_missing_prerequisite(row: dict, rows_by_id: dict[str, dict], eligible_rows: list[dict]) -> dict | None:
    eligible_by_id = {item["course"]["course_id"]: item for item in eligible_rows}
    for item in row["evaluation"].get("missing", []):
        if item.startswith("grade for "):
            continue
        candidate = rows_by_id.get(item) or eligible_by_id.get(item)
        if candidate is not None and candidate["evaluation"]["decision"] == "Eligible":
            return candidate
    return None


def _has_missing_grade(evaluation: dict) -> bool:
    return any(item.startswith("grade for ") for item in evaluation.get("missing", []))
