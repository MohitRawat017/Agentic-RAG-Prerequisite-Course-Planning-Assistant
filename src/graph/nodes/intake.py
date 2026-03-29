from __future__ import annotations

import re

from src.graph.state import GraphState
from src.rag.chunking import load_catalog_records
from src.rag.retriever import build_retrieval_queries


COURSE_CODE_PATTERN = re.compile(r"\b([A-Z]{3,4}\d{3,4})\b", re.IGNORECASE)
GRADE_PATTERN = re.compile(r"\b([ABCDF][+-]?)\b", re.IGNORECASE)


def intake_node(state: GraphState) -> GraphState:
    query = " ".join((state.get("query") or "").split())
    courses, program, policies = load_catalog_records(
        state.get("courses_path"),
        state.get("program_path"),
        state.get("policies_path"),
    )

    intent = _detect_intent(query)
    target_course = _extract_target_course(query, courses, intent)
    target_program = _extract_target_program(query, program)
    context_assumptions: list[str] = []

    if intent == "semester_planning" and target_program is None and program.get("program_id"):
        target_program = program
        context_assumptions.append(
            f"Used {program.get('program_name')} as the target program because it is the only program record in the current dataset."
        )

    completed_courses = _extract_completed_courses(query, target_course)
    grades = _extract_grades(query, completed_courses)
    target_term = _extract_target_term(query)
    max_credits = _extract_max_credits(query)

    student_profile = {
        "target_course": target_course.get("course_id") if target_course else None,
        "target_course_name": target_course.get("course_title") if target_course else None,
        "target_program": target_program.get("program_id") if target_program else None,
        "target_program_name": target_program.get("program_name") if target_program else None,
        "completed_courses": completed_courses,
        "grades": grades,
        "target_term": target_term,
        "max_credits": max_credits,
        "has_instructor_permission": _extract_instructor_permission(query),
    }

    missing_fields, critical_missing_fields = _identify_missing_fields(intent, student_profile)
    clarifying_questions = _build_clarifying_questions(intent, missing_fields)
    retrieval_queries = _build_all_retrieval_queries(intent, query, student_profile, courses, program)
    priority_course_ids = _build_priority_course_ids(intent, student_profile, courses, program)
    retrieval_filters = _build_retrieval_filters(intent, student_profile)
    has_target_entity = bool(student_profile["target_course"] or student_profile["target_program"])

    return {
        **state,
        "query": query,
        "intent": intent,
        "student_profile": student_profile,
        "missing_fields": missing_fields,
        "critical_missing_fields": critical_missing_fields,
        "clarifying_questions": clarifying_questions,
        "context_assumptions": context_assumptions,
        "retrieval_queries": retrieval_queries,
        "retrieval_filters": retrieval_filters,
        "priority_course_ids": priority_course_ids,
        "skip_to_formatter": bool(critical_missing_fields and not has_target_entity),
        "courses": courses,
        "program": program,
        "policies": policies,
    }


def _detect_intent(query: str) -> str:
    lowered = query.lower()

    if any(token in lowered for token in ("when is", "when does", "offered", "schedule", "professor", "who teaches", "teaches", "harder than", "best professor")):
        return "unsupported_catalog_question"
    if any(
        phrase in lowered
        for phrase in (
            "prerequisite path",
            "path to reach",
            "what courses do i need",
            "what should i do next",
            "what should i take next",
            "eventually take",
            "in sequence to reach",
            "before taking",
            "reach comp",
        )
    ):
        return "prerequisite_path"
    if any(token in lowered for token in ("plan my courses", "plan my classes", "plan my semester", "next semester", "next term", "course plan", "plan my next semester")):
        return "semester_planning"
    if any(token in lowered for token in ("can i take", "eligible", "prerequisite", "prereq", "enroll in", "register for")):
        return "prerequisite_check"
    if any(token in lowered for token in ("requirements", "program", "major", "credits required", "core courses", "prioritize")):
        return "requirement_lookup"
    return "requirement_lookup"


