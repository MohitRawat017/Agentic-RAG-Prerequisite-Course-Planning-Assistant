from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from src.utils.constants import GEMINI_EMBEDDING_MODEL, PROJECT_ROOT


def get_gemini_embeddings() -> GoogleGenerativeAIEmbeddings:
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY or GEMINI_API_KEY is required to use Gemini embeddings.")

    os.environ["GOOGLE_API_KEY"] = api_key
    os.environ.pop("GEMINI_API_KEY", None)
    return GoogleGenerativeAIEmbeddings(model=GEMINI_EMBEDDING_MODEL, api_key=api_key)
