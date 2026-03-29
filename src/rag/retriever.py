from __future__ import annotations

from langchain_chroma import Chroma

from src.utils.constants import DEFAULT_TOP_K


def build_retrieval_queries(
    original_query: str,
    *,
    target_course: str | None = None,
    target_course_name: str | None = None,
    target_program: str | None = None,
) -> list[str]:
    course_ref = (target_course_name or target_course or "").strip()
    program_ref = (target_program or "").strip()

    queries = [
        original_query.strip(),
        course_ref,
        f"prerequisites of {course_ref}" if course_ref else "",
        f"requirements for {program_ref}" if program_ref else "",
    ]

    seen: set[str] = set()
    ordered: list[str] = []
    for query in queries:
        normalized = " ".join(query.split())
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(normalized)
    return ordered


def retrieve_chunks(
    vectorstore: Chroma,
    query_strings: list[str],
    top_k: int = DEFAULT_TOP_K,
    filters: dict | None = None,
) -> list[dict]:
    unique_results: list[dict] = []
    seen_chunk_ids: set[str] = set()

    for query in query_strings:
        if len(unique_results) >= top_k:
            break

        remaining_slots = top_k - len(unique_results)
        results = vectorstore.similarity_search(query, k=remaining_slots, filter=filters or None)
        for item in results:
            metadata = dict(item.metadata)
            chunk_id = str(metadata.get("chunk_id") or "")
            if not chunk_id or chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk_id)
            unique_results.append(
                {
                    "chunk_id": chunk_id,
                    "text": item.page_content,
                    "metadata": metadata,
                }
            )
            if len(unique_results) >= top_k:
                break

    return unique_results
