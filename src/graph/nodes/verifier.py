from __future__ import annotations

from typing import Any

from src.graph.state import GraphState
from src.utils.constants import DEFAULT_FALLBACK_MAX_CREDITS


def verifier_node(state: GraphState) -> GraphState:
    grounded_output = _build_grounded_verified_output(state)
    planner_verified_output = _verify_planner_output(state)
    return {
        **state,
        "verified_output": (
            planner_verified_output
            if _should_use_planner_output(grounded_output, planner_verified_output, state.get("intent"))
            else grounded_output
        ),
    }


def _build_grounded_verified_output(state: GraphState) -> dict[str, list[str] | str]:
    intent = state.get("intent")
    if intent == "unsupported_catalog_question":
        return _build_unsupported_output(state)
    if intent == "prerequisite_path":
        return _build_prerequisite_path_output(state)
    if intent == "prerequisite_check":
        return _build_prerequisite_check_output(state)
    if intent == "semester_planning":
        return _build_semester_planning_output(state)
    if intent == "requirement_lookup":
        return _build_requirement_lookup_output(state)
    return _build_safe_output(state)


def _should_use_planner_output(
    grounded_output: dict[str, list[str] | str],
    planner_verified_output: dict[str, list[str] | str] | None,
    intent: str | None,
) -> bool:
    if planner_verified_output is None:
        return False
    if intent == "unsupported_catalog_question":
        return False
    return _is_safe_uncited_answer(str(grounded_output.get("answer_plan", "")))


def _verify_planner_output(state: GraphState) -> dict[str, list[str] | str] | None:
    planner_output = state.get("planner_output") or {}
    if not planner_output:
        return None

    assumptions = _merge_unique_lists(planner_output.get("assumptions_not_in_catalog", []))
    if any("planner model was unavailable" in item.lower() for item in assumptions):
        return None

    answer_plan = " ".join(str(planner_output.get("answer_plan", "")).split())
    if not answer_plan:
        return None

    retrieved_ids = set(state.get("retrieved_chunk_ids", []))
    normalized_why: list[str] = []
    derived_citations: list[str] = []

    for item in planner_output.get("why", []):
        claim_text, citation_ids = _split_planner_why_item(str(item))
        if not claim_text:
            return None
        if not citation_ids:
            return None
        if any(chunk_id not in retrieved_ids for chunk_id in citation_ids):
            return None
        normalized_why.append(claim_text)
        for chunk_id in citation_ids:
            if chunk_id not in derived_citations:
                derived_citations.append(chunk_id)

    planner_citations = [str(item).strip() for item in planner_output.get("citations", []) if str(item).strip()]
    if planner_citations and set(planner_citations) != set(derived_citations):
        return None

    if _is_safe_uncited_answer(answer_plan) and (planner_citations or derived_citations):
        return None
    if normalized_why and not derived_citations:
        return None
    if not normalized_why and not _is_safe_uncited_answer(answer_plan):
        return None

    return {
        "answer_plan": answer_plan,
        "why": normalized_why,
        "citations": derived_citations,
        "clarifying_questions": _merge_unique_lists(
            state.get("clarifying_questions", []),
            planner_output.get("clarifying_questions", []),
        ),
        "assumptions_not_in_catalog": _merge_unique_lists(
            state.get("context_assumptions", []),
            assumptions,
        ),
    }


def _build_unsupported_output(state: GraphState) -> dict[str, list[str] | str]:
    return {
        "answer_plan": "I do not have that information in the provided catalog/policies.",
        "why": ["The information you asked for is not present in the retrieved catalog chunks."],
        "citations": [],
        "clarifying_questions": [],
        "assumptions_not_in_catalog": _merge_unique_lists(
            state.get("context_assumptions", []),
            [_unsupported_gap_note(state.get("query", ""))],
        ),
    }


