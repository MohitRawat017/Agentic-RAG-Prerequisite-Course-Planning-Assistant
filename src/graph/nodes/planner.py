from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from src.graph.state import GraphState
from src.utils.constants import (
    DEFAULT_FALLBACK_MAX_CREDITS,
    GROQ_PLANNER_MODEL,
    PLANNER_PROMPT_PATH,
    PROJECT_ROOT,
)


class PlannerOutput(BaseModel):
    answer_plan: str
    why: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    clarifying_questions: list[str] = Field(default_factory=list)
    assumptions_not_in_catalog: list[str] = Field(default_factory=list)


def planner_node(state: GraphState) -> GraphState:
    retrieved_chunks = state.get("retrieved_chunks", [])
    if not retrieved_chunks:
        return {
            **state,
            "planner_output": {
                "answer_plan": "I do not have that information in the provided catalog/policies.",
                "why": [],
                "citations": [],
                "clarifying_questions": state.get("clarifying_questions", []),
                "assumptions_not_in_catalog": [
                    "No relevant catalog chunks were retrieved for this request."
                ],
            },
        }

    try:
        structured_llm = _build_planner_llm()
        prompt = _load_prompt()
        payload = {
            "query": state.get("query", ""),
            "intent": state.get("intent", ""),
            "student_profile": state.get("student_profile", {}),
            "missing_fields": state.get("missing_fields", []),
            "clarifying_questions": state.get("clarifying_questions", []),
            "retrieved_chunks": [
                {
                    "chunk_id": item["chunk_id"],
                    "title": item["metadata"].get("title", ""),
                    "record_type": item["metadata"].get("record_type", ""),
                    "source_url": item["metadata"].get("source_url", ""),
                    "text": item["text"],
                }
                for item in retrieved_chunks
            ],
        }

        result = structured_llm.invoke(
            [
                SystemMessage(content=prompt),
                HumanMessage(content=json.dumps(payload, indent=2, ensure_ascii=False)),
            ]
        )
        planner_output = result.model_dump()
    except Exception as exc:
        planner_output = _build_fallback_planner_output(state, str(exc))

    planner_output["clarifying_questions"] = _merge_unique_lists(
        state.get("clarifying_questions", []),
        planner_output.get("clarifying_questions", []),
    )

    return {
        **state,
        "planner_output": planner_output,
    }


def _build_planner_llm():
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is required to use the planner model.")

    llm = ChatGroq(
        model=GROQ_PLANNER_MODEL,
        temperature=0,
        api_key=api_key,
    )
    return llm.with_structured_output(PlannerOutput)


def _load_prompt() -> str:
    return Path(PLANNER_PROMPT_PATH).read_text(encoding="utf-8")


