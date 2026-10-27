"""
Grading specs: rubric criteria, guidance, model, reference solution and course
materials for an assignment.

Specs provided by instructors live in DATA_DIR/assignments/{assignment_id}/ and
take precedence over the built-in examples in assessment_agent/assignments/.
An assignment folder holds:

    spec.json                         rubric and settings
    solution/                         reference solutions and answer keys, as text
    materials/                        course materials, as text
    originals/{solution,materials}/   uploads exactly as received

The total score is the sum of the criteria. All spec file access is in this
module, so moving specs to shared storage later only changes this file.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, Field, computed_field, field_validator

from assessment_agent import config
from assessment_agent.extract import UnsupportedFileError, extract_text, text_name
from assessment_agent.llm.models import SUPPORTED_MODELS
from assessment_agent.models import SubmissionFile

_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_FILE_NAME_PATTERN = re.compile(r"^[\w .()-]+$")


class Criterion(BaseModel):
    id: str
    name: str
    description: str = ""
    max_points: float
    # For questions with a known answer (quizzes). Excluded from model_dump(), like the solution.
    expected_answer: str = Field(default="", exclude=True)


class GradingSpec(BaseModel):
    assignment_id: str
    title: str = ""
    description: str = ""
    criteria: list[Criterion]
    guidance: str = ""
    skill_level: str = ""  # what students are expected to know by this assignment
    model: str = config.DEFAULT_MODEL  # every submission for the assignment is graded by this model
    source: str = ""  # "built-in", "upload" or the curriculum designer lab it was imported from
    # Excluded from model_dump(), so the solution never reaches an API response.
    reference_solution: list[SubmissionFile] = Field(default=[], exclude=True)
    materials: list[SubmissionFile] = Field(default=[], exclude=True)

    @field_validator("model")
    @classmethod
    def _check_model(cls, model: str) -> str:
        if model not in SUPPORTED_MODELS:
            raise ValueError(f"unsupported model {model!r}; choose one of {', '.join(SUPPORTED_MODELS)}")
        return model

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


def check_id(assignment_id: str) -> None:
    if not _ID_PATTERN.match(assignment_id):
        raise SpecNotFoundError(f"Invalid assignment id {assignment_id!r}")


def _uploaded_root() -> Path:
    return Path(config.DATA_DIR) / "assignments"


def _uploaded_dir(assignment_id: str) -> Path:
    check_id(assignment_id)
    return _uploaded_root() / assignment_id


def _assignment_dir(assignment_id: str) -> Path:
    uploaded = _uploaded_dir(assignment_id)
    if (uploaded / "spec.json").is_file():
        return uploaded
    return Path(config.ASSIGNMENTS_DIR) / assignment_id


def _read_texts(directory: Path) -> list[SubmissionFile]:
    if not directory.is_dir():
        return []
    return [
        SubmissionFile(filename=path.relative_to(directory).as_posix(), content=path.read_text(encoding="utf-8"))
        for path in sorted(p for p in directory.rglob("*") if p.is_file())
    ]


def load_spec_with_hash(assignment_id: str) -> tuple[GradingSpec, str]:
    """Load a spec and return (spec, sha256 over spec.json, the solution and the materials)."""
    directory = _assignment_dir(assignment_id)
    spec_path = directory / "spec.json"
    if not spec_path.is_file():
        raise SpecNotFoundError(f"No grading spec for assignment {assignment_id!r}")

    spec_text = spec_path.read_text(encoding="utf-8")
    digest = hashlib.sha256(spec_text.encode("utf-8"))
    solution = _read_texts(directory / "solution")
    materials = _read_texts(directory / "materials")
    for prefix, files in (("solution/", solution), ("materials/", materials)):
        for f in files:
            digest.update((prefix + f.filename).encode("utf-8"))
            digest.update(f.content.encode("utf-8"))

    data = json.loads(spec_text)
    data.setdefault("source", "built-in")
    data["assignment_id"] = assignment_id
    data["reference_solution"] = solution
    data["materials"] = materials
    return GradingSpec(**data), digest.hexdigest()


def load_spec(assignment_id: str) -> GradingSpec:
    return load_spec_with_hash(assignment_id)[0]


def list_specs() -> list[GradingSpec]:
    ids: set[str] = set()
    for root in (Path(config.ASSIGNMENTS_DIR), _uploaded_root()):
        if root.is_dir():
            ids.update(e.name for e in root.iterdir() if (e / "spec.json").is_file() and _ID_PATTERN.match(e.name))
    return [load_spec(assignment_id) for assignment_id in sorted(ids)]


# ── Instructor-provided specs ────────────────────────────────────────────────

def _write(path: Path, data: bytes) -> None:
    """Write through a temporary file, so a crash never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _require_uploaded(assignment_id: str) -> Path:
    directory = _uploaded_dir(assignment_id)
    if not (directory / "spec.json").is_file():
        raise SpecNotFoundError(f"Create assignment {assignment_id!r} with PUT /assignments/{assignment_id} first")
    return directory


