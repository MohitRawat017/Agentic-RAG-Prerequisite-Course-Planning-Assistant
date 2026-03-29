from __future__ import annotations

from src.graph.state import GraphState
from src.rag.retriever import build_chunk_documents, get_or_create_vectorstore, index_documents, retrieve


def retriever_node(state: GraphState) -> GraphState:
    vectorstore = get_or_create_vectorstore(rebuild=state.get("rebuild_index", False))
    index_documents(
        vectorstore,
        build_chunk_documents(state["courses"], state["program"], state["policies"]),
        rebuild=state.get("rebuild_index", False),
    )
    return {
        **state,
        "vectorstore": vectorstore,
        "retrieved_chunks": _retrieve_request_evidence(state["request"], vectorstore),
    }


def _retrieve_request_evidence(request: dict, vectorstore) -> list[dict]:
    queries: list[str] = []
    if request.get("query"):
        queries.append(str(request["query"]))
    if request.get("target_program"):
        queries.append(str(request["target_program"]))
    if request.get("target_course"):
        queries.append(str(request["target_course"]))

    evidence: list[dict] = []
    seen_chunk_ids: set[str] = set()
    for query in queries:
        for item in retrieve(query, vectorstore=vectorstore, k=5):
            chunk_id = item["metadata"].get("chunk_id")
            if chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk_id)
            evidence.append(item)
    return evidence