def _merge_unique_lists(*values: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for items in values:
        for item in items:
            normalized = " ".join(str(item).split())
            if not normalized:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            merged.append(normalized)
    return merged


def _build_fallback_planner_output(state: GraphState, error_message: str) -> dict[str, Any]:
    intent = state.get("intent", "")
    assumptions = ["Planner model was unavailable, so a conservative grounded fallback was used."]

    lowered_error = error_message.lower()
    if "quota" in lowered_error or "resource_exhausted" in lowered_error or "rate limit" in lowered_error:
        assumptions.append("Groq planner quota or rate limit was unavailable during this run.")
    elif "groq" in lowered_error:
        assumptions.append("The Groq planner was unavailable during this run.")

    if intent == "prerequisite_check":
        return _fallback_prerequisite_output(state, assumptions)
    if intent == "semester_planning":
        return _fallback_semester_plan_output(state, assumptions)
    if intent == "requirement_lookup":
        return _fallback_requirement_output(state, assumptions)

    return {
        "answer_plan": "I do not have that information in the provided catalog/policies.",
        "why": [],
        "citations": [],
        "clarifying_questions": state.get("clarifying_questions", []),
        "assumptions_not_in_catalog": assumptions,
    }


def _fallback_prerequisite_output(state: GraphState, assumptions: list[str]) -> dict[str, Any]:
    profile = state.get("student_profile", {})
    target_course_id = profile.get("target_course")
    if not target_course_id:
        return {
            "answer_plan": "Need more info to determine the prerequisite check.",
            "why": [],
            "citations": [],
            "clarifying_questions": _merge_unique_lists(
                state.get("clarifying_questions", []),
                ["Which course should I check for prerequisites?"],
            ),
            "assumptions_not_in_catalog": assumptions,
        }

    course_record = _get_course_record(state, target_course_id)
    if not course_record:
        return {
            "answer_plan": "I do not have that information in the provided catalog/policies.",
            "why": [],
            "citations": [],
            "clarifying_questions": state.get("clarifying_questions", []),
            "assumptions_not_in_catalog": assumptions + [f"No structured catalog record was found for {target_course_id}."],
        }

    chunk_id = _find_chunk_id_for_course(state, target_course_id)
    prereq_text = str(course_record.get("prerequisites") or "None")
    why = []
    citations = [chunk_id] if chunk_id else []
    if chunk_id:
        why.append(
            f'The catalog lists the prerequisites for {target_course_id} as "{prereq_text}". [[{chunk_id}]]'
        )

    completed_courses = set(profile.get("completed_courses", []))
    grades = dict(profile.get("grades", {}))
    if not completed_courses:
        return {
            "answer_plan": f"Need more info to determine whether you can take {target_course_id}.",
            "why": why,
            "citations": citations,
            "clarifying_questions": state.get("clarifying_questions", []),
            "assumptions_not_in_catalog": assumptions,
        }

    status = _evaluate_parsed_prereq(course_record.get("parsed_prereq"), completed_courses, grades)
    completed_text = ", ".join(
        f"{course_id} ({grades[course_id]})" if course_id in grades else course_id
        for course_id in profile.get("completed_courses", [])
    )

    if status == "eligible":
        if chunk_id:
            why.append(
                f"Based on the courses and grades you provided ({completed_text}), the listed prerequisite condition is satisfied. [[{chunk_id}]]"
            )
        return {
            "answer_plan": f"Based on the retrieved catalog chunk, you appear eligible to take {target_course_id}.",
            "why": why,
            "citations": citations,
            "clarifying_questions": [],
            "assumptions_not_in_catalog": assumptions,
        }

    if status == "need_more_info":
        if chunk_id:
            why.append(
                f"The catalog includes requirements that cannot be fully verified from the course history or grades you provided ({completed_text}). [[{chunk_id}]]"
            )
        return {
            "answer_plan": f"Need more info to determine whether you can take {target_course_id}.",
            "why": why,
            "citations": citations,
            "clarifying_questions": _merge_unique_lists(
                state.get("clarifying_questions", []),
                ["Do you have instructor permission or any missing prerequisite grades for this course?"],
            ),
            "assumptions_not_in_catalog": assumptions,
        }

    if chunk_id:
        why.append(
            f"Based on the course history you provided ({completed_text}), the listed prerequisite condition is not yet fully met. [[{chunk_id}]]"
        )
    return {
        "answer_plan": f"Based on the retrieved catalog chunk, you do not currently meet the listed prerequisites for {target_course_id}.",
        "why": why,
        "citations": citations,
        "clarifying_questions": [],
        "assumptions_not_in_catalog": assumptions,
    }


def _fallback_requirement_output(state: GraphState, assumptions: list[str]) -> dict[str, Any]:
    profile = state.get("student_profile", {})
    target_course_id = profile.get("target_course")
    target_program_id = profile.get("target_program")

    if target_course_id:
        course_record = _get_course_record(state, target_course_id)
        chunk_id = _find_chunk_id_for_course(state, target_course_id)
        prereq_text = str((course_record or {}).get("prerequisites") or "None")
        why = [
            f'The retrieved catalog chunk for {target_course_id} lists the prerequisites as "{prereq_text}". [[{chunk_id}]]'
        ] if chunk_id else []
        citations = [chunk_id] if chunk_id else []
        return {
            "answer_plan": f"The catalog requirement I found for {target_course_id} is its listed prerequisite rule.",
            "why": why,
            "citations": citations,
            "clarifying_questions": state.get("clarifying_questions", []),
            "assumptions_not_in_catalog": assumptions,
        }

    if target_program_id:
        program = state.get("program", {})
        chunk_id = _find_chunk_id_for_program(state, target_program_id)
        why = []
        citations = [chunk_id] if chunk_id else []
        if chunk_id:
            why.append(
                f"The retrieved program chunk states that {program.get('program_name')} requires {program.get('total_credits_required')} total credits. [[{chunk_id}]]"
            )
            why.append(
                f"The same chunk lists core courses such as {', '.join(program.get('core_courses', []))}. [[{chunk_id}]]"
            )
        return {
            "answer_plan": f"I found the main catalog requirements for {program.get('program_name')}.",
            "why": why,
            "citations": citations,
            "clarifying_questions": state.get("clarifying_questions", []),
            "assumptions_not_in_catalog": assumptions,
        }

    return {
        "answer_plan": "Need more info to determine which catalog requirement you want me to check.",
        "why": [],
        "citations": [],
        "clarifying_questions": _merge_unique_lists(
            state.get("clarifying_questions", []),
            ["Which course or program should I look up?"],
        ),
        "assumptions_not_in_catalog": assumptions,
    }


def _fallback_semester_plan_output(state: GraphState, assumptions: list[str]) -> dict[str, Any]:
    profile = state.get("student_profile", {})
    target_program_id = profile.get("target_program")
    completed_courses = set(profile.get("completed_courses", []))
    if not target_program_id or not completed_courses:
        return {
            "answer_plan": "Need more info to build a semester plan from the catalog.",
            "why": [],
            "citations": [],
            "clarifying_questions": state.get("clarifying_questions", []),
            "assumptions_not_in_catalog": assumptions,
        }

    max_credits = profile.get("max_credits")
    if max_credits is None:
        max_credits = DEFAULT_FALLBACK_MAX_CREDITS
        assumptions.append(
            f"Used the fallback maximum credit load of {DEFAULT_FALLBACK_MAX_CREDITS} because none was provided."
        )

    grades = dict(profile.get("grades", {}))
    course_by_id = {
        str(course.get("course_id")): course
        for course in state.get("courses", [])
        if course.get("course_id")
    }
    retrieved_courses = {
        item["metadata"].get("course_id"): item["chunk_id"]
        for item in state.get("retrieved_chunks", [])
        if item["metadata"].get("course_id")
    }

    program = state.get("program", {})
    program_chunk_id = _find_chunk_id_for_program(state, target_program_id)
    planned_courses: list[str] = []
    planned_credits = 0
    why: list[str] = []
    citations: list[str] = [program_chunk_id] if program_chunk_id else []

    if program_chunk_id:
        why.append(
            f"The retrieved program chunk lists required core courses for {program.get('program_name')}. [[{program_chunk_id}]]"
        )

    for course_id in program.get("core_courses", []) + program.get("electives", []):
        if course_id in completed_courses or course_id in planned_courses:
            continue
        if course_id not in retrieved_courses:
            continue
        course_record = course_by_id.get(course_id)
        if not course_record:
            continue

        status = _evaluate_parsed_prereq(course_record.get("parsed_prereq"), completed_courses, grades)
        if status != "eligible":
            continue

        course_credits = _parse_credits(course_record.get("credits"))
        if planned_courses and planned_credits + course_credits > max_credits:
            continue

        planned_courses.append(course_id)
        planned_credits += course_credits
        chunk_id = retrieved_courses[course_id]
        citations.append(chunk_id)
        prereq_text = str(course_record.get("prerequisites") or "None")
        why.append(
            f'{course_id} lists "Prerequisites: {prereq_text}" in its retrieved course chunk. [[{chunk_id}]]'
        )

    if not planned_courses:
        return {
            "answer_plan": "Need more info to build a grounded semester plan from the retrieved catalog chunks.",
            "why": why,
            "citations": _merge_unique_lists(citations),
            "clarifying_questions": _merge_unique_lists(
                state.get("clarifying_questions", []),
                ["Could you share any additional eligible courses or catalog targets you want prioritized?"],
            ),
            "assumptions_not_in_catalog": assumptions + [
                "The top retrieved chunks did not provide enough eligible course detail for a stronger grounded plan."
            ],
        }

    return {
        "answer_plan": f"Suggested next-term courses: {', '.join(planned_courses)} (about {planned_credits} credits).",
        "why": why,
        "citations": _merge_unique_lists(citations),
        "clarifying_questions": state.get("clarifying_questions", []),
        "assumptions_not_in_catalog": assumptions,
    }


def _evaluate_parsed_prereq(node: dict | None, completed_courses: set[str], grades: dict[str, str]) -> str:
    if not node:
        return "eligible"

    node_type = node.get("type")
    if node_type == "COURSE":
        course_id = str(node.get("course") or "")
        if course_id not in completed_courses:
            return "not_eligible"
        min_grade = node.get("min_grade")
        if not min_grade:
            return "eligible"
        actual_grade = grades.get(course_id)
        if actual_grade is None:
            return "need_more_info"
        return "eligible" if _grade_value(actual_grade) >= _grade_value(str(min_grade)) else "not_eligible"

    if node_type == "AND":
        statuses = [_evaluate_parsed_prereq(child, completed_courses, grades) for child in node.get("conditions", [])]
        if any(status == "not_eligible" for status in statuses):
            return "not_eligible"
        if any(status == "need_more_info" for status in statuses):
            return "need_more_info"
        return "eligible"

    if node_type == "OR":
        statuses = [_evaluate_parsed_prereq(child, completed_courses, grades) for child in node.get("conditions", [])]
        if any(status == "eligible" for status in statuses):
            return "eligible"
        if any(status == "need_more_info" for status in statuses):
            return "need_more_info"
        return "not_eligible"

    if node_type == "EXCEPTION":
        return "need_more_info"

    return "need_more_info"


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
    return ranking.get(grade.upper(), -1)


def _parse_credits(raw_value: object) -> int:
    try:
        return int(str(raw_value))
    except Exception:
        return 0


def _get_course_record(state: GraphState, course_id: str) -> dict | None:
    for course in state.get("courses", []):
        if str(course.get("course_id")) == course_id:
            return course
    return None


def _find_chunk_id_for_course(state: GraphState, course_id: str) -> str | None:
    for chunk in state.get("retrieved_chunks", []):
        if chunk["metadata"].get("course_id") == course_id:
            return chunk["chunk_id"]
    return None


def _find_chunk_id_for_program(state: GraphState, program_id: str) -> str | None:
    for chunk in state.get("retrieved_chunks", []):
        if chunk["metadata"].get("program_id") == program_id:
            return chunk["chunk_id"]
    return None
