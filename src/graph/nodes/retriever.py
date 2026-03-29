from __future__ import annotations

from src.graph.state import GraphState
from src.rag.chunking import build_record_documents
from src.rag.retriever import retrieve_chunks
from src.rag.vectorstore import get_chroma_vectorstore, index_documents
from src.utils.constants import DEFAULT_TOP_K


def retriever_node(state: GraphState) -> GraphState:
    vectorstore = get_chroma_vectorstore(rebuild=state.get("rebuild_index", False))
    documents = build_record_documents(state["courses"], state["program"], state["policies"])
    index_documents(vectorstore, documents, rebuild=state.get("rebuild_index", False))

    retrieved_chunks = retrieve_chunks(
        vectorstore,
        state.get("retrieval_queries", []),
        filters=state.get("retrieval_filters") or None,
    )
    retrieved_chunks = _merge_priority_chunks(state, documents, retrieved_chunks)

    return {
        **state,
        "retrieved_chunks": retrieved_chunks,
        "retrieved_chunk_ids": [item["chunk_id"] for item in retrieved_chunks],
    }


def _merge_priority_chunks(
    state: GraphState,
    documents: list,
    retrieved_chunks: list[dict],
) -> list[dict]:
    priority_chunks: list[dict] = []
    document_by_chunk_id = {
        str(document.metadata.get("chunk_id")): {
            "chunk_id": str(document.metadata.get("chunk_id")),
            "text": document.page_content,
            "metadata": dict(document.metadata),
        }
        for document in documents
        if document.metadata.get("chunk_id")
    }

    priority_chunk_ids: list[str] = []
    target_course = state.get("student_profile", {}).get("target_course")
    target_program = state.get("student_profile", {}).get("target_program")
    if target_course:
        priority_chunk_ids.append(f"course_{target_course}")
    if target_program:
        priority_chunk_ids.append(f"program_{target_program}")
    for course_id in state.get("priority_course_ids", []):
        priority_chunk_ids.append(f"course_{course_id}")

    seen: set[str] = set()
    for chunk_id in priority_chunk_ids:
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        chunk = document_by_chunk_id.get(chunk_id)
        if chunk is not None:
            priority_chunks.append(chunk)

    final_results: list[dict] = []
    added: set[str] = set()
    for chunk in priority_chunks + list(retrieved_chunks):
        chunk_id = str(chunk.get("chunk_id") or "")
        if not chunk_id or chunk_id in added:
            continue
        added.add(chunk_id)
        final_results.append(chunk)
        if len(final_results) >= DEFAULT_TOP_K:
            break
    return final_results