def _safe_name(filename: str) -> str:
    name = PurePosixPath(filename.replace("\\", "/")).name
    if not _FILE_NAME_PATTERN.match(name) or name.startswith("."):
        raise UnsupportedFileError(f"invalid file name {filename!r}")
    return name


def _convert(files: list[tuple[str, bytes]]) -> list[tuple[str, bytes, str]]:
    """(name, original bytes, text) for each upload. Raises before anything is written if one file is bad."""
    return [(name, data, extract_text(name, data)) for name, data in ((_safe_name(n), d) for n, d in files)]


def _save_files(directory: Path, kind: str, converted: list[tuple[str, bytes, str]]) -> list[str]:
    for name, data, text in converted:
        _write(directory / "originals" / kind / name, data)
        _write(directory / kind / text_name(name), text.encode("utf-8"))
    return [name for name, _, _ in converted]


def save_spec(spec: GradingSpec) -> None:
    """Create or replace an instructor-provided spec. Its solution and materials are kept."""
    data = spec.model_dump(exclude={"assignment_id", "max_score"})
    for saved, criterion in zip(data["criteria"], spec.criteria):
        if criterion.expected_answer:
            saved["expected_answer"] = criterion.expected_answer
    _write(_uploaded_dir(spec.assignment_id) / "spec.json", json.dumps(data, indent=2).encode("utf-8"))


def replace_solution(assignment_id: str, files: list[tuple[str, bytes]]) -> list[str]:
    directory = _require_uploaded(assignment_id)
    converted = _convert(files)
    shutil.rmtree(directory / "solution", ignore_errors=True)
    shutil.rmtree(directory / "originals" / "solution", ignore_errors=True)
    return _save_files(directory, "solution", converted)


def add_materials(assignment_id: str, files: list[tuple[str, bytes]]) -> list[str]:
    directory = _require_uploaded(assignment_id)
    return _save_files(directory, "materials", _convert(files))


def save_material_text(assignment_id: str, name: str, text: str) -> None:
    """Store material that has no original file, such as text imported from the curriculum designer."""
    _write(_require_uploaded(assignment_id) / "materials" / _safe_name(name), text.encode("utf-8"))


def list_materials(assignment_id: str) -> list[dict]:
    directory = _require_uploaded(assignment_id)
    originals_dir = directory / "originals" / "materials"
    originals = {p.name for p in originals_dir.iterdir()} if originals_dir.is_dir() else set()
    materials_dir = directory / "materials"
    entries = []
    for path in sorted(materials_dir.glob("*")) if materials_dir.is_dir() else []:
        name = path.name
        if name.endswith(".txt") and name[:-4] in originals:
            name = name[:-4]
        entries.append({
            "name": name,
            "characters": len(path.read_text(encoding="utf-8")),
            "uploaded_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        })
    return entries


def delete_material(assignment_id: str, name: str) -> None:
    directory = _require_uploaded(assignment_id)
    name = _safe_name(name)
    paths = [directory / "materials" / text_name(name), directory / "originals" / "materials" / name]
    if not any(p.is_file() for p in paths):
        raise SpecNotFoundError(f"No material {name!r} for assignment {assignment_id!r}")
    for p in paths:
        p.unlink(missing_ok=True)


def delete_spec(assignment_id: str) -> None:
    """Delete an instructor-provided spec. Built-in examples live in the repo and cannot be deleted."""
    directory = _uploaded_dir(assignment_id)
    if not (directory / "spec.json").is_file():
        if (Path(config.ASSIGNMENTS_DIR) / assignment_id / "spec.json").is_file():
            raise ValueError(f"{assignment_id!r} is a built-in example and cannot be deleted")
        raise SpecNotFoundError(f"No grading spec for assignment {assignment_id!r}")
    shutil.rmtree(directory)
