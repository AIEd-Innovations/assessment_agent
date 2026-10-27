import hashlib
import logging

from assessment_agent.models import (
    AssessmentResult,
    AssessmentRequest,
    ProvenanceCollector,
    SubmissionFile,
)
from assessment_agent.agents.grader import grade_submission, total_score
from assessment_agent.llm import get_llm_provider
from assessment_agent.spec import load_spec_with_hash


logger = logging.getLogger(__name__)


def mock_reason(model: str) -> str:
    return (
        "No API key was provided, so this is a mock grade from the offline test model, not a real "
        f"assessment. Grade it again with an API key for {model}."
    )


def hash_files(files: list[SubmissionFile]) -> str:
    digest = hashlib.sha256()
    for f in files:
        digest.update(f.filename.encode("utf-8") + b"\0" + f.content.encode("utf-8") + b"\0")
    return digest.hexdigest()


async def assess_submission(request: AssessmentRequest, api_key: str | None = None) -> AssessmentResult:
    """
    Grade a submission against its assignment's spec.

    One LLM call scores every rubric criterion and writes the feedback. The
    score is the sum of the criterion scores. Anything the grader is unsure of
    marks the result for instructor review.

    The assignment's spec names the model; api_key is the teacher's key for that
    model's vendor. Without a key the offline mock model grades it, and the
    result is marked as a mock grade.

    Raises SpecNotFoundError if the assignment has no spec, and LLMAuthError if
    the provider rejects the key.
    """
    spec, spec_hash = load_spec_with_hash(request.assignment_id)
    mock = not api_key
    if mock:
        logger.warning("No API key for %s: grading with the mock model", request.assignment_id)
    provider = get_llm_provider(spec.model, api_key)
    collector = ProvenanceCollector(
        model_id=provider.model_id,
        spec_hash=spec_hash,
        submission_hash=hash_files(request.files),
    )

    grading = await grade_submission(spec, request.files, provider, collector)

    reasons = [mock_reason(spec.model)] if mock else []
    reasons += grading.review_reasons

    result = AssessmentResult(
        student_id=request.student_id,
        assignment_id=request.assignment_id,
        files=[f.filename for f in request.files],
        model=provider.model_id,
        mock=mock,
        criteria=grading.criteria,
        score=total_score(grading.criteria) if grading.succeeded else None,
        max_score=spec.max_score,
        feedback=grading.feedback,
        status="needs_review" if reasons else "ai_graded",
        review_reasons=reasons,
    )

    result.provenance = collector.build()
    return result
