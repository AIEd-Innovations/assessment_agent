"""Issue #23 integration tests against the shared repository using mongomock."""
import json
from pathlib import Path

import mongomock
from fastapi.testclient import TestClient
import aied_db
from aied_db.repos import AssessmentRepo

from assessment_agent.main import create_assessment_app
from assessment_agent.auth import Instructor, require_instructor
from assessment_agent.spec import load_repo_spec_with_hash


COURSE_A = "course-a"
COURSE_B = "course-b"
RUBRIC = {
    "title": "Sorting",
    "criteria": [{"id": "correct", "name": "Correct", "max_points": 100}],
    "model": "gemini-3.8-flash",
}


def seed_defaults(db):
    defaults = json.loads((Path(aied_db.__file__).parent / "defaults.json").read_text())
    for agent in defaults["agents"]:
        for setting in agent["settings"]:
            db["agent_config_defaults"].insert_one({"agent": agent["agent"], **setting})


def app_with_database():
    db = mongomock.MongoClient().aied
    seed_defaults(db)
    app = create_assessment_app()
    app.state.database = db
    return app


def test_course_scopes_assignments_results_and_regrades():
    app = app_with_database()
    with TestClient(app) as client:
        assert client.put("/assignments/lab1", params={"course_id": COURSE_A}, json=RUBRIC).status_code == 200
        assert client.put("/assignments/lab1", params={"course_id": COURSE_B}, json=RUBRIC).status_code == 200
        result = client.post("/submit-json", params={"course_id": COURSE_A}, json={"student_id": "s1", "assignment_id": "lab1", "files": [{"filename": "main.py", "content": "print(1)"}]}).json()
        assert client.get("/results", params={"course_id": COURSE_A}).json()[0]["submission_id"] == result["submission_id"]
        assert client.get("/results", params={"course_id": COURSE_B}).json() == []
        assert client.post(f"/results/{result['submission_id']}/regrade", params={"course_id": COURSE_B}).status_code == 404
        assert client.post(f"/results/{result['submission_id']}/regrade", params={"course_id": COURSE_A}).status_code == 200


def test_results_persist_when_a_new_app_uses_the_same_database():
    app = app_with_database()
    with TestClient(app) as client:
        client.put("/assignments/lab1", params={"course_id": COURSE_A}, json=RUBRIC)
        client.post("/submit-json", params={"course_id": COURSE_A}, json={"student_id": "s1", "assignment_id": "lab1", "files": [{"filename": "main.py", "content": "print(1)"}]})
    replacement = create_assessment_app()
    replacement.state.database = app.state.database
    with TestClient(replacement) as client:
        assert len(client.get("/results", params={"course_id": COURSE_A}).json()) == 1


def test_agent_config_changes_the_grading_spec_hash():
    app = app_with_database()
    with TestClient(app) as client:
        assert client.put("/assignments/lab1", params={"course_id": COURSE_A}, json=RUBRIC).status_code == 200
        repo = AssessmentRepo(app.state.database, COURSE_A)
        _, before = load_repo_spec_with_hash(repo, "lab1")
        assert client.put(
            "/assignments/lab1/agent-config",
            params={"course_id": COURSE_A},
            json={"tone": "Direct", "feedback_detail": "Detailed", "partial_credit": "Strict", "notes": "Focus on edge cases."},
        ).status_code == 200
        _, after = load_repo_spec_with_hash(repo, "lab1")
    assert after != before


def test_other_instructor_cannot_read_or_regrade_a_course():
    app = app_with_database()
    db = app.state.database
    db["users"].insert_many([
        {"id": "a", "sso_subject": "oid-a", "email": "a@calpoly.edu", "name": "A", "role": "instructor"},
        {"id": "b", "sso_subject": "oid-b", "email": "b@calpoly.edu", "name": "B", "role": "instructor"},
    ])
    db["courses"].insert_one({"id": COURSE_A, "instructor_id": "a", "name": "A's course"})
    app.dependency_overrides[require_instructor] = lambda: Instructor(email="a@calpoly.edu", name="A", oid="oid-a")
    with TestClient(app) as client:
        assert client.put("/assignments/lab1", params={"course_id": COURSE_A}, json=RUBRIC).status_code == 200
        result = client.post("/submit-json", params={"course_id": COURSE_A}, json={"student_id": "s1", "assignment_id": "lab1", "files": [{"filename": "main.py", "content": "print(1)"}]}).json()
    app.dependency_overrides[require_instructor] = lambda: Instructor(email="b@calpoly.edu", name="B", oid="oid-b")
    with TestClient(app) as client:
        assert client.get("/results", params={"course_id": COURSE_A}).status_code == 403
        assert client.post(f"/results/{result['submission_id']}/regrade", params={"course_id": COURSE_A}).status_code == 403