def _build_prerequisite_check_output(state: GraphState) -> dict[str, list[str] | str]:
    profile = state.get("student_profile", {})
    target_course_id = profile.get("target_course")
    if not target_course_id:
        return _build_safe_output(state)

    course_record = _get_course_record(state, target_course_id)
    if not course_record:
        return _build_safe_output(
            state,
            assumptions=[f"No structured catalog record was found for {target_course_id}."],
        )

    completed_courses = set(profile.get("completed_courses", []))
    grades = dict(profile.get("grades", {}))
    has_instructor_permission = bool(profile.get("has_instructor_permission"))
    evaluation = _evaluate_course_readiness(course_record, completed_courses, grades, has_instructor_permission)

    chunk_id = _find_chunk_id_for_course(state, target_course_id)
    prereq_text = _normalized_prereq_text(course_record)
    why: list[str] = []
    citations: list[str] = []
    if chunk_id:
        why.append(f'The catalog lists the prerequisites for {target_course_id} as "{prereq_text}".')
        citations.append(chunk_id)

    assumptions = list(state.get("context_assumptions", []))
    clarifying_questions: list[str] = []

    if evaluation["used_permission"]:
        if chunk_id:
            why.append(f"Instructor permission is listed as an alternate prerequisite path for {target_course_id}.")
        return {
            "answer_plan": f"Eligible to take {target_course_id} based on the instructor-permission exception listed in the catalog.",
            "why": why,
            "citations": _merge_unique_lists(citations),
            "clarifying_questions": [],
            "assumptions_not_in_catalog": _merge_unique_lists(assumptions),
        }

    if evaluation["status"] == "eligible":
        if chunk_id:
            if _prereq_is_none(course_record):
                why.append(f"{target_course_id} does not list any catalog prerequisite courses.")
            elif _is_skill_only_prerequisite_text(prereq_text):
                why.append(
                    f"{target_course_id} does not list enforceable course prerequisites; the catalog only describes background skills."
                )
            else:
                why.append(f"The courses and grades you provided satisfy the listed prerequisite rule for {target_course_id}.")
        if evaluation["manual_options"] and _is_skill_only_prerequisite_text(prereq_text):
            assumptions.append("Skill-based prerequisite notes were treated as informational only and did not block eligibility.")
        return {
            "answer_plan": f"Eligible to take {target_course_id} based on the catalog requirements you provided.",
            "why": why,
            "citations": _merge_unique_lists(citations),
            "clarifying_questions": [],
            "assumptions_not_in_catalog": _merge_unique_lists(assumptions),
        }

    if evaluation["status"] == "need_more_info":
        if evaluation["missing_grades"]:
            why.append(
                f"I still need the grades for {', '.join(evaluation['missing_grades'])} to check the catalog minimum-grade rule."
            )
            clarifying_questions.append(_grade_question(evaluation["missing_grades"]))
        if evaluation["manual_options"] and not evaluation["missing_grades"]:
            why.append(
                "The catalog also lists additional prerequisite conditions that cannot be verified from the current information alone."
            )
            clarifying_questions.append(_manual_option_question(evaluation["manual_options"]))
        elif evaluation["manual_options"]:
            assumptions.append(
                f"The catalog also lists alternate paths such as {', '.join(evaluation['manual_options'])}."
            )
        if not evaluation["missing_grades"] and not evaluation["manual_options"]:
            clarifying_questions.extend(state.get("clarifying_questions", []))
        return {
            "answer_plan": f"Need more info to determine whether you can take {target_course_id}.",
            "why": why,
            "citations": _merge_unique_lists(citations),
            "clarifying_questions": _merge_unique_lists(state.get("clarifying_questions", []), clarifying_questions),
            "assumptions_not_in_catalog": _merge_unique_lists(assumptions),
        }

    if evaluation["missing_courses"]:
        why.append(f"You are still missing the required prerequisite course(s): {', '.join(evaluation['missing_courses'])}.")
    if evaluation["low_grades"]:
        why.append(_low_grade_reason(evaluation["low_grades"]))
    if evaluation["manual_options"] and not has_instructor_permission:
        assumptions.append(
            f"The catalog lists alternate prerequisite paths such as {', '.join(evaluation['manual_options'])}, but you did not say you satisfy them."
        )

    return {
        "answer_plan": f"Not eligible to take {target_course_id} based on the catalog requirements you provided.",
        "why": why,
        "citations": _merge_unique_lists(citations),
        "clarifying_questions": [],
        "assumptions_not_in_catalog": _merge_unique_lists(assumptions),
    }


