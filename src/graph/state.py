from __future__ import annotations

from pathlib import Path
from typing import TypedDict


class GraphState(TypedDict, total=False):
    query: str | None
    request_payload: dict | None
    request_file: Path | None
    request_json: str | None
    courses_path: Path
    program_path: Path
    policies_path: Path
    output_path: Path | None
    rebuild_index: bool
    print_explanation: bool
    request: dict
    courses: list[dict]
    program: dict
    policies: list[dict]
    courses_by_id: dict[str, dict]
    vectorstore: object
    retrieved_chunks: list[dict]
    plan: dict
    verification: dict
    response_text: str
