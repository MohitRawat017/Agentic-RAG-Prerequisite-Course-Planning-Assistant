import re

from src.ingestion.constants import (
    COURSE_CODE_RE,
    COURSE_HEADER_RE,
    CREDITS_RE,
    DESCRIPTION_BLOCK_RE,
    GRADE_RE,
    HEADER_PATTERNS,
    INLINE_PREREQ_RE,
    STOP_MARKERS,
)


def extract_course_text(raw_text: str) -> str:
    text = raw_text.replace("\r", "\n")
    for pattern in HEADER_PATTERNS:
        text = pattern.sub("", text)

    lines: list[str] = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        if any(marker.lower() in line.lower() for marker in STOP_MARKERS):
            break
        lines.append(line)

    start_index = _find_course_start_index(lines)
    if start_index is not None:
        lines = lines[start_index:]

    return "\n".join(lines).strip()


def extract_course_fields(clean_text: str) -> dict:
    description_block = _extract_description_block(clean_text)
    inline_prereq = _extract_inline_prerequisite(description_block)
    prerequisite_block = _extract_precorequisite_block(clean_text)

    return {
        "type": "course",
        "course_id": _extract_course_id(clean_text),
        "course_title": _extract_course_title(clean_text),
        "description": _extract_description(description_block),
        "prerequisites": _extract_requisites(prerequisite_block, "Prerequisite") or _normalize_inline_requisite_text(inline_prereq),
        "corequisites": _extract_requisites(prerequisite_block, "Corequisite"),
        "credits": _extract_credits(clean_text),
        "notes": None,
    }


def _extract_course_id(clean_text: str) -> str | None:
    match = _extract_course_header_match(clean_text)
    if not match:
        return None
    return f"{match.group(1).upper()}{match.group(2)}"


def _extract_course_title(clean_text: str) -> str | None:
    match = _extract_course_header_match(clean_text)
    if not match:
        return None
    title = match.group(3).strip()
    return title if title else None


def _extract_description_block(clean_text: str) -> str:
    match = DESCRIPTION_BLOCK_RE.search(clean_text)
    if match:
        return match.group(1).strip()
    return ""


def _extract_inline_prerequisite(description_block: str) -> str | None:
    match = INLINE_PREREQ_RE.search(description_block)
    if not match:
        return None
    return _normalize_space(match.group(1))


def _extract_description(description_block: str) -> str | None:
    if not description_block:
        return None

    text = INLINE_PREREQ_RE.sub("", description_block)
    sentences = _split_sentences(_normalize_space(text))
    kept = [sentence for sentence in sentences if not sentence.lower().startswith("it is strongly recommended")]
    if not kept:
        return None
    return " ".join(kept[:3]).strip()


