import json
from pathlib import Path

from src.planning.constants import DEFAULT_COURSE_FILE, DEFAULT_POLICY_FILE, DEFAULT_PROGRAM_FILE


def load_planning_assets(
    course_path: Path = DEFAULT_COURSE_FILE,
    program_path: Path = DEFAULT_PROGRAM_FILE,
    policy_path: Path = DEFAULT_POLICY_FILE,
) -> tuple[list[dict], dict, list[dict]]:
    courses = json.loads(course_path.read_text(encoding="utf-8"))
    program = json.loads(program_path.read_text(encoding="utf-8"))
    policies = json.loads(policy_path.read_text(encoding="utf-8"))
    return courses, program, policies
