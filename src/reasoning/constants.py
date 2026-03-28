from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = PROJECT_ROOT / "src" / "prompts"
DEFAULT_COURSE_INPUT = PROJECT_ROOT / "data" / "processed" / "full_cleaned_documents.json"
DEFAULT_COURSE_OUTPUT = PROJECT_ROOT / "data" / "processed" / "full_cleaned_documents_with_logic.json"
PREREQ_PARSER_PROMPT_FILE = PROMPTS_DIR / "phase3_prereq_parser.txt"

GRADE_ORDER = {
    "A": 12,
    "A-": 11,
    "B+": 10,
    "B": 9,
    "B-": 8,
    "C+": 7,
    "C": 6,
    "C-": 5,
    "D+": 4,
    "D": 3,
    "D-": 2,
    "F": 1,
}

SUPPORTED_NODE_TYPES = {"AND", "OR", "COURSE", "ASSESSMENT", "EXCEPTION", "UNKNOWN", "NON_ENFORCEABLE"}
