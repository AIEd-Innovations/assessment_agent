import asyncio
import hashlib

from assessment_agent.models import (
    AssessmentResult,
    AssessmentRequest,
    ProvenanceCollector,
    SubmissionFile,
)
from assessment_agent.agents.grader import grade_submission, total_score
from assessment_agent.agents.anomaly_detector import detect_anomalies
from assessment_agent.interfaces.integrity_guardian import report_anomaly
from assessment_agent.llm import get_llm_provider
from assessment_agent.spec import load_spec_with_hash


def hash_files(files: list[SubmissionFile]) -> str:
    digest = hashlib.sha256()
    for f in files:
        digest.update(f.filename.encode("utf-8") + b"\0" + f.content.encode("utf-8") + b"\0")
    return digest.hexdigest()


async def assess_submission(request: AssessmentRequest) -> AssessmentResult:
    """
    Grade a submission against its assignment's spec.

    One LLM call scores every rubric criterion and writes the feedback; the
    integrity check runs alongside it. The score is the sum of the criterion
    scores. Anything the grader is unsure of, or a medium/high integrity risk,
    marks the result for instructor review.

    Raises SpecNotFoundError if the assignment has no spec.
    """
    spec, spec_hash = load_spec_with_hash(request.assignment_id)
    provider = get_llm_provider()
    collector = ProvenanceCollector(
        model_id=provider.model_id,
        spec_hash=spec_hash,
        submission_hash=hash_files(request.files),
    )

    grading, anomaly = await asyncio.gather(
        grade_submission(spec, request.files, provider, collector),
        detect_anomalies(request.files, spec, provider, collector),
    )

    reasons = list(grading.review_reasons)
    if anomaly.overall_risk in ("medium", "high"):
        reasons.append(f"The integrity check rated the risk as {anomaly.overall_risk}.")

    result = AssessmentResult(
        student_id=request.student_id,
        assignment_id=request.assignment_id,
        files=[f.filename for f in request.files],
        criteria=grading.criteria,
        score=total_score(grading.criteria) if grading.succeeded else None,
        max_score=spec.max_score,
        feedback=grading.feedback,
        anomaly_report=anomaly,
        status="needs_review" if reasons else "ai_graded",
        review_reasons=reasons,
    )

    if anomaly.flags:
        report_anomaly(
            submission_id=result.submission_id,
            student_id=request.student_id,
            assignment_id=request.assignment_id,
            anomaly_report=anomaly,
        )

    result.provenance = collector.build()
    return result
