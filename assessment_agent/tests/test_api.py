import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from assessment_agent import config
from run import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch):
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "fake")


def submit(*files, student_id="s1", assignment_id="hw1_sorting"):
    return client.post(
        "/submit",
        data={"student_id": student_id, "assignment_id": assignment_id},
        files=[("files", f) for f in files],
    )


def test_multipart_submission_with_several_files(submissions):
    code, report = submissions["perfect_code"], submissions["report"]
    resp = submit((code.filename, code.content.encode()), (report.filename, report.content.encode()))
    assert resp.status_code == 200
    body = resp.json()
    assert body["files"] == [code.filename, report.filename]
    assert body["status"] == "ai_graded"
    assert body["score"] == 80


def test_json_submission():
    resp = client.post("/submit-json", json={
        "student_id": "s1",
        "assignment_id": "hw2_linked_list",
        "files": [{"filename": "list.cpp", "content": "struct Node { int v; Node* next; };"}],
    })
    assert resp.status_code == 200
    assert resp.json()["max_score"] == 100


def test_oversized_json_submission_is_rejected(monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_CHARS", 10)
    resp = client.post("/submit-json", json={
        "student_id": "s1",
        "assignment_id": "hw1_sorting",
        "files": [{"filename": "a.py", "content": "x" * 11}],
    })
    assert resp.status_code == 400


def test_json_submission_without_files_is_rejected():
    resp = client.post("/submit-json", json={"student_id": "s1", "assignment_id": "hw1_sorting", "files": []})
    assert resp.status_code == 400


def test_unknown_assignment_is_404():
    assert submit(("a.py", b"print(1)"), assignment_id="nope").status_code == 404


def test_binary_upload_is_rejected():
    assert submit(("image.png", b"\x89PNG\r\n\x1a\n\xff\xfe")).status_code == 400


def test_assignments_list():
    ids = {a["assignment_id"] for a in client.get("/assignments").json()}
    assert {"hw1_sorting", "hw2_linked_list"} <= ids


def test_rubric_never_includes_the_solution():
    resp = client.get("/assignments/hw2_linked_list/rubric")
    assert resp.status_code == 200
    assert "reference_solution" not in resp.json()
    assert "self.tail = prev" not in resp.text
    assert client.get("/assignments/nope/rubric").status_code == 404


def _seed(data_dir: Path, *results):
    (data_dir / "assessment_results.json").write_text(json.dumps(list(results)))


def _result(submission_id, status="ai_graded", score=70.0):
    return {
        "submission_id": submission_id,
        "student_id": "s1",
        "assignment_id": "hw1_sorting",
        "score": score,
        "max_score": 100.0,
        "status": status,
        "final_score": None,
        "provenance": None,
    }


def test_results_filter_by_status(data_dir: Path):
    _seed(data_dir, _result("a"), _result("b", status="needs_review"))
    got = client.get("/results", params={"status": "needs_review"}).json()
    assert [r["submission_id"] for r in got] == ["b"]


def test_review_replaces_the_score(data_dir: Path):
    _seed(data_dir, _result("sub1", status="needs_review", score=None))
    resp = client.post("/results/sub1/review", json={"final_score": 88, "notes": "Checked by hand"})
    assert resp.status_code == 200

    got = client.get("/results/sub1").json()
    assert got["final_score"] == 88
    assert got["status"] == "instructor_graded"
    assert got["instructor_notes"] == "Checked by hand"
    assert got["reviewed_at"]


@pytest.mark.parametrize("score", [-1, 101])
def test_review_score_must_be_within_max(data_dir: Path, score):
    _seed(data_dir, _result("sub1"))
    assert client.post("/results/sub1/review", json={"final_score": score}).status_code == 400


def test_review_of_a_result_without_max_score(data_dir: Path):
    legacy = _result("old")
    del legacy["max_score"]
    _seed(data_dir, legacy)
    assert client.post("/results/old/review", json={"final_score": 85}).status_code == 200
    assert client.post("/results/old/review", json={"final_score": -1}).status_code == 400


def test_review_unknown_submission_is_404():
    assert client.post("/results/missing/review", json={"final_score": 5}).status_code == 404


def test_provenance_endpoint(data_dir: Path, submissions):
    code = submissions["perfect_code"]
    submission_id = submit((code.filename, code.content.encode())).json()["submission_id"]
    prov = client.get(f"/results/{submission_id}/provenance").json()
    assert prov["spec_hash"]
    assert {c["stage"] for c in prov["llm_calls"]} == {"grading", "anomaly_detection"}


def test_provenance_missing_on_old_results(data_dir: Path):
    _seed(data_dir, _result("legacy"))
    assert client.get("/results/legacy/provenance").status_code == 404
