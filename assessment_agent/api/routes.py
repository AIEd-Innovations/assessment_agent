from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile

from assessment_agent import config
from assessment_agent.agents.orchestrator import assess_submission
from assessment_agent.auth import Instructor, require_instructor
from assessment_agent.database import agent_repo, owner_repo
from assessment_agent.llm import LLMAuthError, SUPPORTED_MODELS
from assessment_agent.models import AssessmentRequest, AssessmentResult, RegradeRequest, ResultStatus, ReviewRequest, SubmissionFile
from assessment_agent.spec import SpecNotFoundError

router = APIRouter(tags=["assessment"], dependencies=[Depends(require_instructor)])
ApiKey = Header(None, alias="X-LLM-API-Key")


async def _read_text_upload(upload: UploadFile) -> str:
    try:
        return (await upload.read()).decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, f"{upload.filename} is not a UTF-8 text file")


async def _grade(body: AssessmentRequest, repo, api_key: str | None, instructions: str = "") -> AssessmentResult:
    try:
        return await assess_submission(body, repo, api_key, instructions)
    except SpecNotFoundError as exc:
        raise HTTPException(404, str(exc))
    except LLMAuthError as exc:
        raise HTTPException(401, str(exc))


async def _assess(request: Request, course_id: str, body: AssessmentRequest, api_key: str | None, instructor: Instructor | None) -> AssessmentResult:
    if not body.files:
        raise HTTPException(400, "At least one file is required")
    if sum(len(f.content) for f in body.files) > config.MAX_UPLOAD_CHARS:
        raise HTTPException(400, f"Submission exceeds {config.MAX_UPLOAD_CHARS} characters")
    owner_repo(request, course_id, instructor)
    result = await _grade(body, agent_repo(request, course_id), api_key)
    return agent_repo(request, course_id).insert_result(result.model_dump(), submitted_files=[file.model_dump() for file in body.files])


@router.post("/submit", response_model=AssessmentResult)
async def submit_assessment(request: Request, course_id: str = Form(...), student_id: str = Form(...), assignment_id: str = Form(...), files: list[UploadFile] = File(...), api_key: str | None = ApiKey, instructor: Instructor | None = Depends(require_instructor)):
    submission = [SubmissionFile(filename=f.filename or f"file{i + 1}", content=await _read_text_upload(f)) for i, f in enumerate(files)]
    return await _assess(request, course_id, AssessmentRequest(student_id=student_id, assignment_id=assignment_id, files=submission), api_key, instructor)


@router.post("/submit-json", response_model=AssessmentResult)
async def submit_assessment_json(request: Request, course_id: str, body: AssessmentRequest, api_key: str | None = ApiKey, instructor: Instructor | None = Depends(require_instructor)):
    return await _assess(request, course_id, body, api_key, instructor)


@router.get("/models")
async def list_models(request: Request, course_id: str, instructor: Instructor | None = Depends(require_instructor)):
    owner_repo(request, course_id, instructor)
    return {"default": config.DEFAULT_MODEL, "models": [asdict(m) for m in SUPPORTED_MODELS.values()]}


@router.get("/results")
async def list_results(request: Request, course_id: str, instructor: Instructor | None = Depends(require_instructor), student_id: str | None = None, assignment_id: str | None = None, status: Optional[ResultStatus] = None, latest: bool = False):
    repo, _ = owner_repo(request, course_id, instructor)
    return repo.list_results(student_id=student_id, assignment_id=assignment_id, status=status, latest=latest)


@router.get("/results/{submission_id}")
async def get_result(request: Request, submission_id: str, course_id: str, instructor: Instructor | None = Depends(require_instructor)):
    result = owner_repo(request, course_id, instructor)[0].get_result(submission_id)
    if result is None:
        raise HTTPException(404, f"Submission '{submission_id}' not found")
    return result


@router.post("/results/{submission_id}/regrade", response_model=AssessmentResult)
async def regrade_result(request: Request, submission_id: str, course_id: str, regrade: RegradeRequest | None = None, api_key: str | None = ApiKey, instructor: Instructor | None = Depends(require_instructor)):
    repo, _ = owner_repo(request, course_id, instructor)
    original = repo.get_result(submission_id)
    if original is None:
        raise HTTPException(404, f"Submission '{submission_id}' not found")
    files = repo.get_submitted_files(submission_id)
    if files is None:
        raise HTTPException(409, "The submitted files were not stored for this result; resubmit to grade it again")
    instructions = regrade.instructions.strip() if regrade else ""
    body = AssessmentRequest(student_id=original["student_id"], assignment_id=original["assignment_id"], files=[SubmissionFile(**file) for file in files])
    result = await _grade(body, agent_repo(request, course_id), api_key, instructions)
    if result.score is None:
        raise HTTPException(502, "Regrading failed, so no new result was saved; the previous grade is unchanged")
    result.regrade_of, result.regrade_instructions = submission_id, instructions
    return agent_repo(request, course_id).insert_result(result.model_dump(), submitted_files=files)


@router.post("/results/{submission_id}/review")
async def review_result(request: Request, submission_id: str, course_id: str, review: ReviewRequest, instructor: Instructor | None = Depends(require_instructor)):
    repo, actor_id = owner_repo(request, course_id, instructor)
    try:
        result = repo.review_result(submission_id, final_score=review.final_score, notes=review.notes, reviewed_by=actor_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if result is None:
        raise HTTPException(404, f"Submission '{submission_id}' not found")
    return result


@router.get("/results/{submission_id}/provenance")
async def get_provenance(request: Request, submission_id: str, course_id: str, instructor: Instructor | None = Depends(require_instructor)):
    provenance = owner_repo(request, course_id, instructor)[0].get_provenance(submission_id)
    if provenance is None:
        raise HTTPException(404, f"No provenance record for submission '{submission_id}'")
    return provenance