def _extract_target_course(query: str, courses: list[dict], intent: str) -> dict | None:
    course_by_id = {str(course.get("course_id")).upper(): course for course in courses if course.get("course_id")}
    title_pairs = sorted(
        [
            (str(course.get("course_title")).lower(), course)
            for course in courses
            if course.get("course_title")
        ],
        key=lambda item: len(item[0]),
        reverse=True,
    )

    patterns = (
        r"(?:take|eligible for|enroll in|register for|before taking|prerequisites? of|prerequisites? for|prereq(?:uisites)? of|prereq(?:uisites)? for|path to reach|reach)\s+([A-Z]{3,4}\d{3,4})",
        r"(?:can i take|can i enroll in)\s+([A-Z]{3,4}\d{3,4})",
    )
    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if not match:
            continue
        course_id = match.group(1).upper()
        if course_id in course_by_id:
            return course_by_id[course_id]

    if intent == "semester_planning":
        return None

    query_upper = query.upper()
    codes = [match.group(1).upper() for match in COURSE_CODE_PATTERN.finditer(query_upper)]
    if len(codes) == 1 and codes[0] in course_by_id:
        return course_by_id[codes[0]]

    lowered = query.lower()
    for title, course in title_pairs:
        if title and title in lowered:
            return course

    return course_by_id.get(codes[0]) if codes else None


def _extract_target_program(query: str, program: dict) -> dict | None:
    program_id = str(program.get("program_id") or "")
    program_name = str(program.get("program_name") or "")
    lowered = query.lower()

    if program_id and program_id.lower() in lowered:
        return program
    if program_name and program_name.lower() in lowered:
        return program
    if "information systems" in lowered:
        return program
    return None


def _extract_completed_courses(query: str, target_course: dict | None) -> list[str]:
    course_codes = [match.group(1).upper() for match in COURSE_CODE_PATTERN.finditer(query)]
    target_course_id = str(target_course.get("course_id")) if target_course else None

    completed: list[str] = []
    for course_id in course_codes:
        if target_course_id and course_id == target_course_id:
            continue
        if _is_negated_course_reference(query, course_id):
            continue
        if course_id not in completed:
            completed.append(course_id)
    return completed


def _is_negated_course_reference(query: str, course_id: str) -> bool:
    patterns = (
        rf"without(?:\s+\w+){{0,3}}\s+{course_id}\b",
        rf"not(?:\s+\w+){{0,3}}\s+{course_id}\b",
        rf"have\s+not\s+tak(?:e|en)(?:\s+\w+){{0,3}}\s+{course_id}\b",
        rf"haven't\s+tak(?:e|en)(?:\s+\w+){{0,3}}\s+{course_id}\b",
        rf"did\s+not\s+tak(?:e|en)(?:\s+\w+){{0,3}}\s+{course_id}\b",
    )
    return any(re.search(pattern, query, re.IGNORECASE) for pattern in patterns)


def _extract_grades(query: str, completed_courses: list[str]) -> dict[str, str]:
    grades: dict[str, str] = {}
    for course_id in completed_courses:
        patterns = (
            rf"{course_id}\s*\(([ABCDF][+-]?)\)",
            rf"{course_id}.{{0,25}}?grade(?:s)?(?:\s+of|\s+is|\s+was|\s+)?\s*([ABCDF][+-]?)",
            rf"{course_id}.{{0,15}}?with\s+([ABCDF][+-]?)",
        )
        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                grades[course_id] = match.group(1).upper()
                break

    if grades or not completed_courses:
        return grades

    ordered_grades = [match.group(1).upper() for match in GRADE_PATTERN.finditer(query)]
    if len(ordered_grades) == len(completed_courses):
        return dict(zip(completed_courses, ordered_grades, strict=False))

    shared_grade_match = re.search(r"with(?:\s+grade)?\s+([ABCDF][+-]?)\b", query, re.IGNORECASE)
    if shared_grade_match and completed_courses:
        shared_grade = shared_grade_match.group(1).upper()
        return {course_id: shared_grade for course_id in completed_courses}

    return grades


