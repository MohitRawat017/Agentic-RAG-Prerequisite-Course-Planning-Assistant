import os
import shutil
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.documents import Document

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except Exception:
    from langchain.text_splitter import RecursiveCharacterTextSplitter

from src.planning.constants import DEFAULT_CHROMA_DIR


COLLECTION_NAME = "course_planning_rag"
EMBEDDING_MODEL = "gemini-embedding-2-preview"
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200


def build_chunk_documents(courses: list[dict], program: dict, policies: list[dict]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    documents: list[Document] = []

    for course in courses:
        base_metadata = {
            "type": "course",
            "course_id": course["course_id"],
            "course_code": course["course_id"],
            "source_url": course.get("source_url"),
            "page_number": course.get("page_number"),
        }
        documents.extend(_split_record_text(_course_record_text(course), f"course_{course['course_id']}", base_metadata, splitter))

    program_metadata = {
        "type": "program",
        "program_id": program["program_id"],
        "source_url": program.get("source_url"),
        "page_number": program.get("page_number"),
    }
    documents.extend(_split_record_text(_program_record_text(program), f"program_{program['program_id']}", program_metadata, splitter))

    for policy in policies:
        base_metadata = {
            "type": "policy",
            "policy_id": policy["policy_id"],
            "source_url": policy.get("source_url"),
            "page_number": policy.get("page_number"),
        }
        documents.extend(_split_record_text(_policy_record_text(policy), f"policy_{policy['policy_id']}", base_metadata, splitter))

    return documents


def get_or_create_vectorstore(persist_dir: str | Path = DEFAULT_CHROMA_DIR, rebuild: bool = False):
    persist_path = Path(persist_dir)
    if rebuild and persist_path.exists():
        shutil.rmtree(persist_path)

    from langchain_chroma import Chroma

    embeddings = _build_embeddings()
    return Chroma(
        collection_name=COLLECTION_NAME,
        persist_directory=str(persist_path),
        embedding_function=embeddings,
    )


def index_documents(vectorstore, documents: list[Document], rebuild: bool = False) -> None:
    if not documents:
        return

    existing_count = 0
    try:
        existing_count = vectorstore._collection.count()
    except Exception:
        existing_count = 0

    if existing_count > 0 and not rebuild:
        return

    ids = [document.metadata["chunk_id"] for document in documents]
    vectorstore.add_documents(documents=documents, ids=ids)


def retrieve(query: str, vectorstore, k: int = 5) -> list[dict]:
    if not query.strip():
        return []
    results = vectorstore.similarity_search(query, k=k)
    return [
        {
            "text": item.page_content,
            "metadata": dict(item.metadata),
        }
        for item in results
    ]


def _build_embeddings():
    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY or GEMINI_API_KEY is required for Phase 5 retrieval")
    os.environ.setdefault("GOOGLE_API_KEY", api_key)
    try:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
    except Exception as exc:
        raise RuntimeError("langchain_google_genai is required for Phase 5 retrieval") from exc
    return GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL, google_api_key=api_key)


def _split_record_text(
    text: str,
    chunk_prefix: str,
    metadata: dict,
    splitter: RecursiveCharacterTextSplitter,
) -> list[Document]:
    chunks = splitter.split_text(text)
    documents: list[Document] = []
    for index, chunk_text in enumerate(chunks, start=1):
        chunk_metadata = dict(metadata)
        chunk_metadata["chunk_id"] = f"{chunk_prefix}_{index}"
        documents.append(Document(page_content=chunk_text, metadata=chunk_metadata))
    return documents


def _course_record_text(course: dict) -> str:
    parts = [
        f"Course {course['course_id']}: {course['course_title']}.",
        f"Description: {course.get('description') or 'Not provided.'}",
        f"Prerequisites: {course.get('prerequisites') or 'None'}",
        f"Corequisites: {course.get('corequisites') or 'None'}",
        f"Credits: {course.get('credits') or 'Unknown'}",
    ]
    if course.get("notes"):
        parts.append(f"Notes: {course['notes']}")
    return " ".join(parts)


def _program_record_text(program: dict) -> str:
    general_education = ", ".join(_stringify_program_item(item) for item in program.get("general_education", [])) or "None"
    parts = [
        f"Program {program['program_id']}: {program.get('program_name')}.",
        f"Total credits required: {program.get('total_credits_required')}.",
        f"Core courses: {', '.join(program.get('core_courses', [])) or 'None'}.",
        f"Electives: {', '.join(program.get('electives', [])) or 'None'}.",
        f"General education: {general_education}.",
        f"Capstone: {program.get('capstone') or 'None'}.",
        f"Rules: {'; '.join(program.get('rules', [])) or 'None'}.",
    ]
    return " ".join(parts)


def _policy_record_text(policy: dict) -> str:
    return " ".join(
        [
            f"Policy {policy['policy_id']}: {policy.get('policy_name')}.",
            f"Rules: {'; '.join(policy.get('rules', [])) or 'None'}.",
        ]
    )


def _stringify_program_item(item: object) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        if item.get("type") == "OR":
            return " OR ".join(item.get("options", []))
    return str(item)