def _build_prerequisite_path_output(state: GraphState) -> dict[str, list[str] | str]:
    profile = state.get("student_profile", {})
    target_course_id = profile.get("target_course")
    if not target_course_id:
        return _build_safe_output(state)

    course_map = _course_map(state)
    target_course = course_map.get(target_course_id)
    if not target_course:
        return _build_safe_output(
            state,
            assumptions=[f"No structured catalog record was found for {target_course_id}."],
        )

    sequence = _build_course_sequence(target_course_id, course_map)
    direct_courses = _ordered_direct_course_ids(target_course, course_map)
    completed_courses = set(profile.get("completed_courses", []))

    target_chunk_id = _find_chunk_id_for_course(state, target_course_id)
    why: list[str] = []
    citations: list[str] = []
    if target_chunk_id:
        why.append(
            f'The target course {target_course_id} lists "{_normalized_prereq_text(target_course)}" as its direct prerequisite rule.'
        )
        citations.append(target_chunk_id)

    for course_id in sequence:
        dependency_course = course_map.get(course_id)
        dependency_chunk_id = _find_chunk_id_for_course(state, course_id)
        if not dependency_course or not dependency_chunk_id:
            continue
        if _prereq_is_none(dependency_course):
            continue
        why.append(
            f'{course_id} lists "{_normalized_prereq_text(dependency_course)}" as its own prerequisite rule.'
        )
        citations.append(dependency_chunk_id)

    clarifying_questions: list[str] = []
    assumptions = list(state.get("context_assumptions", []))

    if completed_courses:
        remaining = [course_id for course_id in sequence if course_id not in completed_courses]
        if remaining:
            answer_plan = f"Next step toward {target_course_id}: take {remaining[0]} next."
        else:
            answer_plan = f"You have completed the course path leading up to {target_course_id}."
    elif _wants_direct_prerequisite_list(state.get("query", "")) and direct_courses:
        answer_plan = f"Required courses before {target_course_id}: {', '.join(direct_courses)}."
    else:
        full_path = sequence + [target_course_id] if sequence else [target_course_id]
        answer_plan = f"Course path to reach {target_course_id}: {' -> '.join(full_path)}."

    return {
        "answer_plan": answer_plan,
        "why": why,
        "citations": _merge_unique_lists(citations),
        "clarifying_questions": _merge_unique_lists(state.get("clarifying_questions", []), clarifying_questions),
        "assumptions_not_in_catalog": _merge_unique_lists(assumptions),
    }


def _build_requirement_lookup_output(state: GraphState) -> dict[str, list[str] | str]:
    profile = state.get("student_profile", {})
    target_course_id = profile.get("target_course")
    target_program_id = profile.get("target_program")

    if target_course_id:
        course_record = _get_course_record(state, target_course_id)
        chunk_id = _find_chunk_id_for_course(state, target_course_id)
        why: list[str] = []
        citations: list[str] = []
        if course_record and chunk_id:
            why.append(
                f'The retrieved course chunk for {target_course_id} lists "{_normalized_prereq_text(course_record)}" as the catalog prerequisite rule.'
            )
            citations.append(chunk_id)
        return {
            "answer_plan": f"The main catalog requirement I found for {target_course_id} is its listed prerequisite rule.",
            "why": why,
            "citations": citations,
            "clarifying_questions": [],
            "assumptions_not_in_catalog": _merge_unique_lists(state.get("context_assumptions", [])),
        }

    if target_program_id:
        program = state.get("program", {})
        chunk_id = _find_chunk_id_for_program(state, target_program_id)
        why: list[str] = []
        citations: list[str] = []
        if chunk_id:
            citations.append(chunk_id)
            lowered_query = (state.get("query") or "").lower()
            if "prioritize" in lowered_query:
                completed = set(profile.get("completed_courses", []))
                remaining_core = [course_id for course_id in program.get("core_courses", []) if course_id not in completed]
                why.append(
                    f"The program chunk says students must complete all required core courses, and the listed core courses are {', '.join(program.get('core_courses', []))}."
                )
                if completed:
                    answer_plan = f"Prioritize these remaining core courses next: {', '.join(remaining_core or program.get('core_courses', []))}."
                    clarifying_questions: list[str] = []
                else:
                    answer_plan = f"Start by prioritizing the core courses listed in the program: {', '.join(program.get('core_courses', []))}."
                    clarifying_questions = ["If you want a personalized priority order, which program courses have you already completed?"]
                return {
                    "answer_plan": answer_plan,
                    "why": why,
                    "citations": citations,
                    "clarifying_questions": clarifying_questions,
                        "assumptions_not_in_catalog": _merge_unique_lists(state.get("context_assumptions", [])),
                }

            why.extend(
                [
                    f"The program chunk states that {program.get('program_name')} requires {program.get('total_credits_required')} total credits.",
                    f"The same chunk lists these core courses: {', '.join(program.get('core_courses', []))}.",
                    "The same chunk also mentions additional elective, general education, and capstone requirements.",
                ]
            )
        return {
            "answer_plan": (
                f"The retrieved program chunk lists these core courses for {program.get('program_name')}: "
                f"{', '.join(program.get('core_courses', []))}."
            ),
            "why": why,
            "citations": citations,
            "clarifying_questions": [],
            "assumptions_not_in_catalog": _merge_unique_lists(state.get("context_assumptions", [])),
        }

    return _build_safe_output(state)


