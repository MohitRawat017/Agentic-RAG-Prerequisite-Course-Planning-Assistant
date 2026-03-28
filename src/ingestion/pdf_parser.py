import os
from pathlib import Path

import fitz
from dotenv import load_dotenv

from src.ingestion.constants import LLAMAPARSE_PROMPT_FILE

try:
    from llama_parse import LlamaParse
except Exception:
    LlamaParse = None


def _load_prompt(prompt_path: Path) -> str:
    return prompt_path.read_text(encoding="utf-8").strip()


def _parse_with_pymupdf(pdf_path: Path) -> str:
    document = fitz.open(pdf_path)
    try:
        pages = [page.get_text() for page in document]
    finally:
        document.close()
    return "\n".join(pages).strip()


def parse_pdf(pdf_path: Path) -> tuple[str, str]:
    load_dotenv()
    api_key = os.getenv("LLAMA_CLOUD_API_KEY")

    if api_key and LlamaParse is not None:
        try:
            parser = LlamaParse(
                api_key=api_key,
                result_type="markdown",
                system_prompt=_load_prompt(LLAMAPARSE_PROMPT_FILE),
            )
            documents = parser.load_data(str(pdf_path))
            text = "\n\n".join(
                doc.text if hasattr(doc, "text") else getattr(doc, "page_content", "")
                for doc in documents
            ).strip()
            if text:
                return text, "llamaparse"
        except Exception:
            pass

    text = _parse_with_pymupdf(pdf_path)
    if not text:
        raise ValueError(f"No text could be extracted from {pdf_path.name}")
    return text, "pymupdf"
