from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from assessment_agent import config
from assessment_agent.spec import load_spec
from run import app

client = TestClient(app)

RUBRIC = {
    "title": "Lab 9: Stacks",
    "description": "Implement a stack.",
    "criteria": [
        {"id": "push_pop", "name": "Push and pop", "max_points": 60},
        {"id": "q1", "name": "Question 1", "max_points": 40, "expected_answer": "LIFO"},
    ],
    "guidance": "Partial credit is fine.",
    "model": "gemini-3.8-flash",
}


def create(assignment_id="lab9", body=RUBRIC):
    return client.put(f"/assignments/{assignment_id}", json=body)


def test_put_creates_an_assignment_without_leaking_expected_answers():
    resp = create()
    assert resp.status_code == 200
    assert resp.json()["source"] == "upload"
    assert resp.json()["max_score"] == 100
    rubric = client.get("/assignments/lab9/rubric").json()
    assert rubric["model"] == "gemini-3.8-flash"
    assert "LIFO" not in str(rubric)
    assert load_spec("lab9").criteria[1].expected_answer == "LIFO"
    listed = {a["assignment_id"]: a for a in client.get("/assignments").json()}
    assert listed["lab9"]["source"] == "upload"


def test_invalid_rubrics_are_rejected():
    assert create(body={**RUBRIC, "criteria": []}).status_code == 400
    assert create(body={**RUBRIC, "model": "gpt-2"}).status_code == 400
    assert create("../etc", RUBRIC).status_code == 404


def test_solution_is_stored_but_never_returned(make_pdf):
    assert client.put("/assignments/lab9/solution", files=[("files", ("s.py", b"x"))]).status_code == 404
    create()
    resp = client.put("/assignments/lab9/solution", files=[
        ("files", ("stack.py", b"class Stack: SOLUTION_MARKER = 1")),
        ("files", ("key.pdf", make_pdf("ANSWER KEY MARKER"))),
    ])
    assert resp.json()["files"] == ["stack.py", "key.pdf"]
    solution = {f.filename: f.content for f in load_spec("lab9").reference_solution}
    assert "SOLUTION_MARKER" in solution["stack.py"]
    assert "ANSWER KEY MARKER" in solution["key.pdf.txt"]
    for path in ("/assignments", "/assignments/lab9/rubric", "/assignments/lab9/materials"):
        assert "MARKER" not in client.get(path).text


def test_replacing_the_solution_removes_the_old_one():
    create()
    client.put("/assignments/lab9/solution", files=[("files", ("old.py", b"old"))])
    client.put("/assignments/lab9/solution", files=[("files", ("new.py", b"new"))])
    assert [f.filename for f in load_spec("lab9").reference_solution] == ["new.py"]


def test_bad_solution_file_keeps_the_old_solution():
    create()
    client.put("/assignments/lab9/solution", files=[("files", ("old.py", b"old"))])
    resp = client.put("/assignments/lab9/solution", files=[("files", ("x.png", b"\x89PNG\xff\xfe"))])
    assert resp.status_code == 400
    assert [f.filename for f in load_spec("lab9").reference_solution] == ["old.py"]


def test_materials_upload_list_and_delete(make_pdf, make_docx):
    create()
    resp = client.post("/assignments/lab9/materials", files=[
        ("files", ("notes.pdf", make_pdf("Stacks are LIFO"))),
        ("files", ("handout.docx", make_docx("Use push and pop"))),
        ("files", ("extra.md", b"# Extra")),
    ])
    assert resp.status_code == 200
    assert "warning" not in resp.json()
    names = [m["name"] for m in client.get("/assignments/lab9/materials").json()]
    assert sorted(names) == ["extra.md", "handout.docx", "notes.pdf"]
    assert any("LIFO" in m.content for m in load_spec("lab9").materials)

    assert client.delete("/assignments/lab9/materials/notes.pdf").status_code == 204
    assert sorted(m["name"] for m in client.get("/assignments/lab9/materials").json()) == ["extra.md", "handout.docx"]
    assert client.delete("/assignments/lab9/materials/notes.pdf").status_code == 404


def test_materials_over_the_limit_warn(monkeypatch):
    monkeypatch.setattr(config, "MAX_MATERIAL_CHARS", 10)
    create()
    resp = client.post("/assignments/lab9/materials", files=[("files", ("long.txt", b"x" * 50))])
    assert "only the first 10" in resp.json()["warning"]


def test_unsupported_material_stores_nothing():
    create()
    resp = client.post("/assignments/lab9/materials", files=[
        ("files", ("ok.txt", b"fine")),
        ("files", ("x.png", b"\x89PNG\xff\xfe")),
    ])
    assert resp.status_code == 400
    assert client.get("/assignments/lab9/materials").json() == []


def test_uploaded_spec_overrides_a_built_in_example_until_deleted():
    assert load_spec("hw1_sorting").source == "built-in"
    create("hw1_sorting")
    assert load_spec("hw1_sorting").source == "upload"
    assert client.delete("/assignments/hw1_sorting").status_code == 204
    assert load_spec("hw1_sorting").source == "built-in"


def test_built_in_and_unknown_assignments_cannot_be_deleted():
    assert client.delete("/assignments/hw1_sorting").status_code == 400
    assert client.delete("/assignments/nope").status_code == 404


def test_uploaded_assignment_is_graded():
    create()
    resp = client.post("/submit-json", json={
        "student_id": "s1", "assignment_id": "lab9", "files": [{"filename": "stack.py", "content": "class Stack: ..."}],
    })
    assert resp.status_code == 200
    assert resp.json()["max_score"] == 100


LAB = {
    "lab_id": "lab4",
    "title": "Linked Lists",
    "spec_markdown": "Implement a linked list.",
    "agent_instructions": "",
    "learning_objectives": ["pointers"],
    "difficulty": "basic",
    "approval_status": "approved",
    "version": 1,
    "material_content": "Lecture: nodes point to the next node.",
    "rubric": {"criteria": [{"name": "Correctness", "weight": 1, "description": "Works."}]},
    "quiz": [{"id": "q1", "question": "Search cost?", "type": "short_answer", "expected_answer": "O(n)", "rubric_points": 5}],
}


def import_lab(lab=LAB, path="/assignments/import/lab4"):
    async def fake_fetch(lab_id):
        return lab
    with patch("assessment_agent.curriculum.fetch_lab", fake_fetch):
        return client.post(path)


def test_import_creates_the_lab_and_its_quiz(data_dir: Path):
    resp = import_lab()
    assert resp.status_code == 200
    assert resp.json() == {"imported": ["lab4", "lab4-quiz"], "material": True}
    assert load_spec("lab4").source == "curriculum-designer lab4 v1"
    assert load_spec("lab4-quiz").criteria[0].expected_answer == "O(n)"
    assert "nodes point" in load_spec("lab4").materials[0].content
    assert "O(n)" not in client.get("/assignments/lab4-quiz/rubric").text


def test_reimport_keeps_the_uploaded_solution():
    import_lab()
    client.put("/assignments/lab4/solution", files=[("files", ("list.py", b"class Node: ..."))])
    import_lab({**LAB, "version": 2})
    spec = load_spec("lab4")
    assert spec.source == "curriculum-designer lab4 v2"
    assert [f.filename for f in spec.reference_solution] == ["list.py"]


def test_import_into_a_chosen_assignment_id():
    assert import_lab(path="/assignments/import/lab4?assignment_id=hw4").json()["imported"] == ["hw4", "hw4-quiz"]


def test_unapproved_lab_is_409():
    assert import_lab({**LAB, "approval_status": "pending"}).status_code == 409
