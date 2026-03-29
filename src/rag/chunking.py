"""Record-level chunking for the Pure RAG catalog.

This project intentionally uses one structured JSON record as one chunk.
Chunk size is therefore "one full record" and chunk overlap is always zero.
No recursive text splitter is used in this module by design.
"""

from __future__ import annotations

import json
from pathlib import Path

from langchain_core.documents import Document

from src.utils.constants import (
    COURSE_CCO_URL_TEMPLATE,
    DEFAULT_COURSES_PATH,
    DEFAULT_POLICIES_PATH,
    DEFAULT_PROGRAM_PATH,
)


def load_catalog_records(
    courses_path: Path = DEFAULT_COURSES_PATH,
    program_path: Path = DEFAULT_PROGRAM_PATH,
    policies_path: Path = DEFAULT_POLICIES_PATH,
) -> tuple[list[dict], dict, list[dict]]:
    courses = _load_json(courses_path)
    program = _load_json(program_path)
    policies = _load_json(policies_path)

    if not isinstance(courses, list):
        raise ValueError(f"Expected a list of course records in {courses_path}")
    if not isinstance(program, dict):
        raise ValueError(f"Expected a program record in {program_path}")
    if not isinstance(policies, list):
        raise ValueError(f"Expected a list of policy records in {policies_path}")

    return courses, program, policies


def build_record_documents(courses: list[dict], program: dict, policies: list[dict]) -> list[Document]:
    """Build one LangChain document per catalog record."""
    documents: list[Document] = []

    for course in courses:
        course_id = str(course.get("course_id") or "").strip()
        if not course_id:
            continue
        chunk_id = f"course_{course_id}"
        documents.append(
            Document(
                page_content=_build_course_text(course),
                metadata=_build_metadata(
                    chunk_id=chunk_id,
                    record_type=str(course.get("type") or "course"),
                    entity_id=course_id,
                    title=str(course.get("course_title") or course_id),
                    source_url=_course_source_url(course_id, course.get("source_url")),
                    accessed_date=course.get("accessed_date"),
                    extra={"course_id": course_id},
                ),
            )
        )

    program_id = str(program.get("program_id") or "").strip()
    if program_id:
        documents.append(
            Document(
                page_content=_build_program_text(program),
                metadata=_build_metadata(
                    chunk_id=f"program_{program_id}",
                    record_type=str(program.get("type") or "program_requirement"),
                    entity_id=program_id,
                    title=str(program.get("program_name") or program_id),
                    source_url=program.get("source_url"),
                    accessed_date=program.get("accessed_date"),
                    extra={"program_id": program_id},
                ),
            )
        )

    for policy in policies:
        policy_id = str(policy.get("policy_id") or "").strip()
        if not policy_id:
            continue
        documents.append(
            Document(
                page_content=_build_policy_text(policy),
                metadata=_build_metadata(
                    chunk_id=f"policy_{policy_id}",
                    record_type=str(policy.get("type") or "academic_policy"),
                    entity_id=policy_id,
                    title=str(policy.get("policy_name") or policy_id),
                    source_url=policy.get("source_url"),
                    accessed_date=policy.get("accessed_date"),
                    extra={"policy_id": policy_id},
                ),
            )
        )

    return documents


def _load_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_metadata(
    *,
    chunk_id: str,
    record_type: str,
    entity_id: str,
    title: str,
    source_url: object,
    accessed_date: object,
    extra: dict[str, str],
) -> dict[str, str]:
    metadata: dict[str, str] = {
        "chunk_id": chunk_id,
        "record_type": record_type,
        "entity_id": entity_id,
        "title": title,
        "source_url": str(source_url or ""),
        "accessed_date": str(accessed_date or ""),
    }
    metadata.update(extra)
    return metadata


def _build_course_text(course: dict) -> str:
    parts = [
        f"Record Type: {course.get('type') or 'course'}",
        f"Course ID: {course.get('course_id') or 'Unknown'}",
        f"Course Title: {course.get('course_title') or 'Unknown'}",
        f"Description: {course.get('description') or 'Not provided.'}",
        f"Prerequisites: {course.get('prerequisites') or 'None'}",
        f"Corequisites: {course.get('corequisites') or 'None'}",
        f"Credits: {course.get('credits') or 'Unknown'}",
    ]
    if course.get("parsed_prereq") is not None:
        parts.append(
            "Parsed prerequisite structure: "
            + json.dumps(course["parsed_prereq"], sort_keys=True, ensure_ascii=True)
        )
    if course.get("notes"):
        parts.append(f"Notes: {course['notes']}")
    return "\n".join(parts)


def _course_source_url(course_id: str, fallback_url: object) -> str:
    normalized_course_id = " ".join(str(course_id or "").split()).upper()
    if normalized_course_id:
        return COURSE_CCO_URL_TEMPLATE.format(course_id=normalized_course_id)
    return str(fallback_url or "")


def _build_program_text(program: dict) -> str:
    parts = [
        f"Record Type: {program.get('type') or 'program_requirement'}",
        f"Program ID: {program.get('program_id') or 'Unknown'}",
        f"Program Name: {program.get('program_name') or 'Unknown'}",
        f"Total Credits Required: {program.get('total_credits_required') or 'Unknown'}",
        f"Core Courses: {', '.join(program.get('core_courses', [])) or 'None'}",
        f"Electives: {', '.join(program.get('electives', [])) or 'None'}",
        f"General Education: {_stringify_general_education(program.get('general_education', []))}",
        f"Capstone: {program.get('capstone') or 'None'}",
        f"Rules: {'; '.join(program.get('rules', [])) or 'None'}",
    ]
    return "\n".join(parts)


def _build_policy_text(policy: dict) -> str:
    return "\n".join(
        [
            f"Record Type: {policy.get('type') or 'academic_policy'}",
            f"Policy ID: {policy.get('policy_id') or 'Unknown'}",
            f"Policy Name: {policy.get('policy_name') or 'Unknown'}",
            f"Rules: {'; '.join(policy.get('rules', [])) or 'None'}",
        ]
    )


def _stringify_general_education(items: list[object]) -> str:
    rendered: list[str] = []
    for item in items:
        if isinstance(item, str):
            rendered.append(item)
        elif isinstance(item, dict) and item.get("type") == "OR":
            rendered.append(" OR ".join(str(option) for option in item.get("options", [])))
        else:
            rendered.append(str(item))
    return ", ".join(rendered) or "None"