def _extract_target_term(query: str) -> str | None:
    match = re.search(r"\b(fall|spring|summer|winter)\s*(\d{4})?\b", query, re.IGNORECASE)
    if match:
        season = match.group(1).capitalize()
        year = match.group(2)
        return f"{season} {year}".strip()
    if re.search(r"\bnext (semester|term)\b", query, re.IGNORECASE):
        return "next semester"
    return None


def _extract_max_credits(query: str) -> int | None:
    patterns = (
        r"(?:max(?:imum)?|up to|at most)\s+(\d+)\s+credits?",
        r"max(?:imum)?\s+credits?\s*(?:are|is|=|:)?\s*(\d+)",
        r"(\d+)\s+credits?\s+(?:max(?:imum)?|limit)",
        r"credit\s+limit\s*(?:is|=|:)?\s*(\d+)",
    )
    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _extract_instructor_permission(query: str) -> bool:
    lowered = query.lower()
    return "instructor permission" in lowered or "instructor consent" in lowered


def _identify_missing_fields(intent: str, student_profile: dict) -> tuple[list[str], list[str]]:
    missing_fields: list[str] = []
    critical_missing_fields: list[str] = []

    target_course = student_profile.get("target_course")
    target_program = student_profile.get("target_program")
    completed_courses = student_profile.get("completed_courses") or []
    max_credits = student_profile.get("max_credits")

    if intent == "prerequisite_check":
        if not target_course:
            missing_fields.append("target_course")
            critical_missing_fields.append("target_course")
        if not completed_courses and not student_profile.get("has_instructor_permission"):
            missing_fields.append("completed_courses")
    elif intent == "prerequisite_path":
        if not target_course:
            missing_fields.append("target_course")
            critical_missing_fields.append("target_course")
    elif intent == "semester_planning":
        if not target_program:
            missing_fields.append("target_program")
            critical_missing_fields.append("target_program")
        if not completed_courses:
            missing_fields.append("completed_courses")
        if max_credits is None:
            missing_fields.append("max_credits")
    elif intent == "requirement_lookup":
        if not target_course and not target_program:
            missing_fields.append("target_entity")
            critical_missing_fields.append("target_entity")

    return missing_fields, critical_missing_fields


def _build_clarifying_questions(intent: str, missing_fields: list[str]) -> list[str]:
    questions: list[str] = []

    if "target_course" in missing_fields or "target_entity" in missing_fields:
        questions.append("Which course or program should I look up in the catalog?")
    if intent == "semester_planning" and "target_program" in missing_fields:
        questions.append("Which target program or major should I plan for?")
    if "completed_courses" in missing_fields:
        questions.append("Which courses have you already completed, and what grades did you earn if they matter?")
    if "max_credits" in missing_fields:
        questions.append("What is your maximum credit load for the next term?")
    return questions


def _build_all_retrieval_queries(
    intent: str,
    original_query: str,
    student_profile: dict,
    courses: list[dict],
    program: dict,
) -> list[str]:
    course_by_id = {str(course.get("course_id")): course for course in courses if course.get("course_id")}
    queries = build_retrieval_queries(
        original_query,
        target_course=student_profile.get("target_course"),
        target_course_name=student_profile.get("target_course_name"),
        target_program=student_profile.get("target_program_name") or student_profile.get("target_program"),
    )

    if intent == "prerequisite_path" and student_profile.get("target_course"):
        for course_id in _collect_dependency_course_ids(student_profile["target_course"], course_by_id):
            queries.append(course_id)
            course = course_by_id.get(course_id)
            if course and course.get("course_title"):
                queries.append(str(course.get("course_title")))

    if intent == "semester_planning" and student_profile.get("target_program"):
        for course_id in _planning_seed_course_ids(program, student_profile.get("completed_courses", []), course_by_id):
            queries.append(course_id)
            course = course_by_id.get(course_id)
            if course and course.get("course_title"):
                queries.append(str(course.get("course_title")))

    seen: set[str] = set()
    ordered: list[str] = []
    for query in queries:
        normalized = " ".join(str(query).split())
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(normalized)
    return ordered


