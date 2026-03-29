import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

from src.planning.constants import DEFAULT_INTENT, DEFAULT_PROGRAM_ID, INTAKE_PROMPT_FILE

try:
    from langchain_groq import ChatGroq
except Exception:
    ChatGroq = None


ABSTAIN_RESPONSE = {
    "intent": "abstain",
    "target_course": None,
    "completed_courses": [],
    "grades": {},
    "assessments": {},
    "max_credits": None,
    "target_program": DEFAULT_PROGRAM_ID,
    "include_general_education": False,
    "query": None,
    "unsupported_query": True,
}

GREETING_RESPONSE = {
    "intent": "greeting",
    "target_course": None,
    "completed_courses": [],
    "grades": {},
    "assessments": {},
    "max_credits": None,
    "target_program": DEFAULT_PROGRAM_ID,
    "include_general_education": False,
    "query": None,
    "greeting_query": True,
}

TARGET_COURSE_PATTERNS = [
    re.compile(r"\bcan\s+i\s+take\s+([A-Za-z]{3,4}\s*\d{3,4})\b", re.IGNORECASE),
    re.compile(r"\bam\s+i\s+eligible\s+for\s+([A-Za-z]{3,4}\s*\d{3,4})\b", re.IGNORECASE),
    re.compile(r"\b(?:to\s+reach|reach)\s+([A-Za-z]{3,4}\s*\d{3,4})\b", re.IGNORECASE),
    re.compile(r"\bwhen\s+is\s+([A-Za-z]{3,4}\s*\d{3,4})\b", re.IGNORECASE),
    re.compile(r"\bwho\s+teaches\s+([A-Za-z]{3,4}\s*\d{3,4})\b", re.IGNORECASE),
    re.compile(r"\b(?:schedule|time)\s+(?:for\s+)?([A-Za-z]{3,4}\s*\d{3,4})\b", re.IGNORECASE),
]


def parse_planning_request(query: str | None, payload: dict | None) -> dict:
    if payload is not None:
        return _normalize_request(payload, query)
    if query is None:
        raise ValueError("Provide either a freeform query or a structured payload")
    if is_greeting_query(query):
        response = dict(GREETING_RESPONSE)
        response["query"] = query
        return response
    if not is_supported_query(query):
        response = dict(ABSTAIN_RESPONSE)
        response["query"] = query
        response["target_course"] = _extract_target_course(query)
        return response
    return _normalize_request(_parse_query_with_llm(query), query)


def _parse_query_with_llm(query: str) -> dict:
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or ChatGroq is None:
        raise RuntimeError("GROQ_API_KEY is required for freeform planning query intake")

    prompt = Path(INTAKE_PROMPT_FILE).read_text(encoding="utf-8").strip().replace("{{USER_QUERY}}", query)
    client = ChatGroq(
        api_key=api_key,
        model="llama-3.3-70b-versatile",
        temperature=0,
    )
    response = client.invoke(prompt)
    content = response.content
    if isinstance(content, list):
        content = "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    return json.loads(_extract_json_text(str(content)))


def _normalize_request(payload: dict, fallback_query: str | None = None) -> dict:
    student = payload.get("student", {}) if isinstance(payload.get("student"), dict) else {}
    raw_query = payload.get("query") or fallback_query
    if raw_query is not None and is_greeting_query(raw_query):
        response = dict(GREETING_RESPONSE)
        response["query"] = raw_query
        return response
    if raw_query is not None and not is_supported_query(raw_query):
        response = dict(ABSTAIN_RESPONSE)
        response["query"] = raw_query
        response["target_course"] = _extract_target_course(raw_query)
        return response
    completed_courses = [
        _normalize_course_code(item)
        for item in payload.get("completed_courses", student.get("completed_courses", []))
    ]
    grades = {
        _normalize_course_code(course_code): _normalize_grade(grade)
        for course_code, grade in payload.get("grades", student.get("grades", {})).items()
        if _normalize_course_code(course_code) is not None and _normalize_grade(grade) is not None
    }
    assessments = {
        _normalize_assessment_name(name): int(value)
        for name, value in payload.get("assessments", student.get("assessments", {})).items()
        if _normalize_assessment_name(name) is not None and _extract_int(value) is not None
        for value in [int(_extract_int(value))]
    }
    target_course = _normalize_course_code(payload.get("target_course")) or _extract_target_course(raw_query)
    intent = str(payload.get("intent") or _infer_intent(raw_query, target_course) or DEFAULT_INTENT)

    return {
        "intent": intent,
        "target_course": target_course,
        "completed_courses": [code for code in completed_courses if code is not None],
        "grades": grades,
        "assessments": assessments,
        "max_credits": _extract_int(payload.get("max_credits")),
        "target_program": str(payload.get("target_program") or DEFAULT_PROGRAM_ID),
        "include_general_education": bool(payload.get("include_general_education", False)),
        "query": raw_query,
    }


def _extract_json_text(text: str) -> str:
    fenced_match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced_match:
        return fenced_match.group(1)
    raw_match = re.search(r"(\{.*\})", text, re.DOTALL)
    if raw_match:
        return raw_match.group(1)
    raise ValueError("Intake response did not contain JSON")


def _normalize_course_code(value: str | None) -> str | None:
    if value is None:
        return None
    match = re.search(r"([A-Za-z]{3,4})\s*(\d{3,4})", str(value))
    if not match:
        return None
    return f"{match.group(1).upper()}{match.group(2)}"


def _normalize_grade(value: str | None) -> str | None:
    if value is None:
        return None
    match = re.search(r"([ABCDF][+-]?)", str(value).upper())
    return match.group(1) if match else None


def _normalize_assessment_name(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", "_", str(value).strip().upper())
    return cleaned or None


def _extract_int(value: object) -> int | None:
    if value is None:
        return None
    match = re.search(r"\d+", str(value))
    return int(match.group(0)) if match else None


def is_supported_query(query: str) -> bool:
    unsupported_keywords = [
        "when",
        "schedule",
        "time",
        "professor",
        "who teaches",
    ]
    lowered = query.lower()
    return not any(keyword in lowered for keyword in unsupported_keywords)


def is_greeting_query(query: str) -> bool:
    lowered = " ".join(query.lower().split())
    greeting_patterns = (
        "hi",
        "hii",
        "hiii",
        "hello",
        "hey",
        "good morning",
        "good afternoon",
        "good evening",
    )
    return lowered in greeting_patterns


def _extract_target_course(query: str | None) -> str | None:
    if query is None:
        return None
    for pattern in TARGET_COURSE_PATTERNS:
        match = pattern.search(query)
        if match:
            return _normalize_course_code(match.group(1))
    return None


def _infer_intent(query: str | None, target_course: str | None) -> str | None:
    lowered = (query or "").lower()
    if target_course is not None and ("can i take" in lowered or "am i eligible" in lowered):
        return "course_eligibility"
    if target_course is not None and "with instructor permission" in lowered:
        return "course_eligibility"
    if "plan" in lowered or "semester" in lowered:
        return "course_planning"
    if target_course is not None:
        return "course_eligibility"
    return None