def _build_semester_planning_output(state: GraphState) -> dict[str, list[str] | str]:
    profile = state.get("student_profile", {})
    target_program_id = profile.get("target_program")
    completed_courses = set(profile.get("completed_courses", []))
    grades = dict(profile.get("grades", {}))
    has_instructor_permission = bool(profile.get("has_instructor_permission"))

    if not target_program_id:
        return _build_safe_output(state)

    program = state.get("program", {})
    program_chunk_id = _find_chunk_id_for_program(state, target_program_id)
    program_citation = [program_chunk_id] if program_chunk_id else []
    assumptions = list(state.get("context_assumptions", []))

    if not completed_courses:
        why = []
        if program_chunk_id:
            why.append(
                f"The program chunk lists core courses such as {', '.join(program.get('core_courses', []))} for {program.get('program_name')}."
            )
        return {
            "answer_plan": "I can identify the required program courses, but I need your completed courses to build a safe next-semester plan.",
            "why": why,
            "citations": program_citation,
            "clarifying_questions": _merge_unique_lists(state.get("clarifying_questions", [])),
            "assumptions_not_in_catalog": _merge_unique_lists(assumptions),
        }

    max_credits = profile.get("max_credits")
    if max_credits is None:
        max_credits = DEFAULT_FALLBACK_MAX_CREDITS
        assumptions.append(
            f"Used the fallback maximum credit load of {DEFAULT_FALLBACK_MAX_CREDITS} because none was provided."
        )

    course_map = _course_map(state)
    planned_courses: list[str] = []
    planned_credits = 0
    why: list[str] = []
    citations: list[str] = list(program_citation)

    if program_chunk_id:
        why.append(
            f"The program chunk lists required core courses for {program.get('program_name')}, and those are the first courses I prioritized."
        )

    for course_id in list(program.get("core_courses", [])) + list(program.get("electives", [])):
        if course_id in completed_courses or course_id in planned_courses:
            continue

        course_record = course_map.get(str(course_id))
        chunk_id = _find_chunk_id_for_course(state, str(course_id))
        if course_record is None or chunk_id is None:
            continue

        evaluation = _evaluate_course_readiness(course_record, completed_courses, grades, has_instructor_permission)
        if evaluation["status"] != "eligible":
            continue

        course_credits = _parse_credits(course_record.get("credits"))
        if planned_credits + course_credits > max_credits:
            continue

        planned_courses.append(str(course_id))
        planned_credits += course_credits
        citations.append(chunk_id)

        prereq_text = _normalized_prereq_text(course_record)
        if _prereq_is_none(course_record):
            why.append(f"{course_id} is a listed program course and its retrieved chunk does not list any prerequisite courses.")
        else:
            why.append(f'{course_id} is a listed program course and its retrieved chunk lists "{prereq_text}" as the prerequisite rule.')

        if planned_credits >= max_credits:
            break

    if not planned_courses:
        return {
            "answer_plan": "Need more info to build a safe next-semester plan from the retrieved catalog chunks.",
            "why": why,
            "citations": _merge_unique_lists(citations),
            "clarifying_questions": _merge_unique_lists(
                state.get("clarifying_questions", []),
                ["If you want a more specific plan, please share any prerequisite grades that could affect course eligibility."],
            ),
            "assumptions_not_in_catalog": _merge_unique_lists(
                assumptions,
                ["I only recommended courses whose supporting course chunks were retrieved and whose prerequisites could be checked from the current information."],
            ),
        }

    return {
        "answer_plan": f"Suggested next-term courses: {', '.join(planned_courses)} ({planned_credits} credits total).",
        "why": why,
        "citations": _merge_unique_lists(citations),
        "clarifying_questions": [],
        "assumptions_not_in_catalog": _merge_unique_lists(assumptions),
    }