def _extract_precorequisite_block(clean_text: str) -> str:
    match = re.search(r"Pre/Corequisites\s+(.*)", clean_text, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else ""


def _extract_requisites(block: str, label: str) -> str | None:
    if not block:
        return None

    lines = [line.strip() for line in block.splitlines() if line.strip()]
    segments: list[tuple[str | None, str | None]] = []
    seen_label = False
    index = 0

    while index < len(lines):
        line = lines[index]
        if line.lower().startswith(label.lower()):
            seen_label = True
            remainder = line[len(label) :].strip(" :\t")
            if remainder:
                normalized = _normalize_requisite_item(remainder)
                if normalized is None:
                    return None
                connector = None if not segments else "AND"
                segments.append((connector, normalized))
            elif index + 1 < len(lines):
                candidate = lines[index + 1]
                if candidate.upper().startswith(("OR ", "AND ")):
                    index += 1
                    continue
                normalized = _normalize_requisite_item(candidate)
                if normalized is None:
                    return None
                connector = None if not segments else "AND"
                segments.append((connector, normalized))
                index += 1
        elif seen_label and line.upper().startswith("OR "):
            normalized = _normalize_requisite_item(line[3:].strip())
            if normalized is not None:
                segments.append(("OR", normalized))
        elif seen_label and line.upper().startswith("AND "):
            normalized = _normalize_requisite_item(line[4:].strip())
            if normalized is not None:
                segments.append(("AND", normalized))
        index += 1

    if not segments:
        if label.lower() == "prerequisite":
            fallback_text = " ".join(
                line for line in lines if not line.lower().startswith(("corequisite", "prerequisite"))
            ).strip()
            return _normalize_inline_requisite_text(fallback_text) if fallback_text else None
        return None

    groups: list[list[str]] = []
    current_group: list[str] = []

    for connector, item in segments:
        if item is None:
            continue
        if connector in (None, "AND"):
            current_group.append(item)
        elif connector == "OR":
            if current_group:
                groups.append(current_group)
            current_group = [item]

    if current_group:
        groups.append(current_group)

    rendered_groups = []
    for group in groups:
        rendered = _render_requisite_group(group)
        if len(groups) > 1 and len(group) > 1 and " WITH grade " not in rendered:
            rendered = f"({rendered})"
        rendered_groups.append(rendered)

    if not rendered_groups:
        return None
    return _standardize_requisite_output(" OR ".join(rendered_groups))


def _normalize_inline_requisite_text(text: str | None) -> str | None:
    if not text:
        return None

    cleaned = _clean_requisite_noise(text)
    if _is_null_requisite(cleaned):
        return None

    course_codes = [f"{match.group(1)}{match.group(2)}" for match in COURSE_CODE_RE.finditer(cleaned)]
    if not course_codes:
        normalized = re.sub(r"\band\b", "AND", cleaned, flags=re.IGNORECASE)
        normalized = re.sub(r"\bor\b", "OR", normalized, flags=re.IGNORECASE)
        return _standardize_requisite_output(normalized)

    normalized = cleaned
    for match, course_code in zip(COURSE_CODE_RE.finditer(cleaned), course_codes):
        normalized = normalized.replace(match.group(0), course_code, 1)
    normalized = re.sub(r"\band\b", "AND", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bor\b", "OR", normalized, flags=re.IGNORECASE)
    normalized = normalized.replace("[", "(").replace("]", ")")
    return _standardize_requisite_output(normalized)


def _normalize_requisite_item(text: str) -> str | None:
    cleaned = _clean_requisite_noise(text).strip(" .;:")
    if _is_null_requisite(cleaned):
        return None
    if "instructor permission" in cleaned.lower():
        return "instructor permission"

    course_match = COURSE_CODE_RE.search(cleaned)
    if not course_match:
        return cleaned

    course_code = f"{course_match.group(1)}{course_match.group(2)}"
    normalized = cleaned.replace("[", "(").replace("]", ")")
    grade_match = GRADE_RE.search(normalized)

    if grade_match:
        grade_text = _normalize_grade_text(grade_match.group(1))
        return f"{course_code}, grade {grade_text}"

    return course_code


def _extract_credits(clean_text: str) -> str | None:
    match = CREDITS_RE.search(clean_text)
    if not match:
        return None
    return match.group(1)


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _split_sentences(text: str) -> list[str]:
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [part.strip() for part in parts if part.strip()]


def _render_requisite_group(group: list[str]) -> str:
    parsed_items = [_split_course_and_grade(item) for item in group]
    grades = [grade for _, grade in parsed_items if grade is not None]

    if len(parsed_items) == len(group) and len(grades) == len(group) and len(set(grades)) == 1:
        course_codes = [course_code for course_code, _ in parsed_items]
        joined_courses = " AND ".join(course_codes)
        if len(course_codes) > 1:
            joined_courses = f"({joined_courses})"
        return f"{joined_courses} WITH grade {grades[0]}"

    return " AND ".join(group)


def _split_course_and_grade(item: str) -> tuple[str, str | None]:
    match = re.fullmatch(r"([A-Z]{3,4}\d{3,4}), grade (.+)", item)
    if not match:
        return item, None
    return match.group(1), match.group(2)


def _normalize_grade_text(text: str) -> str:
    cleaned = _normalize_space(text)
    cleaned = re.sub(r"\s*[\[(]\s*\d\.\d\s*[\])]\s*", " ", cleaned)
    cleaned = re.sub(r"\bor higher\b", "or better", cleaned, flags=re.IGNORECASE)
    cleaned = _normalize_space(cleaned)
    return cleaned


def _extract_course_header_match(clean_text: str) -> re.Match[str] | None:
    lines = [line.strip() for line in clean_text.splitlines() if line.strip()]
    for line in lines[:12]:
        match = COURSE_HEADER_RE.fullmatch(line)
        if match and _looks_like_course_title(match.group(3)):
            return match
    return None


def _find_course_start_index(lines: list[str]) -> int | None:
    for index, line in enumerate(lines[:12]):
        match = COURSE_HEADER_RE.fullmatch(line)
        if match and _looks_like_course_title(match.group(3)):
            return index
    return None


def _looks_like_course_title(title: str) -> bool:
    lowered = title.strip().lower()
    bad_starts = (
        "and ",
        "or ",
        "with ",
        "grade ",
        "prerequisite",
        "corequisite",
    )
    bad_contains = (
        "grade of",
        "grade c",
        "instructor permission",
    )
    if lowered.startswith(bad_starts):
        return False
    return not any(token in lowered for token in bad_contains)


def _clean_requisite_noise(text: str) -> str:
    cleaned = _normalize_space(text)
    cleaned = re.sub(r"^[a-z]{1,2}:\s*", "", cleaned, flags=re.IGNORECASE)
    return cleaned


def _is_null_requisite(text: str) -> bool:
    lowered = _normalize_space(text).lower().strip(" .;:")
    return lowered in {"none", "s: none", "n/a", "na", "null"}


def _standardize_requisite_output(text: str) -> str:
    normalized = _normalize_space(text)
    normalized = re.sub(r"\bStudent must obtain\b", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bMust have\b", "", normalized, flags=re.IGNORECASE)
    normalized = _compact_course_codes(normalized)
    normalized = _standardize_accuplacer_reading(normalized)
    normalized = re.sub(r"\bcompletion of\s+([A-Z]{3,4}\d{3,4})\b", r"\1", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bcomplete\s+([A-Z]{3,4}\d{3,4})\b", r"\1", normalized, flags=re.IGNORECASE)
    normalized = _standardize_course_grade_phrases(normalized)
    normalized = re.sub(r"\ba\s+(?=ACCUPLACER_)", "", normalized, flags=re.IGNORECASE)
    normalized = normalized.rstrip(".")
    return _normalize_space(normalized)


def _compact_course_codes(text: str) -> str:
    return COURSE_CODE_RE.sub(lambda match: f"{match.group(1).upper()}{match.group(2)}", text)


def _standardize_accuplacer_reading(text: str) -> str:
    patterns = (
        r"Accuplacer Reading score\s*>=\s*(\d+)",
        r"Accuplacer Reading Score of (\d+)\s+OR\s+above",
        r"Reading Comprehension Score of (\d+)",
        r"score of (\d+)\s+OR\s+above in reading comprehension on the Accuplacer(?: test)?",
        r"a score of (\d+)\s+OR\s+above in reading comprehension on the Accuplacer(?: test)?",
        r"score of (\d+)\s+or\s+higher on the Reading portion of the Accuplacer test",
    )

    normalized = text
    for pattern in patterns:
        normalized = re.sub(
            pattern,
            lambda match: f"ACCUPLACER_READING >= {match.group(1)}",
            normalized,
            flags=re.IGNORECASE,
        )
    normalized = re.sub(
        r"Accuplacer\s+ACCUPLACER_READING\s*>=\s*(\d+)\s+OR\s+above",
        lambda match: f"ACCUPLACER_READING >= {match.group(1)}",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"ACCUPLACER_READING\s*>=\s*(\d+)\s+OR\s+above",
        lambda match: f"ACCUPLACER_READING >= {match.group(1)}",
        normalized,
        flags=re.IGNORECASE,
    )
    return normalized


def _standardize_course_grade_phrases(text: str) -> str:
    pattern = re.compile(
        r"((?:[A-Z]{3,4}\d{3,4})(?:\s+AND\s+[A-Z]{3,4}\d{3,4})*)\s+with a grade of\s+\"?([A-Z][+-]?)\"?\s+OR\s+(higher|better)",
        re.IGNORECASE,
    )

    def replace(match: re.Match[str]) -> str:
        course_group = match.group(1)
        grade = match.group(2).upper()
        joined_courses = f"({course_group})" if " AND " in course_group else course_group
        return f"{joined_courses} WITH grade {grade} or better"

    return pattern.sub(replace, text)
