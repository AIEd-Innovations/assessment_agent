from dataclasses import asdict
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, Header, HTTPException

from assessment_agent.models import (
    AssessmentRequest,
    AssessmentResult,
    ResultStatus,
    ReviewRequest,
    SubmissionFile,
)
from assessment_agent.agents.orchestrator import assess_submission
from assessment_agent.llm import SUPPORTED_MODELS, LLMAuthError
from assessment_agent.spec import SpecNotFoundError
from assessment_agent import config, persistence

router = APIRouter(tags=["assessment"])

# The teacher's API key for the assignment's model vendor. Used for this request only, never stored or logged.
ApiKey = Header(None, alias="X-LLM-API-Key")


def _save_result(result: AssessmentResult) -> None:
    """Persist assessment result to JSON file."""
    persistence.append_json(config.RESULTS_FILE, result.model_dump())


def _get_results() -> list[dict]:
    return persistence.read_json(config.RESULTS_FILE)


async def _read_text_upload(upload: UploadFile) -> str:
    """Read an UploadFile as UTF-8 text. Raise HTTP 400 on bad bytes."""
    try:
        return (await upload.read()).decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, f"{upload.filename} is not a UTF-8 text file")


async def _assess(request: AssessmentRequest, api_key: str | None) -> AssessmentResult:
    if not request.files:
        raise HTTPException(400, "At least one file is required")
    if sum(len(f.content) for f in request.files) > config.MAX_UPLOAD_CHARS:
        raise HTTPException(400, f"Submission exceeds {config.MAX_UPLOAD_CHARS} characters")
    try:
        result = await assess_submission(request, api_key)
    except SpecNotFoundError as exc:
        raise HTTPException(404, str(exc))
    except LLMAuthError as exc:
        raise HTTPException(401, str(exc))
    _save_result(result)
    return result


@router.post("/submit", response_model=AssessmentResult)
async def submit_assessment(
    student_id: str = Form(...),
    assignment_id: str = Form(...),
    files: list[UploadFile] = File(...),
    api_key: str | None = ApiKey,
):
    """Submit any number of text files (code in any language, reports, notes).

    Send the teacher's API key in the X-LLM-API-Key header. Without it the mock model grades the submission."""
    submission = [
        SubmissionFile(filename=f.filename or f"file{i + 1}", content=await _read_text_upload(f))
        for i, f in enumerate(files)
    ]
    return await _assess(AssessmentRequest(
        student_id=student_id, assignment_id=assignment_id, files=submission,
    ), api_key)


@router.post("/submit-json", response_model=AssessmentResult)
async def submit_assessment_json(request: AssessmentRequest, api_key: str | None = ApiKey):
    """Submit as JSON: student_id, assignment_id and files [{filename, content}]. API key as for /submit."""
    return await _assess(request, api_key)


@router.get("/models")
async def list_models():
    """Models an assignment can be graded with, and the default for specs that name none."""
    return {"default": config.DEFAULT_MODEL, "models": [asdict(m) for m in SUPPORTED_MODELS.values()]}


@router.get("/results")
async def list_results(
    student_id: str = None,
    assignment_id: str = None,
    status: Optional[ResultStatus] = None,
):
    """List assessment results with optional filters."""
    results = _get_results()
    if student_id:
        results = [r for r in results if r["student_id"] == student_id]
    if assignment_id:
        results = [r for r in results if r["assignment_id"] == assignment_id]
    if status:
        results = [r for r in results if r.get("status") == status]
    return results


@router.get("/results/{submission_id}")
async def get_result(submission_id: str):
    """Get a specific assessment result."""
    results = _get_results()
    for r in results:
        if r["submission_id"] == submission_id:
            return r
    raise HTTPException(404, f"Submission '{submission_id}' not found")


@router.post("/results/{submission_id}/review")
async def review_result(submission_id: str, review: ReviewRequest):
    """Record the instructor's grade. It replaces the AI score."""
    # The curriculum designer's rubric still reserves a 10% manual_weight for the instructor.
    # If that survives its rubric redesign, this becomes an adjustment rather than a replacement.
    target = next((r for r in _get_results() if r["submission_id"] == submission_id), None)
    if target is None:
        raise HTTPException(404, f"Submission '{submission_id}' not found")

    if review.final_score < 0:
        raise HTTPException(400, "final_score cannot be negative")
    # Results stored before rubric grading have no max_score.
    max_score = target.get("max_score")
    if max_score is not None and review.final_score > max_score:
        raise HTTPException(400, f"final_score cannot exceed {max_score:g}")

    updates = {
        "final_score": review.final_score,
        "instructor_notes": review.notes,
        "status": "instructor_graded",
        "reviewed_at": datetime.now().isoformat(),
    }
    persistence.update_json(config.RESULTS_FILE, "submission_id", submission_id, updates)
    return {**target, **updates}


@router.get("/results/{submission_id}/provenance")
async def get_provenance(submission_id: str):
    """Get the provenance record for a submission: model, prompt and input hashes, call timings."""
    results = _get_results()
    for r in results:
        if r["submission_id"] == submission_id:
            provenance = r.get("provenance")
            if provenance is None:
                raise HTTPException(404, f"No provenance record for submission '{submission_id}'")
            return provenance
    raise HTTPException(404, f"Submission '{submission_id}' not found")