def _build_safe_output(
    state: GraphState,
    *,
    assumptions: list[str] | None = None,
) -> dict[str, list[str] | str]:
    clarifying_questions = _merge_unique_lists(state.get("clarifying_questions", []))
    assumption_list = _merge_unique_lists(state.get("context_assumptions", []), assumptions or [])
    answer_plan = (
        "Need more info to answer this from the catalog."
        if clarifying_questions
        else "I do not have that information in the provided catalog/policies."
    )
    return {
        "answer_plan": answer_plan,
        "why": [],
        "citations": [],
        "clarifying_questions": clarifying_questions,
        "assumptions_not_in_catalog": assumption_list,
    }


def _split_planner_why_item(item: str) -> tuple[str, list[str]]:
    stripped = " ".join(item.split())
    if not stripped.endswith("]]") or "[[" not in stripped:
        return stripped, []

    prefix, _, suffix = stripped.rpartition("[[")
    claim_text = prefix.strip()
    citation_text = suffix[:-2].strip()
    citation_ids = [value.strip() for value in citation_text.split(",") if value.strip()]
    return claim_text, citation_ids


def _is_safe_uncited_answer(answer_plan: str) -> bool:
    lowered = answer_plan.lower()
    return "i do not have that information" in lowered or "need more info" in lowered


def _evaluate_course_readiness(
    course_record: dict[str, Any],
    completed_courses: set[str],
    grades: dict[str, str],
    has_instructor_permission: bool,
) -> dict[str, Any]:
    parsed_prereq = course_record.get("parsed_prereq")
    prereq_text = _normalized_prereq_text(course_record)

    if parsed_prereq is None:
        if prereq_text.lower() == "none":
            return _result("eligible")
        if _is_skill_only_prerequisite_text(prereq_text):
            return _result("eligible", manual_options=[prereq_text])
        return _result("need_more_info", manual_options=[prereq_text])

    return _evaluate_prereq_node(parsed_prereq, completed_courses, grades, has_instructor_permission)


def _evaluate_prereq_node(
    node: dict[str, Any] | None,
    completed_courses: set[str],
    grades: dict[str, str],
    has_instructor_permission: bool,
) -> dict[str, Any]:
    if not isinstance(node, dict):
        return _result("eligible")

    node_type = str(node.get("type") or "")
    if node_type == "COURSE":
        course_id = str(node.get("course") or "").strip()
        min_grade = str(node.get("min_grade") or "").strip()
        if course_id not in completed_courses:
            return _result("not_eligible", missing_courses=[course_id])
        if not min_grade:
            return _result("eligible")
        actual_grade = grades.get(course_id)
        if actual_grade is None:
            return _result("need_more_info", missing_grades=[course_id])
        if _grade_value(actual_grade) < _grade_value(min_grade):
            return _result("not_eligible", low_grades=[(course_id, actual_grade, min_grade)])
        return _result("eligible")

    if node_type == "EXCEPTION":
        option = str(node.get("value") or "exception")
        if has_instructor_permission:
            return _result("eligible", manual_options=[option], used_permission=True)
        return _result("not_eligible", manual_options=[option])

    if node_type == "ASSESSMENT":
        assessment = str(node.get("assessment") or "assessment").replace("_", " ")
        min_score = node.get("min_score")
        option = f"{assessment} >= {min_score}" if min_score is not None else assessment
        return _result("need_more_info", manual_options=[option])

    if node_type == "NON_ENFORCEABLE":
        reason = str(node.get("reason") or "additional experience requirement")
        return _result("eligible", manual_options=[reason])

    if node_type == "AND":
        results = [
            _evaluate_prereq_node(child, completed_courses, grades, has_instructor_permission)
            for child in node.get("conditions", [])
        ]
        return _combine_and_results(results)

    if node_type == "OR":
        results = [
            _evaluate_prereq_node(child, completed_courses, grades, has_instructor_permission)
            for child in node.get("conditions", [])
        ]
        return _combine_or_results(results)

    return _result("need_more_info", manual_options=[str(node_type or "unparsed prerequisite rule")])


def _combine_and_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    if any(item["status"] == "not_eligible" for item in results):
        status = "not_eligible"
    elif any(item["status"] == "need_more_info" for item in results):
        status = "need_more_info"
    else:
        status = "eligible"

    return _result(
        status,
        missing_courses=_merge_unique_lists(*(item["missing_courses"] for item in results)),
        missing_grades=_merge_unique_lists(*(item["missing_grades"] for item in results)),
        manual_options=_merge_unique_lists(*(item["manual_options"] for item in results)),
        low_grades=_merge_unique_tuples(*(item["low_grades"] for item in results)),
        used_permission=any(item["used_permission"] for item in results),
    )


