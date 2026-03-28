import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from src.ingestion.constants import (
    DEFAULT_COURSE_DIR,
    DEFAULT_OUTPUT_FILE,
    DEFAULT_REPORT_FILE,
    PREFERRED_SAMPLE_FILES,
)
from src.ingestion.document_processor import extract_course_fields, extract_course_text
from src.ingestion.metadata_extractor import GroqCourseExtractor, build_course_json
from src.ingestion.pdf_parser import parse_pdf
from src.ingestion.report import write_ingestion_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 2 course ingestion pipeline")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_COURSE_DIR,
        help="Directory containing course PDFs",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_FILE,
        help="Path to save the extracted course JSON",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT_FILE,
        help="Path to save the ingestion report",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=3,
        help="Number of PDFs to process. Use 0 to process all PDFs.",
    )
    return parser.parse_args()


def select_course_pdfs(input_dir: Path, sample_limit: int) -> list[Path]:
    pdfs = sorted(input_dir.glob("*.pdf"))
    if sample_limit == 0:
        return pdfs

    preferred_map = {path.name: path for path in pdfs}
    selected: list[Path] = []

    for filename in PREFERRED_SAMPLE_FILES:
        path = preferred_map.get(filename)
        if path is not None:
            selected.append(path)

    for path in pdfs:
        if path not in selected:
            selected.append(path)
        if len(selected) >= sample_limit:
            break

    return selected[:sample_limit]


def main() -> None:
    load_dotenv()
    args = parse_args()

    course_paths = select_course_pdfs(args.input_dir, args.sample_limit)
    if not course_paths:
        raise FileNotFoundError(f"No course PDFs found in {args.input_dir}")

    llm_extractor = GroqCourseExtractor()
    extracted_courses: list[dict] = []
    report_rows: list[dict] = []

    for pdf_path in course_paths:
        try:
            raw_text, parser_used = parse_pdf(pdf_path)
            clean_text = extract_course_text(raw_text)
            extracted_fields = extract_course_fields(clean_text)
            course_json = build_course_json(extracted_fields, clean_text, llm_extractor)
            extracted_courses.append(course_json)
            report_rows.append(
                {
                    "file_name": pdf_path.name,
                    "status": "success",
                    "parser_used": parser_used,
                    "course_id": course_json["course_id"],
                    "missing_fields": [
                        key
                        for key in ("course_id", "course_title", "description", "prerequisites", "credits")
                        if course_json.get(key) is None
                    ],
                }
            )
        except Exception as exc:
            report_rows.append(
                {
                    "file_name": pdf_path.name,
                    "status": "failed",
                    "parser_used": "unknown",
                    "course_id": None,
                    "missing_fields": [],
                    "error": str(exc),
                }
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(extracted_courses, handle, indent=2, ensure_ascii=False)

    write_ingestion_report(report_rows, args.report, extracted_courses)

    success_count = sum(row["status"] == "success" for row in report_rows)
    print(f"Processed {len(course_paths)} PDFs")
    print(f"Successful extractions: {success_count}")
    print(f"Saved JSON to: {args.output}")
    print(f"Saved report to: {args.report}")


if __name__ == "__main__":
    main()
