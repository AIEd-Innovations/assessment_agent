import os

# Grading weights (defaults -- can be overridden per-assignment via system_config.yaml)
CODE_GRADE_WEIGHT = 0.60
REPORT_GRADE_WEIGHT = 0.30
MANUAL_REVIEW_WEIGHT = 0.10

# Course
COURSE_ID = "CSC 580"

# LLM provider (override via DEFAULT_LLM_PROVIDER env var)
# Supported: "claude_cli", "anthropic", "fake" (offline canned responses, no CLI or API key needed)
DEFAULT_LLM_PROVIDER = os.environ.get("DEFAULT_LLM_PROVIDER", "claude_cli")

# LLM input truncation
MAX_REPORT_CHARS = 8000
MAX_CODE_CHARS = 8000

# Sandbox limits
SANDBOX_TIMEOUT_SECONDS = 30
SANDBOX_MEMORY_LIMIT_MB = 256
MAX_SUBMISSION_SIZE_MB = 10

# Paths
_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
# Where results, the review queue and anomaly reports are written. Override with DATA_DIR (for example a mounted volume).
DATA_DIR = os.environ.get("DATA_DIR") or (
    "/appdata" if os.environ.get("CONTAINER_APP_NAME") else os.path.dirname(_PACKAGE_DIR)
)
RESULTS_FILE = os.path.join(DATA_DIR, "assessment_results.json")
REVIEW_QUEUE_FILE = os.path.join(DATA_DIR, "review_queue.json")
ANOMALY_REPORTS_FILE = os.path.join(DATA_DIR, "anomaly_reports.json")
TEST_CASES_DIR = os.path.join(_PACKAGE_DIR, "test_cases")  # legacy location
ASSIGNMENTS_DIR = os.path.join(_PACKAGE_DIR, "assignments")
PROMPTS_DIR = os.path.join(_PACKAGE_DIR, "prompts")


def ensure_data_dir() -> None:
    """Create DATA_DIR if needed, and fail at startup (not after a slow grading run) if it cannot be written."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except OSError as e:
        raise RuntimeError(f"Cannot create DATA_DIR {DATA_DIR!r}: {e}") from e
    if not os.access(DATA_DIR, os.W_OK):
        raise RuntimeError(
            f"DATA_DIR {DATA_DIR!r} is not writable by the current user. If it is a mounted volume, "
            "fix its ownership or permissions (the Docker image runs as uid 1000)."
        )
