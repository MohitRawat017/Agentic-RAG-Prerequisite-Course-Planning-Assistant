from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
PROMPTS_DIR = SRC_DIR / "prompts"
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"

DEFAULT_COURSES_PATH = PROCESSED_DATA_DIR / "full_cleaned_documents_with_logic.json"
DEFAULT_PROGRAM_PATH = PROCESSED_DATA_DIR / "clean_program.json"
DEFAULT_POLICIES_PATH = PROCESSED_DATA_DIR / "clean_policy.json"
DEFAULT_OUTPUT_PATH = PROCESSED_DATA_DIR / "sample_course_plan.json"

DEFAULT_CHROMA_DIR = PROJECT_ROOT / "chroma_db"
CHROMA_COLLECTION_NAME = "pure_rag_catalog"
CHROMA_COLLECTION_METADATA = {"hnsw:space": "cosine"}

GEMINI_EMBEDDING_MODEL = "gemini-embedding-2-preview"
GROQ_PLANNER_MODEL = "llama-3.3-70b-versatile"
DEFAULT_TOP_K = 3
DEFAULT_FALLBACK_MAX_CREDITS = 8
COURSE_CCO_URL_TEMPLATE = "https://southcentral.edu/webdocs/current_cco/{course_id}_cco_2026.pdf"

PLANNER_PROMPT_PATH = PROMPTS_DIR / "pure_rag_planner_prompt.txt"

MANDATORY_OUTPUT_HEADERS = (
    "Answer / Plan:",
    "Why (requirements/prereqs satisfied):",
    "Citations:",
    "Clarifying questions (if needed):",
    "Assumptions / Not in catalog:",
)

NONE_TEXT = "None"
