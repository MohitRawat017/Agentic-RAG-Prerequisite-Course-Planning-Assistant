from __future__ import annotations

import json

from src.graph.state import GraphState
from src.planning.constants import DEFAULT_COURSE_FILE, DEFAULT_POLICY_FILE, DEFAULT_PROGRAM_FILE
from src.planning.intake import parse_planning_request
from src.planning.loader import load_planning_assets


def intake_node(state: GraphState) -> GraphState:
    payload = _load_payload(state.get("request_file"), state.get("request_json"), state.get("request_payload"))
    request = parse_planning_request(state.get("query"), payload)
    courses, program, policies = load_planning_assets(
        state.get("courses_path") or DEFAULT_COURSE_FILE,
        state.get("program_path") or DEFAULT_PROGRAM_FILE,
        state.get("policies_path") or DEFAULT_POLICY_FILE,
    )
    return {
        **state,
        "request_payload": payload,
        "request": request,
        "courses": courses,
        "program": program,
        "policies": policies,
        "courses_by_id": {course["course_id"]: course for course in courses},
    }


def _load_payload(request_file, request_json: str | None, request_payload: dict | None) -> dict | None:
    if request_payload is not None:
        return request_payload
    if request_file is not None:
        return json.loads(request_file.read_text(encoding="utf-8"))
    if request_json is not None:
        return json.loads(request_json)
    return None
