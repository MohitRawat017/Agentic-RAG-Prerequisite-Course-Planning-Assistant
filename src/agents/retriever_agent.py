from src.rag.retriever import retrieve


def retrieve_plan_evidence(request: dict, plan: dict, vectorstore, k: int = 5) -> list[dict]:
    queries: list[str] = []
    if request.get("query"):
        queries.append(str(request["query"]))
    if request.get("target_program"):
        queries.append(str(request["target_program"]))
    if request.get("target_course"):
        queries.append(str(request["target_course"]))
    for course_id in plan.get("recommended_courses", []):
        queries.append(course_id)
    direct_course = plan.get("direct_course_result", {}).get("course_id") if plan.get("direct_course_result") else None
    if direct_course:
        queries.append(direct_course)

    evidence: list[dict] = []
    seen_chunk_ids: set[str] = set()
    for query in queries:
        for item in retrieve(query, vectorstore=vectorstore, k=k):
            chunk_id = item["metadata"].get("chunk_id")
            if chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk_id)
            evidence.append(item)
    return evidence