def _combine_or_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    eligible_results = [item for item in results if item["status"] == "eligible"]
    if eligible_results:
        return _best_result(eligible_results)

    need_more_info_results = [item for item in results if item["status"] == "need_more_info"]
    if need_more_info_results:
        best = _best_result(need_more_info_results)
        best["manual_options"] = _merge_unique_lists(
            best["manual_options"],
            *(item["manual_options"] for item in results),
        )
        return best

    course_route_results = [
        item
        for item in results
        if item["status"] == "not_eligible"
        and (item["missing_courses"] or item["missing_grades"] or item["low_grades"])
    ]
    best = _best_result(course_route_results or results)
    best["manual_options"] = _merge_unique_lists(
        best["manual_options"],
        *(item["manual_options"] for item in results),
    )
    return best


def _best_result(results: list[dict[str, Any]]) -> dict[str, Any]:
    return min(
        results,
        key=lambda item: (
            1 if item["used_permission"] else 0,
            len(item["missing_courses"]) + len(item["missing_grades"]) + len(item["low_grades"]) + len(item["manual_options"]),
        ),
    ).copy()


def _build_course_sequence(
    course_id: str,
    course_map: dict[str, dict[str, Any]],
    visited: set[str] | None = None,
) -> list[str]:
    if visited is None:
        visited = set()
    if course_id in visited:
        return []
    visited.add(course_id)

    course_record = course_map.get(course_id)
    if not course_record:
        return []

    branch = _preferred_course_branch(course_record.get("parsed_prereq"))
    direct_courses = _collect_course_ids(branch)
    direct_courses.sort(
        key=lambda dependency_id: (
            0 if not _build_course_sequence(dependency_id, course_map, set(visited)) else -1,
            dependency_id,
        )
    )
    ordered: list[str] = []
    for dependency_id in direct_courses:
        for nested_id in _build_course_sequence(dependency_id, course_map, visited):
            if nested_id not in ordered:
                ordered.append(nested_id)
        if dependency_id not in ordered:
            ordered.append(dependency_id)
    return ordered


def _ordered_direct_course_ids(course_record: dict[str, Any], course_map: dict[str, dict[str, Any]]) -> list[str]:
    branch = _preferred_course_branch(course_record.get("parsed_prereq"))
    direct_courses = _collect_course_ids(branch)
    direct_courses.sort(
        key=lambda dependency_id: (
            0 if _build_course_sequence(dependency_id, course_map, set()) else 1,
            dependency_id,
        )
    )
    return direct_courses


def _wants_direct_prerequisite_list(query: str) -> bool:
    lowered = str(query or "").lower()
    return "what courses do i need" in lowered or "before taking" in lowered


