from pathlib import Path


def write_ingestion_report(rows: list[dict], output_path: Path, extracted_courses: list[dict]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    success_count = sum(row["status"] == "success" for row in rows)
    failure_count = len(rows) - success_count

    lines = [
        "# Phase 2 Ingestion Report",
        "",
        f"- PDFs processed: {len(rows)}",
        f"- Successful extractions: {success_count}",
        f"- Failed extractions: {failure_count}",
        f"- Output records: {len(extracted_courses)}",
        "",
        "## Per File Results",
        "",
    ]

    for row in rows:
        lines.append(f"### {row['file_name']}")
        lines.append(f"- Status: {row['status']}")
        lines.append(f"- Parser used: {row['parser_used']}")
        lines.append(f"- Course ID: {row.get('course_id')}")
        if row.get("missing_fields"):
            lines.append(f"- Missing fields: {', '.join(row['missing_fields'])}")
        else:
            lines.append("- Missing fields: none")
        if row.get("error"):
            lines.append(f"- Error: {row['error']}")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
