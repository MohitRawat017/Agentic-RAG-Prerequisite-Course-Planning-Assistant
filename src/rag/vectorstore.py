from __future__ import annotations

import shutil
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document

from src.rag.embeddings import get_gemini_embeddings
from src.utils.constants import (
    CHROMA_COLLECTION_METADATA,
    CHROMA_COLLECTION_NAME,
    DEFAULT_CHROMA_DIR,
)


def get_chroma_vectorstore(rebuild: bool = False) -> Chroma:
    persist_directory = Path(DEFAULT_CHROMA_DIR)
    if rebuild and persist_directory.exists():
        shutil.rmtree(persist_directory)

    persist_directory.mkdir(parents=True, exist_ok=True)
    return Chroma(
        collection_name=CHROMA_COLLECTION_NAME,
        collection_metadata=CHROMA_COLLECTION_METADATA,
        persist_directory=str(persist_directory),
        embedding_function=get_gemini_embeddings(),
    )


def index_documents(vectorstore: Chroma, documents: list[Document], rebuild: bool = False) -> None:
    if not documents:
        return

    ids = [str(document.metadata["chunk_id"]) for document in documents]
    expected_state = {
        str(document.metadata["chunk_id"]): {
            "page_content": document.page_content,
            "metadata": dict(document.metadata),
        }
        for document in documents
    }
    existing_snapshot = vectorstore.get(include=["documents", "metadatas"])
    existing_ids = [str(item) for item in existing_snapshot.get("ids", [])]
    existing_state = {
        str(chunk_id): {
            "page_content": page_content or "",
            "metadata": dict(metadata or {}),
        }
        for chunk_id, page_content, metadata in zip(
            existing_snapshot.get("ids", []),
            existing_snapshot.get("documents", []),
            existing_snapshot.get("metadatas", []),
            strict=False,
        )
    }

    if not rebuild and existing_state == expected_state:
        return

    if existing_ids:
        vectorstore.delete(ids=existing_ids)

    vectorstore.add_documents(documents=documents, ids=ids)
