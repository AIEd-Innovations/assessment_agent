import pytest

from assessment_agent import config
from assessment_agent.curriculum import CurriculumError, fetch_lab, lab_to_specs


def lab(**overrides) -> dict:
    data = {
        "lab_id": "lab4",
        "title": "Linked Lists",
        "spec_markdown": "# Lab 4\nImplement a linked list.",
        "agent_instructions": "Be encouraging.",
        "learning_objectives": ["pointer manipulation", "edge cases"],
        "difficulty": "intermediate",
        "approval_status": "approved",
        "version": 3,
        "rubric": {
            "code_weight": 0.6, "report_weight": 0.3, "manual_weight": 0.1,
            "criteria": [
                {"name": "Correctness", "weight": 2, "description": "Operations work."},
                {"name": "Correctness", "weight": 1, "description": "Edge cases work."},
                {"name": "Code Style!", "weight": 1, "description": "Readable."},
            ],
        },
        "quiz": [
            {"id": "q1", "question": "Cost of search?", "type": "short_answer", "expected_answer": "O(n)", "rubric_points": 5},
            {"id": "q2", "question": "Unscored warm-up", "type": "essay", "expected_answer": "", "rubric_points": 0},
        ],
    }
    data.update(overrides)
    return data


def test_rubric_becomes_a_spec_scaled_to_100_points():
    spec = lab_to_specs(lab(), "lab4")[0]
    assert spec.assignment_id == "lab4"
    assert [c.id for c in spec.criteria] == ["correctness", "correctness_2", "code_style"]
    assert [c.max_points for c in spec.criteria] == [50, 25, 25]
    assert spec.description.startswith("# Lab 4")
    assert spec.guidance == "Be encouraging."
    assert "pointer manipulation" in spec.skill_level
    assert spec.source == "curriculum-designer lab4 v3"


def test_quiz_becomes_a_separate_spec_with_expected_answers():
    specs = lab_to_specs(lab(), "lab4")
    quiz = specs[1]
    assert quiz.assignment_id == "lab4-quiz"
    assert [(c.id, c.max_points, c.expected_answer) for c in quiz.criteria] == [("q1", 5, "O(n)")]
    assert "O(n)" not in str(quiz.model_dump())


def test_lab_without_a_quiz_gives_one_spec():
    assert len(lab_to_specs(lab(quiz=[]), "lab4")) == 1


@pytest.mark.parametrize("status", ["pending", "needs_changes"])
def test_only_approved_labs_are_imported(status):
    with pytest.raises(CurriculumError) as exc:
        lab_to_specs(lab(approval_status=status), "lab4")
    assert exc.value.status == 409


def test_lab_without_weighted_criteria_is_rejected():
    with pytest.raises(CurriculumError) as exc:
        lab_to_specs(lab(rubric={"criteria": [{"name": "A", "weight": 0, "description": ""}]}), "lab4")
    assert exc.value.status == 422


async def test_fetch_needs_curriculum_url(monkeypatch):
    monkeypatch.setattr(config, "CURRICULUM_URL", "")
    with pytest.raises(CurriculumError) as exc:
        await fetch_lab("lab4")
    assert exc.value.status == 503
