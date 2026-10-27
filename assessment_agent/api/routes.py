from datetime import datetime
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from assessment_agent.models import (
    AssessmentRequest,
    AssessmentResult,
    ResultStatus,
    ReviewRequest,
    SubmissionFile,
)
from assessment_agent.agents.orchestrator import assess_submission
from assessment_agent.interfaces.integrity_guardian import get_anomaly_reports
from assessment_agent.spec import SpecNotFoundError, list_specs, load_spec
from assessment_agent import config, persistence

router = APIRouter(tags=["assessment"])


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


async def _assess(request: AssessmentRequest) -> AssessmentResult:
    if not request.files:
        raise HTTPException(400, "At least one file is required")
    if sum(len(f.content) for f in request.files) > config.MAX_UPLOAD_CHARS:
        raise HTTPException(400, f"Submission exceeds {config.MAX_UPLOAD_CHARS} characters")
    try:
        result = await assess_submission(request)
    except SpecNotFoundError as exc:
        raise HTTPException(404, str(exc))
    _save_result(result)
    return result


@router.post("/submit", response_model=AssessmentResult)
async def submit_assessment(
    student_id: str = Form(...),
    assignment_id: str = Form(...),
    files: list[UploadFile] = File(...),
):
    """Submit any number of text files (code in any language, reports, notes)."""
    submission = [
        SubmissionFile(filename=f.filename or f"file{i + 1}", content=await _read_text_upload(f))
        for i, f in enumerate(files)
    ]
    return await _assess(AssessmentRequest(
        student_id=student_id, assignment_id=assignment_id, files=submission,
    ))


@router.post("/submit-json", response_model=AssessmentResult)
async def submit_assessment_json(request: AssessmentRequest):
    """Submit as JSON: student_id, assignment_id and files [{filename, content}]."""
    return await _assess(request)


@router.get("/assignments")
async def list_assignments():
    """List assignments that have a grading spec."""
    return [
        {
            "assignment_id": spec.assignment_id,
            "title": spec.title,
            "num_criteria": len(spec.criteria),
            "max_score": spec.max_score,
        }
        for spec in list_specs()
    ]


@router.get("/assignments/{assignment_id}/rubric")
async def get_rubric(assignment_id: str):
    """Get an assignment's rubric and guidance. Never includes the reference solution."""
    try:
        return load_spec(assignment_id).model_dump()
    except SpecNotFoundError as exc:
        raise HTTPException(404, str(exc))


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


@router.get("/anomalies")
async def list_anomalies(reviewed: bool = None):
    """Get flagged anomaly reports."""
    return get_anomaly_reports(reviewed=reviewed)
