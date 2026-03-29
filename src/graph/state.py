from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from src.utils.constants import DEFAULT_COURSES_PATH, DEFAULT_POLICIES_PATH, DEFAULT_PROGRAM_PATH


class GraphState(TypedDict, total=False):
    query: str
    rebuild_index: bool
    courses_path: Path
    program_path: Path
    policies_path: Path
    intent: str
    student_profile: dict[str, Any]
    missing_fields: list[str]
    critical_missing_fields: list[str]
    clarifying_questions: list[str]
    context_assumptions: list[str]
    retrieval_queries: list[str]
    retrieval_filters: dict[str, str]
    priority_course_ids: list[str]
    retrieved_chunks: list[dict[str, Any]]
    retrieved_chunk_ids: list[str]
    planner_output: dict[str, Any]
    verified_output: dict[str, Any]
    final_response: str
    skip_to_formatter: bool
    courses: list[dict[str, Any]]
    program: dict[str, Any]
    policies: list[dict[str, Any]]


def build_initial_state(query: str, rebuild_index: bool = False) -> GraphState:
    return GraphState(
        query=query,
        rebuild_index=rebuild_index,
        courses_path=DEFAULT_COURSES_PATH,
        program_path=DEFAULT_PROGRAM_PATH,
        policies_path=DEFAULT_POLICIES_PATH,
    )
