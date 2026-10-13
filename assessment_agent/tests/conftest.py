import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from assessment_agent.llm.fake import FakeLLMProvider
from assessment_agent.models import SubmissionFile

_REPO_ROOT = Path(__file__).parent.parent.parent  # assessment_agent/tests/ → assessment_agent/ → project root
_SUBMISSIONS_DIR = _REPO_ROOT / "demo" / "submissions"


@pytest.fixture
def fake_provider() -> FakeLLMProvider:
    return FakeLLMProvider()


@pytest.fixture(autouse=True)
def data_dir(tmp_path: Path):
    """Redirect all file output to a temp directory."""
    old = os.environ.get("DATA_DIR")
    os.environ["DATA_DIR"] = str(tmp_path)

    import assessment_agent.config as cfg
    import assessment_agent.interfaces.integrity_guardian as ig
    saved = (cfg.DATA_DIR, cfg.RESULTS_FILE, cfg.ANOMALY_REPORTS_FILE, ig.ANOMALY_REPORTS_FILE)
    cfg.DATA_DIR             = str(tmp_path)
    cfg.RESULTS_FILE         = str(tmp_path / "assessment_results.json")
    cfg.ANOMALY_REPORTS_FILE = str(tmp_path / "anomaly_reports.json")
    ig.ANOMALY_REPORTS_FILE  = cfg.ANOMALY_REPORTS_FILE

    yield tmp_path

    cfg.DATA_DIR, cfg.RESULTS_FILE, cfg.ANOMALY_REPORTS_FILE, ig.ANOMALY_REPORTS_FILE = saved
    if old is None:
        os.environ.pop("DATA_DIR", None)
    else:
        os.environ["DATA_DIR"] = old


@pytest.fixture(scope="session")
def submissions() -> dict[str, SubmissionFile]:
    def read(name: str) -> SubmissionFile:
        return SubmissionFile(filename=name, content=(_SUBMISSIONS_DIR / name).read_text(encoding="utf-8"))

    return {
        "perfect_code":    read("student_a_perfect.py"),
        "report":          read("student_a_report.md"),
        "buggy_code":      read("student_b_buggy.py"),
        "suspicious_code": read("student_c_suspicious.py"),
        "partial_code":    read("student_d_partial.py"),
    }
