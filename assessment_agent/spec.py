"""
Grading specs: rubric criteria, guidance and the reference solution for an
assignment.

Read from assignments/{assignment_id}/spec.json, with reference solution files
in assignments/{assignment_id}/solution/. The total score is the sum of the
criteria, so any code/report balance is expressed as criterion points.

TODO: load specs from the curriculum designer once its rubric format is final.
Its rubric still has the fixed code/report/manual weights (0.6/0.3/0.1) and
fractional criterion weights; map those to Criterion.max_points here.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from pydantic import BaseModel, Field, computed_field, field_validator

from assessment_agent import config
from assessment_agent.models import SubmissionFile

_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


class Criterion(BaseModel):
    id: str
    name: str
    description: str = ""
    max_points: float


class GradingSpec(BaseModel):
    assignment_id: str
    title: str = ""
    description: str = ""
    criteria: list[Criterion]
    guidance: str = ""
    skill_level: str = ""  # what students are expected to know by this assignment
    # Excluded from model_dump(), so the solution never reaches an API response.
    reference_solution: list[SubmissionFile] = Field(default=[], exclude=True)

    @field_validator("criteria")
    @classmethod
    def _check_criteria(cls, criteria: list[Criterion]) -> list[Criterion]:
        if not criteria:
            raise ValueError("a spec needs at least one criterion")
        ids = [c.id for c in criteria]
        if len(ids) != len(set(ids)):
            raise ValueError("criterion ids must be unique")
        if any(c.max_points <= 0 for c in criteria):
            raise ValueError("max_points must be positive")
        return criteria

    @computed_field
    @property
    def max_score(self) -> float:
        return sum(c.max_points for c in self.criteria)


class SpecNotFoundError(LookupError):
    pass


def _assignment_dir(assignment_id: str) -> Path:
    if not _ID_PATTERN.match(assignment_id):
        raise SpecNotFoundError(f"Invalid assignment id {assignment_id!r}")
    return Path(config.ASSIGNMENTS_DIR) / assignment_id


def load_spec_with_hash(assignment_id: str) -> tuple[GradingSpec, str]:
    """Load a spec and return (spec, sha256 over spec.json and the solution files)."""
    directory = _assignment_dir(assignment_id)
    spec_path = directory / "spec.json"
    if not spec_path.is_file():
        raise SpecNotFoundError(f"No grading spec for assignment {assignment_id!r}")

    spec_text = spec_path.read_text(encoding="utf-8")
    digest = hashlib.sha256(spec_text.encode("utf-8"))

    solution: list[SubmissionFile] = []
    solution_dir = directory / "solution"
    if solution_dir.is_dir():
        for path in sorted(p for p in solution_dir.rglob("*") if p.is_file()):
            name = path.relative_to(solution_dir).as_posix()
            content = path.read_text(encoding="utf-8")
            solution.append(SubmissionFile(filename=name, content=content))
            digest.update(name.encode("utf-8"))
            digest.update(content.encode("utf-8"))

    data = json.loads(spec_text)
    data["assignment_id"] = assignment_id
    data["reference_solution"] = solution
    return GradingSpec(**data), digest.hexdigest()


def load_spec(assignment_id: str) -> GradingSpec:
    return load_spec_with_hash(assignment_id)[0]


def list_specs() -> list[GradingSpec]:
    root = Path(config.ASSIGNMENTS_DIR)
    if not root.is_dir():
        return []
    return [
        load_spec(entry.name)
        for entry in sorted(root.iterdir())
        if (entry / "spec.json").is_file() and _ID_PATTERN.match(entry.name)
    ]
