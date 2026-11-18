from contextlib import contextmanager

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel

from aied_db import AgentConfig as MongoAgentConfig, Role
from assessment_agent import config
from assessment_agent.agent_config import AgentConfig
from assessment_agent.auth import Instructor, require_instructor
from assessment_agent.curriculum import CurriculumError, import_lab
from assessment_agent.database import owner_repo
from assessment_agent.extract import UnsupportedFileError, extract_text
from assessment_agent.llm.models import SUPPORTED_MODELS
from assessment_agent.spec import Criterion, GradingSpec, SpecNotFoundError

router = APIRouter(tags=["assignments"], dependencies=[Depends(require_instructor)])


class SpecInput(BaseModel):
    title: str = ""
    description: str = ""
    criteria: list[Criterion]
    guidance: str = ""
    model: str = config.DEFAULT_MODEL


@contextmanager
def _http_errors():
    try:
        yield
    except SpecNotFoundError as exc:
        raise HTTPException(404, str(exc))
    except CurriculumError as exc:
        raise HTTPException(exc.status, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


async def _files(files: list[UploadFile]) -> list[dict]:
    limit = config.MAX_MATERIAL_FILE_MB * 1024 * 1024
    stored = []
    for upload in files:
        data = await upload.read()
        if len(data) > limit:
            raise HTTPException(400, f"{upload.filename} exceeds {config.MAX_MATERIAL_FILE_MB} MB")
        name = upload.filename or "upload"
        try:
            text = extract_text(name, data)
        except UnsupportedFileError as exc:
            raise HTTPException(400, str(exc))
        stored.append({"filename": name, "content_type": upload.content_type, "size_bytes": len(data), "extracted_text": text})
    return stored


def _repo(request: Request, course_id: str, instructor: Instructor | None):
    return owner_repo(request, course_id, instructor)


@router.get("/assignments")
async def list_assignments(request: Request, course_id: str, instructor: Instructor | None = Depends(require_instructor)):
    repo, _ = _repo(request, course_id, instructor)
    return [{"assignment_id": item["assignment_id"], "title": item.get("title", ""), "num_criteria": len(item.get("criteria", [])), "max_score": item.get("max_score", 0), "model": item.get("model", ""), "source": item.get("source", "")} for item in repo.list_assignments()]


@router.get("/assignments/{assignment_id}/rubric")
async def get_rubric(request: Request, assignment_id: str, course_id: str, instructor: Instructor | None = Depends(require_instructor)):
    assignment = _repo(request, course_id, instructor)[0].get_assignment(assignment_id)
    if assignment is None:
        raise HTTPException(404, f"No grading spec for assignment {assignment_id!r}")
    # Keep the original endpoint shape while ensuring expected quiz answers
    # and reference solutions never leave the service.
    return {
        **{key: assignment.get(key) for key in ("assignment_id", "title", "description", "guidance", "model", "source", "max_score")},
        "criteria": [{key: value for key, value in criterion.items() if key != "expected_answer"} for criterion in assignment.get("criteria", [])],
    }


def _config(repo, course_id: str, assignment_id: str):
    return MongoAgentConfig(repo._db, "assessment", course_id=course_id, assignment_id=assignment_id)


@router.get("/assignments/{assignment_id}/agent-config", response_model=AgentConfig)
async def get_agent_config(request: Request, assignment_id: str, course_id: str, instructor: Instructor | None = Depends(require_instructor)):
    repo, _ = _repo(request, course_id, instructor)
    if repo.get_assignment(assignment_id) is None:
        raise HTTPException(404, f"No grading spec for assignment {assignment_id!r}")
    settings = _config(repo, course_id, assignment_id)
    return AgentConfig(tone=settings.get("feedback.tone", "Neutral"), feedback_detail=settings.get("feedback.detail", "Standard"), partial_credit=settings.get("grading.partial_credit", "Balanced"), notes=settings.get("grading.notes", ""))


@router.put("/assignments/{assignment_id}/agent-config", response_model=AgentConfig)
async def put_agent_config(request: Request, assignment_id: str, course_id: str, body: AgentConfig, instructor: Instructor | None = Depends(require_instructor)):
    repo, actor_id = _repo(request, course_id, instructor)
    if repo.get_assignment(assignment_id) is None:
        raise HTTPException(404, f"No grading spec for assignment {assignment_id!r}")
    settings = _config(repo, course_id, assignment_id)
    try:
        for key, value in {"feedback.tone": body.tone, "feedback.detail": body.feedback_detail, "grading.partial_credit": body.partial_credit, "grading.notes": body.notes}.items():
            settings.set_assignment_override(key, value, set_by=actor_id, role=Role.INSTRUCTOR.value)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return body


@router.post("/assignments/import/{lab_id}")
async def import_from_curriculum_designer(request: Request, lab_id: str, course_id: str, assignment_id: str | None = None, instructor: Instructor | None = Depends(require_instructor)):
    repo, _ = _repo(request, course_id, instructor)
    with _http_errors():
        return await import_lab(repo, lab_id, course_id, assignment_id)


@router.put("/assignments/{assignment_id}")
async def put_spec(request: Request, assignment_id: str, course_id: str, body: SpecInput, instructor: Instructor | None = Depends(require_instructor)):
    repo, _ = _repo(request, course_id, instructor)
    with _http_errors():
        spec = GradingSpec(assignment_id=assignment_id, source="upload", **dict(body))
        stored = spec.model_dump(exclude={"reference_solution", "materials", "agent_config", "max_score"})
        for row, criterion in zip(stored["criteria"], spec.criteria):
            if criterion.expected_answer:
                row["expected_answer"] = criterion.expected_answer
        return repo.upsert_assignment(stored)


@router.delete("/assignments/{assignment_id}", status_code=204)
async def delete_assignment(request: Request, assignment_id: str, course_id: str, instructor: Instructor | None = Depends(require_instructor)):
    repo, _ = _repo(request, course_id, instructor)
    if not repo.delete_assignment(assignment_id):
        raise HTTPException(404, f"No grading spec for assignment {assignment_id!r}")
    repo._db["agent_configs"].delete_many({"agent": "assessment", "course_id": course_id, "assignment_id": assignment_id})
    return Response(status_code=204)


@router.put("/assignments/{assignment_id}/solution")
async def put_solution(request: Request, assignment_id: str, course_id: str, files: list[UploadFile] = File(...), instructor: Instructor | None = Depends(require_instructor)):
    repo, _ = _repo(request, course_id, instructor)
    if repo.get_assignment(assignment_id) is None:
        raise HTTPException(404, f"No grading spec for assignment {assignment_id!r}")
    return {"assignment_id": assignment_id, "files": [file["filename"] for file in repo.replace_solution(assignment_id, await _files(files))]}


@router.post("/assignments/{assignment_id}/materials")
async def add_materials(request: Request, assignment_id: str, course_id: str, files: list[UploadFile] = File(...), instructor: Instructor | None = Depends(require_instructor)):
    repo, _ = _repo(request, course_id, instructor)
    if repo.get_assignment(assignment_id) is None:
        raise HTTPException(404, f"No grading spec for assignment {assignment_id!r}")
    added = [repo.add_material(assignment_id, file) for file in await _files(files)]
    materials = repo.list_materials(assignment_id)
    total = sum(item.get("char_count", 0) for item in materials)
    result = {"added": [item["filename"] for item in added], "materials": materials, "total_characters": total}
    if total > config.MAX_MATERIAL_CHARS:
        result["warning"] = f"The materials total {total} characters; only the first {config.MAX_MATERIAL_CHARS} are given to the grader."
    return result


@router.get("/assignments/{assignment_id}/materials")
async def get_materials(request: Request, assignment_id: str, course_id: str, instructor: Instructor | None = Depends(require_instructor)):
    repo, _ = _repo(request, course_id, instructor)
    if repo.get_assignment(assignment_id) is None:
        raise HTTPException(404, f"No grading spec for assignment {assignment_id!r}")
    return repo.list_materials(assignment_id)


@router.delete("/assignments/{assignment_id}/materials/{name}", status_code=204)
async def delete_material(request: Request, assignment_id: str, name: str, course_id: str, instructor: Instructor | None = Depends(require_instructor)):
    repo, _ = _repo(request, course_id, instructor)
    if not repo.delete_material(assignment_id, name):
        raise HTTPException(404, f"No material {name!r} for assignment {assignment_id!r}")
    return Response(status_code=204)
