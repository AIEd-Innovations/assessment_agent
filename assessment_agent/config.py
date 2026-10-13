import os

# Course
COURSE_ID = "CSC 580"

# LLM provider (override via DEFAULT_LLM_PROVIDER env var)
# Supported: "claude_cli", "anthropic", "fake" (offline canned responses, no CLI or API key needed)
DEFAULT_LLM_PROVIDER = os.environ.get("DEFAULT_LLM_PROVIDER", "claude_cli")

# Submission limits
MAX_UPLOAD_CHARS = 1_000_000  # larger submissions are rejected
MAX_SUBMISSION_CHARS = 60000  # total text sent to the grader; anything past this is cut and flagged for review

# Paths
_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
# Where results and anomaly reports are written. Override with DATA_DIR (for example a mounted volume).
DATA_DIR = os.environ.get("DATA_DIR") or (
    "/appdata" if os.environ.get("CONTAINER_APP_NAME") else os.path.dirname(_PACKAGE_DIR)
)
RESULTS_FILE = os.path.join(DATA_DIR, "assessment_results.json")
ANOMALY_REPORTS_FILE = os.path.join(DATA_DIR, "anomaly_reports.json")
ASSIGNMENTS_DIR = os.path.join(_PACKAGE_DIR, "assignments")
PROMPTS_DIR = os.path.join(_PACKAGE_DIR, "prompts")
