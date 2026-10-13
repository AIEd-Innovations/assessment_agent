import json

import pytest
from pydantic import ValidationError

from assessment_agent.spec import (
    GradingSpec,
    SpecNotFoundError,
    list_specs,
    load_spec,
    load_spec_with_hash,
)


def test_loads_hw1_spec():
    spec = load_spec("hw1_sorting")
    assert spec.assignment_id == "hw1_sorting"
    assert [c.id for c in spec.criteria] == [
        "correctness", "input_output", "code_quality", "report_approach", "report_analysis",
    ]
    assert spec.max_score == 100


def test_reference_solution_is_loaded():
    spec = load_spec("hw2_linked_list")
    assert [f.filename for f in spec.reference_solution] == ["solution.py"]
    assert "class LinkedList" in spec.reference_solution[0].content


def test_unknown_assignment_raises():
    with pytest.raises(SpecNotFoundError):
        load_spec("no_such_assignment")


@pytest.mark.parametrize("bad_id", ["../config", "hw1_sorting/..", "a b", ""])
def test_unsafe_ids_rejected(bad_id):
    with pytest.raises(SpecNotFoundError):
        load_spec(bad_id)


def test_dump_excludes_solution():
    spec = load_spec("hw2_linked_list")
    view = spec.model_dump()
    assert "reference_solution" not in view
    assert spec.reference_solution[0].content not in json.dumps(view)
    assert view["max_score"] == 100


def test_hash_is_stable_and_distinct():
    _, first = load_spec_with_hash("hw1_sorting")
    _, again = load_spec_with_hash("hw1_sorting")
    _, other = load_spec_with_hash("hw2_linked_list")
    assert first == again
    assert first != other
    assert len(first) == 64


def test_list_specs_includes_both_assignments():
    assert {s.assignment_id for s in list_specs()} >= {"hw1_sorting", "hw2_linked_list"}


@pytest.mark.parametrize("criteria", [
    [],
    [{"id": "a", "name": "A", "max_points": 5}, {"id": "a", "name": "B", "max_points": 5}],
    [{"id": "a", "name": "A", "max_points": 0}],
])
def test_invalid_criteria_rejected(criteria):
    with pytest.raises(ValidationError):
        GradingSpec(assignment_id="x", criteria=criteria)
