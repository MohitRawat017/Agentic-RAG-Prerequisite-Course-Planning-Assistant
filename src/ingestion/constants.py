import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = PROJECT_ROOT / "src" / "prompts"
DEFAULT_COURSE_DIR = PROJECT_ROOT / "data" / "Courses"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
DEFAULT_OUTPUT_FILE = DEFAULT_OUTPUT_DIR / "sample_courses.json"
DEFAULT_REPORT_FILE = DEFAULT_OUTPUT_DIR / "ingestion_report.md"

SOURCE_URL = "https://southcentral.edu/majors-and-programs/course-descriptions-academic-catalog"
ACCESSED_DATE = "28 March 2026"

PREFERRED_SAMPLE_FILES = [
    "COMP1120_cco_2026.pdf",
    "COMP1130_cco_2026.pdf",
    "COMP2145_cco_2026.pdf",
]

STOP_MARKERS = (
    "Institutional Core Competencies",
    "Course Competencies",
    "Learning Objectives",
)

HEADER_PATTERNS = (
    re.compile(r"Common Course Outline - Page \d+ of \d+", re.IGNORECASE),
    re.compile(r"Course Outcome Summary - Page \d+ of \d+", re.IGNORECASE),
    re.compile(r"South Central College", re.IGNORECASE),
    re.compile(r"\b[A-Za-z]+,\s+[A-Za-z]+\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}\s+[AP]M\b"),
)

COURSE_HEADER_RE = re.compile(r"^\s*([A-Za-z]{3,4})\s*(\d{3,4})\s+(.+?)\s*$")
DESCRIPTION_BLOCK_RE = re.compile(
    r"Description\s+(.*?)\s+Total Credits",
    re.IGNORECASE | re.DOTALL,
)
INLINE_PREREQ_RE = re.compile(r"\(\s*Prerequisites?:\s*(.*?)\)", re.IGNORECASE | re.DOTALL)
CREDITS_RE = re.compile(r"Total Credits\s+(\d+(?:\.\d+)?)", re.IGNORECASE)
COURSE_CODE_RE = re.compile(r"\b([A-Za-z]{3,4})\s*(\d{3,4})\b")
GRADE_RE = re.compile(
    r"([ABCDF][+-]?\s*(?:[\[(]\s*\d\.\d\s*[\])])?\s*or\s*(?:better|higher))",
    re.IGNORECASE,
)

LLAMAPARSE_PROMPT_FILE = PROMPTS_DIR / "llamaparse_course_instructions.txt"
GROQ_PROMPT_FILE = PROMPTS_DIR / "groq_course_extraction.txt"
