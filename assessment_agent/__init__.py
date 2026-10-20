from dotenv import load_dotenv

# Load .env (if present) before config.py reads environment variables at import time.
load_dotenv()

from assessment_agent.main import create_assessment_app  # noqa: E402

__all__ = ["create_assessment_app"]
