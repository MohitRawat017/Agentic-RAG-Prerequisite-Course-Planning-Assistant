import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

from src.ingestion.constants import ACCESSED_DATE, GROQ_PROMPT_FILE, SOURCE_URL

try:
    from langchain_groq import ChatGroq
except Exception:
    ChatGroq = None


class GroqCourseExtractor:
    def __init__(self, prompt_path: Path = GROQ_PROMPT_FILE) -> None:
        load_dotenv()
        self.prompt_text = prompt_path.read_text(encoding="utf-8").strip()
        self.api_key = os.getenv("GROQ_API_KEY")
        self.enabled = bool(self.api_key and ChatGroq is not None)
        self.client = None

        if self.enabled:
            self.client = ChatGroq(
                api_key=self.api_key,
                model="llama-3.3-70b-versatile",
                temperature=0,
            )

    def extract(self, clean_text: str) -> dict | None:
        if not self.enabled or self.client is None:
            return None

        prompt = self.prompt_text.replace("{{PASTE CLEANED TEXT HERE}}", clean_text)
        response = self.client.invoke(prompt)
        content = response.content
        if isinstance(content, list):
            content = "".join(
                item.get("text", "") if isinstance(item, dict) else str(item)
                for item in content
            )

        json_text = _extract_json_text(str(content))
        return json.loads(json_text)


def build_course_json(extracted_fields: dict, clean_text: str, llm_extractor: GroqCourseExtractor | None = None) -> dict:
    merged = dict(extracted_fields)
    required_fields = ("course_id", "course_title", "description", "credits")
    needs_llm = any(merged.get(field) in (None, "") for field in required_fields)

    if needs_llm and llm_extractor is not None:
        llm_result = llm_extractor.extract(clean_text) or {}
        for key in ("course_id", "course_title", "description", "prerequisites", "corequisites", "credits", "notes"):
            if merged.get(key) in (None, "") and llm_result.get(key) not in ("",):
                merged[key] = llm_result.get(key)

    merged["type"] = "course"
    merged["source_url"] = SOURCE_URL
    merged["accessed_date"] = ACCESSED_DATE
    merged["notes"] = None if merged.get("notes") in ("", None) else merged["notes"]

    return validate_course_json(merged)


def validate_course_json(course_obj: dict) -> dict:
    validated = {
        "type": "course",
        "course_id": _normalize_course_id(course_obj.get("course_id")),
        "course_title": _empty_to_none(course_obj.get("course_title")),
        "description": _empty_to_none(course_obj.get("description")),
        "prerequisites": _empty_to_none(course_obj.get("prerequisites")),
        "corequisites": _empty_to_none(course_obj.get("corequisites")),
        "credits": _normalize_credits(course_obj.get("credits")),
        "notes": _empty_to_none(course_obj.get("notes")),
        "source_url": SOURCE_URL,
        "accessed_date": ACCESSED_DATE,
    }

    if validated["course_id"] is None or validated["course_title"] is None:
        raise ValueError("Missing required course header fields")

    return validated


def _extract_json_text(text: str) -> str:
    fenced_match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced_match:
        return fenced_match.group(1)

    raw_match = re.search(r"(\{.*\})", text, re.DOTALL)
    if raw_match:
        return raw_match.group(1)

    raise ValueError("Groq response did not contain JSON")


def _normalize_course_id(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", "", str(value)).upper()
    return cleaned or None


def _normalize_credits(value: str | None) -> str | None:
    if value is None:
        return None
    match = re.search(r"\d+(?:\.\d+)?", str(value))
    return match.group(0) if match else None


def _empty_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None