def _preferred_course_branch(node: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(node, dict):
        return None
    if node.get("type") != "OR":
        return node

    conditions = list(node.get("conditions", []))
    if not conditions:
        return node

    def rank(item: dict[str, Any]) -> tuple[int, int]:
        course_count = len(_collect_course_ids(item))
        if course_count > 0:
            return (0, -course_count)
        item_type = str(item.get("type") or "")
        if item_type == "ASSESSMENT":
            return (1, 0)
        if item_type == "NON_ENFORCEABLE":
            return (2, 0)
        if item_type == "EXCEPTION":
            return (3, 0)
        return (4, 0)

    return sorted(conditions, key=rank)[0]


def _collect_course_ids(node: dict[str, Any] | None) -> list[str]:
    if not isinstance(node, dict):
        return []

    node_type = str(node.get("type") or "")
    if node_type == "COURSE":
        course_id = str(node.get("course") or "").strip()
        return [course_id] if course_id else []
    if node_type in {"AND", "OR"}:
        ordered: list[str] = []
        for child in node.get("conditions", []):
            for course_id in _collect_course_ids(child):
                if course_id not in ordered:
                    ordered.append(course_id)
        return ordered
    return []


def _course_map(state: GraphState) -> dict[str, dict[str, Any]]:
    return {
        str(course.get("course_id")): course
        for course in state.get("courses", [])
        if course.get("course_id")
    }


def _get_course_record(state: GraphState, course_id: str) -> dict[str, Any] | None:
    return _course_map(state).get(course_id)


def _find_chunk_id_for_course(state: GraphState, course_id: str | None) -> str | None:
    if not course_id:
        return None
    for chunk in state.get("retrieved_chunks", []):
        if chunk.get("metadata", {}).get("course_id") == course_id:
            return _chunk_id(chunk)
    return None


def _find_chunk_id_for_program(state: GraphState, program_id: str | None) -> str | None:
    if not program_id:
        return None
    for chunk in state.get("retrieved_chunks", []):
        if chunk.get("metadata", {}).get("program_id") == program_id:
            return _chunk_id(chunk)
    return None


def _chunk_id(chunk: dict[str, Any]) -> str | None:
    metadata_chunk_id = chunk.get("metadata", {}).get("chunk_id")
    top_level_chunk_id = chunk.get("chunk_id")
    value = metadata_chunk_id or top_level_chunk_id
    return str(value) if value else None


def _normalized_prereq_text(course_record: dict[str, Any]) -> str:
    raw_value = course_record.get("prerequisites")
    text = " ".join(str(raw_value or "None").split())
    return text or "None"


def _is_skill_only_prerequisite_text(prereq_text: str) -> bool:
    lowered = " ".join(str(prereq_text or "").split()).lower()
    if not lowered or lowered == "none":
        return False
    return "(skill)" in lowered or "skill -" in lowered or "basic windows navigation" in lowered


def _prereq_is_none(course_record: dict[str, Any]) -> bool:
    return _normalized_prereq_text(course_record).lower() == "none"


def _grade_question(course_ids: list[str]) -> str:
    if len(course_ids) == 1:
        return f"What grade did you earn in {course_ids[0]}?"
    return f"What grades did you earn in {', '.join(course_ids[:-1])}, and {course_ids[-1]}?"


def _manual_option_question(options: list[str]) -> str:
    if len(options) == 1:
        return f"Do you satisfy this alternate catalog condition: {options[0]}?"
    return f"Do you satisfy any of these alternate catalog conditions: {', '.join(options)}?"


def _low_grade_reason(low_grades: list[tuple[str, str, str]]) -> str:
    parts = [
        f"{course_id} needs {required_grade} or better, but you reported {actual_grade}"
        for course_id, actual_grade, required_grade in low_grades
    ]
    if len(parts) == 1:
        return parts[0] + "."
    return "; ".join(parts) + "."


def _unsupported_gap_note(query: str) -> str:
    lowered = str(query or "").lower()
    if any(token in lowered for token in ("offered", "schedule", "next semester")):
        return "Course offering and schedule information is not present in the provided catalog data."
    if any(token in lowered for token in ("professor", "instructor", "teaches")):
        return "Instructor and professor information is not present in the provided catalog data."
    if "harder than" in lowered or "best" in lowered:
        return "Comparative opinions are not present in the provided catalog data."
    return "The requested information is not present in the provided catalog data."


def _result(
    status: str,
    *,
    missing_courses: list[str] | None = None,
    missing_grades: list[str] | None = None,
    low_grades: list[tuple[str, str, str]] | None = None,
    manual_options: list[str] | None = None,
    used_permission: bool = False,
) -> dict[str, Any]:
    return {
        "status": status,
        "missing_courses": list(missing_courses or []),
        "missing_grades": list(missing_grades or []),
        "low_grades": list(low_grades or []),
        "manual_options": list(manual_options or []),
        "used_permission": used_permission,
    }


def _grade_value(grade: str) -> int:
    ranking = {
        "A+": 12,
        "A": 11,
        "A-": 10,
        "B+": 9,
        "B": 8,
        "B-": 7,
        "C+": 6,
        "C": 5,
        "C-": 4,
        "D+": 3,
        "D": 2,
        "D-": 1,
        "F": 0,
    }
    return ranking.get(str(grade).upper(), -1)


def _parse_credits(raw_value: object) -> int:
    try:
        return int(str(raw_value))
    except Exception:
        return 0


def _merge_unique_lists(*values: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for items in values:
        for item in items:
            normalized = " ".join(str(item).split())
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(normalized)
    return merged


def _merge_unique_tuples(*values: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    merged: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for items in values:
        for item in items:
            normalized = tuple(str(part) for part in item)
            if normalized in seen:
                continue
            seen.add(normalized)
            merged.append(normalized)
    return merged