def _collect_dependency_course_ids(course_id: str, course_by_id: dict[str, dict], visited: set[str] | None = None) -> list[str]:
    if visited is None:
        visited = set()
    if course_id in visited:
        return []
    visited.add(course_id)

    course = course_by_id.get(course_id)
    if not course:
        return []

    direct_dependencies = _collect_direct_course_ids(course.get("parsed_prereq"))
    direct_dependencies.sort(
        key=lambda dependency_id: (
            0 if _collect_direct_course_ids((course_by_id.get(dependency_id) or {}).get("parsed_prereq")) else 1,
            dependency_id,
        )
    )

    ordered: list[str] = []
    for dependency_id in direct_dependencies:
        for nested_id in _collect_dependency_course_ids(dependency_id, course_by_id, visited):
            if nested_id not in ordered:
                ordered.append(nested_id)
        if dependency_id not in ordered:
            ordered.append(dependency_id)
    return ordered


def _collect_direct_course_ids(node: dict | None) -> list[str]:
    if not isinstance(node, dict):
        return []

    node_type = str(node.get("type") or "")
    if node_type == "COURSE":
        course_id = str(node.get("course") or "").strip()
        return [course_id] if course_id else []
    if node_type in {"AND", "OR"}:
        ordered: list[str] = []
        for child in node.get("conditions", []):
            for course_id in _collect_direct_course_ids(child):
                if course_id not in ordered:
                    ordered.append(course_id)
        return ordered
    return []


def _planning_seed_course_ids(
    program: dict,
    completed_courses: list[str],
    course_by_id: dict[str, dict],
) -> list[str]:
    completed = set(completed_courses)
    candidates = [
        str(course_id)
        for course_id in list(program.get("core_courses", [])) + list(program.get("electives", []))
        if course_id not in completed
    ]
    candidates.sort(key=lambda course_id: _planning_priority_rank(course_by_id.get(course_id)))

    seeds: list[str] = []
    for course_id in candidates:
        if course_id in completed or course_id in seeds:
            continue
        seeds.append(course_id)
        if len(seeds) >= 3:
            break
    return seeds


def _build_priority_course_ids(
    intent: str,
    student_profile: dict,
    courses: list[dict],
    program: dict,
) -> list[str]:
    course_by_id = {str(course.get("course_id")): course for course in courses if course.get("course_id")}
    if intent == "prerequisite_path" and student_profile.get("target_course"):
        return _collect_dependency_course_ids(student_profile["target_course"], course_by_id)
    if intent == "semester_planning" and student_profile.get("target_program"):
        return _planning_seed_course_ids(program, student_profile.get("completed_courses", []), course_by_id)
    return []


def _planning_priority_rank(course: dict | None) -> tuple[int, str]:
    if not course:
        return (3, "")
    prereq_text = " ".join(str(course.get("prerequisites") or "None").split()).lower()
    if prereq_text == "none":
        return (0, str(course.get("course_id") or ""))
    if course.get("parsed_prereq") is not None:
        return (1, str(course.get("course_id") or ""))
    return (2, str(course.get("course_id") or ""))


def _build_retrieval_filters(intent: str, student_profile: dict) -> dict[str, str]:
    if intent in {"prerequisite_check", "unsupported_catalog_question"} and student_profile.get("target_course"):
        return {"course_id": str(student_profile["target_course"])}
    if intent == "requirement_lookup" and student_profile.get("target_program") and not student_profile.get("target_course"):
        return {"program_id": str(student_profile["target_program"])}
    return {}
