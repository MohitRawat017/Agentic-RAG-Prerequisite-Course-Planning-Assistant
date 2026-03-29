from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = PROJECT_ROOT / "src" / "prompts"
DEFAULT_COURSE_FILE = PROJECT_ROOT / "data" / "processed" / "full_cleaned_documents_with_logic.json"
DEFAULT_PROGRAM_FILE = PROJECT_ROOT / "data" / "processed" / "clean_program.json"
DEFAULT_POLICY_FILE = PROJECT_ROOT / "data" / "processed" / "clean_policy.json"
DEFAULT_PLAN_REQUEST_FILE = PROJECT_ROOT / "data" / "processed" / "sample_planning_request.json"
DEFAULT_PLAN_OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "sample_course_plan.json"
INTAKE_PROMPT_FILE = PROMPTS_DIR / "phase4_intake_prompt.txt"
EXPLANATION_PROMPT_FILE = PROMPTS_DIR / "phase5_grounded_explanation_prompt.txt"
DEFAULT_CHROMA_DIR = PROJECT_ROOT / "chroma_db"
DEFAULT_RAG_DEMO_OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "phase5_demo_output.json"
DEFAULT_GRADIO_HISTORY_FILE = PROJECT_ROOT / "data" / "processed" / "gradio_chat_history.json"

DEFAULT_INTENT = "course_planning"
DEFAULT_PROGRAM_ID = "AAS_INFORMATION_SYSTEMS"
