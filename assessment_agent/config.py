import os

# Course
COURSE_ID = "CSC 580"

# Model used when an assignment's spec names none (see llm/models.py for the supported list)
DEFAULT_MODEL = "claude-sonnet-5-5"

# Submission limits
MAX_UPLOAD_CHARS = 1_000_000  # larger submissions are rejected
MAX_SUBMISSION_CHARS = 60000  # total text sent to the grader; anything past this is cut and flagged for review
MAX_MATERIAL_CHARS = 40000  # course material sent to the grader; instructors are warned at upload when it is longer
MAX_MATERIAL_FILE_MB = 20  # per uploaded solution or material file

# Curriculum designer base URL for importing approved labs, e.g. http://localhost:8003
CURRICULUM_URL = os.environ.get("CURRICULUM_URL", "")

# Microsoft sign-in (see auth.py). With AUTH_MS_CLIENT_ID unset every endpoint is open, as before.
AUTH_MS_CLIENT_ID = os.environ.get("AUTH_MS_CLIENT_ID", "")  # the instructor UI's VITE_MS_CLIENT_ID
AUTH_MS_TENANT_ID = os.environ.get("AUTH_MS_TENANT_ID", "1b0d02db-fc9e-4495-9537-1d379cca2ae7")  # Cal Poly
AUTH_ALLOWED_EMAIL_DOMAIN = os.environ.get("AUTH_ALLOWED_EMAIL_DOMAIN", "calpoly.edu").lower()

# Paths
_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
# Where results and instructor-provided specs are written. Override with DATA_DIR (for example a mounted volume).
DATA_DIR = os.environ.get("DATA_DIR") or (
    "/appdata" if os.environ.get("CONTAINER_APP_NAME") else os.path.dirname(_PACKAGE_DIR)
)
RESULTS_FILE = os.path.join(DATA_DIR, "assessment_results.json")
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
