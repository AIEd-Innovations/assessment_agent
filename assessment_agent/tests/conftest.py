import os
import sys
import json
from urllib.parse import parse_qsl, urlsplit
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import aied_db
import mongomock
import pytest
from fastapi.testclient import TestClient

from assessment_agent.llm.fake import FakeLLMProvider
from assessment_agent.models import SubmissionFile

TEST_COURSE_ID = "test-course"


def _seed_shared_defaults(db) -> None:
    defaults = json.loads((Path(aied_db.__file__).parent / "defaults.json").read_text())
    for agent in defaults["agents"]:
        for setting in agent["settings"]:
            db["agent_config_defaults"].insert_one({"agent": agent["agent"], **setting})


def _seed_fixture_assignments(db) -> None:
    root = _REPO_ROOT / "assessment_agent" / "assignments"
    for spec_path in root.glob("*/spec.json"):
        data = json.loads(spec_path.read_text())
        assignment_id = spec_path.parent.name
        db["assignments"].insert_one({
            "assignment_id": assignment_id,
            "course_id": TEST_COURSE_ID,
            "title": data.get("title", ""),
            "description": data.get("description", ""),
            "criteria": data["criteria"],
            "guidance": data.get("guidance", ""),
            "model": data.get("model", "claude-sonnet-5-5"),
            "source": "built-in",
            "max_score": float(sum(item["max_points"] for item in data["criteria"])),
            "created_at": None,
            "updated_at": None,
        })
        for path in (spec_path.parent / "solution").glob("*"):
            if not path.is_file():
                continue
            db["assignment_files"].insert_one({
                "course_id": TEST_COURSE_ID,
                "assignment_id": assignment_id,
                "file_id": f"fixture-{assignment_id}-{path.name}",
                "filename": path.name,
                "kind": "solution",
                "extracted_text": path.read_text(),
                "char_count": len(path.read_text()),
                "uploaded_at": None,
            })


@pytest.fixture(autouse=True)
def mongo_database(monkeypatch):
    """Give every legacy API test a fresh Mongo-backed course and URL scope."""
    from run import app

    db = mongomock.MongoClient().aied
    _seed_shared_defaults(db)
    _seed_fixture_assignments(db)
    db["users"].insert_one({"id": "test-instructor", "sso_subject": "user-oid-1", "email": "prof.smith@calpoly.edu", "name": "Prof Smith", "role": "instructor"})
    db["courses"].insert_one({"id": TEST_COURSE_ID, "instructor_id": "test-instructor", "name": "Test Course"})
    app.state.database = db

    original_request = TestClient.request

    def scoped_request(self, method, url, *args, **kwargs):
        parsed = urlsplit(str(url))
        path = parsed.path
        if path == "/submit":
            data = dict(kwargs.get("data") or {})
            data.setdefault("course_id", TEST_COURSE_ID)
            kwargs["data"] = data
        elif path != "/health":
            params = dict(parse_qsl(parsed.query))
            params.update(kwargs.get("params") or {})
            params.setdefault("course_id", TEST_COURSE_ID)
            kwargs["params"] = params
            url = path
        return original_request(self, method, url, *args, **kwargs)

    monkeypatch.setattr(TestClient, "request", scoped_request)
    yield db


@pytest.fixture
def assessment_repo(mongo_database):
    from aied_db.repos import AssessmentRepo
    return AssessmentRepo(mongo_database, TEST_COURSE_ID)

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
    saved = (cfg.DATA_DIR, cfg.RESULTS_FILE)
    cfg.DATA_DIR     = str(tmp_path)
    cfg.RESULTS_FILE = str(tmp_path / "assessment_results.json")

    yield tmp_path

    cfg.DATA_DIR, cfg.RESULTS_FILE = saved
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


def _pdf(text: str) -> bytes:
    """A one-page PDF whose text layer is `text` (empty text makes a PDF with nothing to extract)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode() if text else b""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return out


def _docx(*paragraphs: str) -> bytes:
    import io

    import docx

    document = docx.Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def make_pdf():
    return _pdf


@pytest.fixture
def make_docx():
    return _docx
