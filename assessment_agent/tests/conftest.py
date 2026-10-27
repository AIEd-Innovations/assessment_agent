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
