from contextlib import contextmanager

from fastapi import APIRouter, File, HTTPException, Response, UploadFile
from pydantic import BaseModel

from assessment_agent import config, spec as specs
from assessment_agent.curriculum import CurriculumError, import_lab
from assessment_agent.spec import Criterion, GradingSpec, SpecNotFoundError

# TODO: anyone who can reach the agent can change grading materials. Restrict the
# write endpoints below to instructors once there is a login.
router = APIRouter(tags=["assignments"])


class SpecInput(BaseModel):
    title: str = ""
    description: str = ""
    criteria: list[Criterion]
    guidance: str = ""
    skill_level: str = ""
    model: str = config.DEFAULT_MODEL


@contextmanager
def _http_errors():
    try:
        yield
    except SpecNotFoundError as exc:
        raise HTTPException(404, str(exc))
    except CurriculumError as exc:
        raise HTTPException(exc.status, str(exc))
    except ValueError as exc:  # invalid specs, unsupported files, built-in examples
        raise HTTPException(400, str(exc))


async def _read_files(files: list[UploadFile]) -> list[tuple[str, bytes]]:
    limit = config.MAX_MATERIAL_FILE_MB * 1024 * 1024
    read = []
    for f in files:
        data = await f.read()
        if len(data) > limit:
            raise HTTPException(400, f"{f.filename} exceeds {config.MAX_MATERIAL_FILE_MB} MB")
        read.append((f.filename or "", data))
    return read


@router.get("/assignments")
async def list_assignments():
    """List assignments that have a grading spec."""
    return [
        {
            "assignment_id": spec.assignment_id,
            "title": spec.title,
            "num_criteria": len(spec.criteria),
            "max_score": spec.max_score,
            "model": spec.model,
            "source": spec.source,
        }
        for spec in specs.list_specs()
    ]


@router.get("/assignments/{assignment_id}/rubric")
async def get_rubric(assignment_id: str):
    """Get an assignment's rubric and guidance. Never includes the solution, materials or expected answers."""
    with _http_errors():
        return specs.load_spec(assignment_id).model_dump()


@router.post("/assignments/import/{lab_id}")
async def import_from_curriculum_designer(lab_id: str, assignment_id: str | None = None):
    """Copy an approved curriculum designer lab into an assignment (and its quiz into {assignment_id}-quiz)."""
    with _http_errors():
        return await import_lab(lab_id, assignment_id)


@router.put("/assignments/{assignment_id}")
async def put_spec(assignment_id: str, body: SpecInput):
    """Create or replace an assignment's rubric and settings. Its solution and materials are kept."""
    with _http_errors():
        spec = GradingSpec(assignment_id=assignment_id, source="upload", **dict(body))
        specs.save_spec(spec)
        return spec.model_dump()


@router.delete("/assignments/{assignment_id}", status_code=204)
async def delete_assignment(assignment_id: str):
    """Delete an uploaded assignment with its solution and materials. Built-in examples cannot be deleted."""
    with _http_errors():
        specs.delete_spec(assignment_id)
    return Response(status_code=204)


@router.put("/assignments/{assignment_id}/solution")
async def put_solution(assignment_id: str, files: list[UploadFile] = File(...)):
    """Replace the reference solution or answer key: text, PDF, .docx or .ipynb files. Never returned by the API."""
    uploads = await _read_files(files)
    with _http_errors():
        return {"assignment_id": assignment_id, "files": specs.replace_solution(assignment_id, uploads)}


@router.post("/assignments/{assignment_id}/materials")
async def add_materials(assignment_id: str, files: list[UploadFile] = File(...)):
    """Add course materials (lecture notes, handouts): text, PDF, .docx or .ipynb files."""
    uploads = await _read_files(files)
    with _http_errors():
        added = specs.add_materials(assignment_id, uploads)
        materials = specs.list_materials(assignment_id)
    total = sum(m["characters"] for m in materials)
    result = {"added": added, "materials": materials, "total_characters": total}
    if total > config.MAX_MATERIAL_CHARS:
        result["warning"] = (
            f"The materials total {total} characters; only the first {config.MAX_MATERIAL_CHARS} are given to the grader."
        )
    return result


@router.get("/assignments/{assignment_id}/materials")
async def get_materials(assignment_id: str):
    """List an assignment's course materials (names and sizes, not their text)."""
    with _http_errors():
        return specs.list_materials(assignment_id)


@router.delete("/assignments/{assignment_id}/materials/{name}", status_code=204)
async def delete_material(assignment_id: str, name: str):
    with _http_errors():
        specs.delete_material(assignment_id, name)
    return Response(status_code=204)
