"""Submitted files, kept so a submission can be graded again. Stored apart from results, in DATA_DIR/submissions/."""
import json
import re
from pathlib import Path

from assessment_agent import config
from assessment_agent.models import SubmissionFile

_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def _path(submission_id: str) -> Path:
    if not _ID_PATTERN.match(submission_id):
        raise ValueError(f"Invalid submission id {submission_id!r}")
    return Path(config.DATA_DIR) / "submissions" / f"{submission_id}.json"


def save_files(submission_id: str, files: list[SubmissionFile]) -> None:
    path = _path(submission_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([f.model_dump() for f in files]), encoding="utf-8")


def load_files(submission_id: str) -> list[SubmissionFile] | None:
    """The submitted files, or None if they were not stored (results graded before submissions were kept)."""
    try:
        path = _path(submission_id)
    except ValueError:
        return None
    if not path.is_file():
        return None
    return [SubmissionFile(**f) for f in json.loads(path.read_text(encoding="utf-8"))]
