import json
from pathlib import Path

from src.ingestion.document_processor import extract_course_fields, extract_course_text
from src.ingestion.metadata_extractor import build_course_json
from src.ingestion.pdf_parser import parse_pdf


def test_extract_course_fields_from_comp2145_text() -> None:
    sample_text = """
    South Central College
    COMP 2145  Web Programming
    Description
    This course teaches you one of the popular server-side programming languages so that you can design and build secure web applications.
    In this class, you will learn the principles of the client-server architecture and protocols that govern the network communication and data transfer.
    (Prerequisites: COMP 1130 with a C [2.0] or higher, and COMP 1140 with a C [2.0], OR higher OR instructor permission.)
    It is strongly recommended that you have a minimum typing speed of at least 35 wpm.
    Total Credits
    4
    Pre/Corequisites
    Prerequisite
    C (2.0) or better in COMP1140
    Prerequisite
    C (2.0) or better in COMP1130
    OR Instructor permission
    Institutional Core Competencies
    """

    clean_text = extract_course_text(sample_text)
    fields = extract_course_fields(clean_text)

    assert fields["course_id"] == "COMP2145"
    assert fields["course_title"] == "Web Programming"
    assert fields["credits"] == "4"
    assert fields["description"] is not None
    assert "strongly recommended" not in fields["description"].lower()
    assert fields["prerequisites"] == "(COMP1140 AND COMP1130) WITH grade C or better OR instructor permission"


def test_parse_pdf_falls_back_to_pymupdf(monkeypatch) -> None:
    monkeypatch.delenv("LLAMA_CLOUD_API_KEY", raising=False)
    pdf_path = Path("data/Courses/COMP1120_cco_2026.pdf")

    text, parser_used = parse_pdf(pdf_path)

    assert parser_used == "pymupdf"
    assert "Foundations of Computing" in text


def test_build_course_json_normalizes_required_fields() -> None:
    course = build_course_json(
        {
            "course_id": "COMP 1130",
            "course_title": "Programming Fundamentals",
            "description": "Teaches students how to design and develop small programs.",
            "prerequisites": "COMP1120",
            "corequisites": "",
            "credits": "4 credits",
            "notes": "",
        },
        clean_text="",
        llm_extractor=None,
    )

    assert course["course_id"] == "COMP1130"
    assert course["credits"] == "4"
    assert course["corequisites"] is None


def test_requisite_noise_none_becomes_null() -> None:
    sample_text = """
    COMP 2145 Web Programming
    Description
    Example description.
    Total Credits
    4
    Pre/Corequisites
    Corequisite
    s: None
    Institutional Core Competencies
    """

    fields = extract_course_fields(extract_course_text(sample_text))
    assert fields["corequisites"] is None


def test_course_header_uses_real_header_not_prerequisite_line() -> None:
    sample_text = """
    Random intro text
    READ 0080 College Reading
    Description
    Example description.
    (Prerequisites: READ 0090 with a grade of C or higher.)
    Total Credits
    4
    """

    fields = extract_course_fields(extract_course_text(sample_text))
    assert fields["course_id"] == "READ0080"
    assert fields["course_title"] == "College Reading"


def test_inline_prerequisites_standardize_accuplacer_and_course_codes() -> None:
    sample_text = """
    COMM 100 Introduction to Human Communication
    Description
    Example description.
    (Prerequisites: Accuplacer Reading score >= 78 or READ 0080 and READ 0090 with a grade of C or higher)
    Total Credits
    3
    """

    fields = extract_course_fields(extract_course_text(sample_text))
    assert fields["prerequisites"] == "ACCUPLACER_READING >= 78 OR (READ0080 AND READ0090) WITH grade C or better"


def test_sample_pipeline_output_is_json_shape(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("LLAMA_CLOUD_API_KEY", raising=False)
    pdf_path = Path("data/Courses/COMP1130_cco_2026.pdf")
    raw_text, _ = parse_pdf(pdf_path)
    clean_text = extract_course_text(raw_text)
    course = build_course_json(extract_course_fields(clean_text), clean_text, llm_extractor=None)

    output_path = tmp_path / "sample.json"
    output_path.write_text(json.dumps([course], indent=2), encoding="utf-8")

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved[0]["type"] == "course"
    assert saved[0]["course_id"] == "COMP1130"
