import json
import logging
import secrets
from dataclasses import dataclass, field

from assessment_agent.models import (
    CriterionScore,
    FeedbackReport,
    LLMCallRecord,
    ProvenanceCollector,
    SubmissionFile,
)
from assessment_agent.llm import LLMAuthError, LLMProvider
from assessment_agent.spec import GradingSpec
from assessment_agent.prompt_loader import load_prompt
from assessment_agent import config

logger = logging.getLogger(__name__)

GRADING_FAILED = "Automatic grading failed; grade this submission manually."
TRUNCATED = "The submission was too long and was cut before grading."
ATTEMPTS = 2


class GradingOutputError(ValueError):
    pass


@dataclass
class GradingOutcome:
    criteria: list[CriterionScore] = field(default_factory=list)
    feedback: FeedbackReport | None = None
    review_reasons: list[str] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        return bool(self.criteria)


def new_boundary() -> str:
    """A per-call delimiter, so submitted text cannot fake the end of the submission."""
    return f"<<<SUBMISSION {secrets.token_hex(8)}>>>"


def format_files(files: list[SubmissionFile], limit: int | None = None) -> tuple[str, bool]:
    """Render files for a prompt. Returns (text, truncated)."""
    text = "\n\n".join(f"=== FILE: {f.filename} ===\n{f.content}" for f in files)
    if limit is not None and len(text) > limit:
        return text[:limit] + "\n[truncated]", True
    return text, False


def total_score(criteria: list[CriterionScore]) -> float:
    return round(sum(c.score for c in criteria), 2)


def _criteria_block(spec: GradingSpec) -> str:
    return "\n".join(
        f"- [{c.id}] {c.name} (0-{c.max_points:g} points): {c.description}" for c in spec.criteria
    )


def build_grading_prompt(
    spec: GradingSpec, files: list[SubmissionFile], boundary: str
) -> tuple[str, bool]:
    """Returns (prompt, truncated)."""
    submission_block, truncated = format_files(files, config.MAX_SUBMISSION_CHARS)
    solution_block = format_files(spec.reference_solution)[0] if spec.reference_solution else "None provided."
    prompt = load_prompt(
        "grading",
        assignment_id=spec.assignment_id,
        course_id=config.COURSE_ID,
        title=spec.title or spec.assignment_id,
        description=spec.description or "Not provided.",
        guidance=spec.guidance or "None.",
        criteria_block=_criteria_block(spec),
        solution_block=solution_block,
        boundary=boundary,
        submission_block=submission_block,
    )
    return prompt, truncated


def _str_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v) for v in value if str(v).strip()]


def parse_grading(data: dict, spec: GradingSpec) -> tuple[list[CriterionScore], FeedbackReport, list[str]]:
    """Validate the model's response against the spec. Raises GradingOutputError if unusable."""
    if not isinstance(data, dict) or not isinstance(data.get("criteria"), list):
        raise GradingOutputError("response has no criteria list")

    by_id = {str(c.get("id")): c for c in data["criteria"] if isinstance(c, dict)}
    scores = []
    for criterion in spec.criteria:
        entry = by_id.get(criterion.id)
        if entry is None:
            raise GradingOutputError(f"missing criterion {criterion.id!r}")
        score = entry.get("score")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise GradingOutputError(f"criterion {criterion.id!r} has a non-numeric score")
        if not 0 <= score <= criterion.max_points:
            raise GradingOutputError(f"criterion {criterion.id!r} score {score} is out of range")
        scores.append(CriterionScore(
            id=criterion.id,
            name=criterion.name,
            score=float(score),
            max_points=criterion.max_points,
            justification=str(entry.get("justification", "")),
            evidence=str(entry.get("evidence", "")),
        ))

    fb = data.get("feedback") if isinstance(data.get("feedback"), dict) else {}
    feedback = FeedbackReport(
        summary=str(fb.get("summary", "")),
        strengths=_str_list(fb.get("strengths")),
        improvements=_str_list(fb.get("improvements")),
        next_steps=_str_list(fb.get("next_steps")),
    )
    return scores, feedback, _str_list(data.get("review_flags"))


async def grade_submission(
    spec: GradingSpec,
    files: list[SubmissionFile],
    provider: LLMProvider,
    collector: ProvenanceCollector | None = None,
) -> GradingOutcome:
    """Grade a submission against the spec's rubric with a single LLM call (retried once if unusable)."""
    prompt, truncated = build_grading_prompt(spec, files, new_boundary())
    reasons = [TRUNCATED] if truncated else []

    for _ in range(ATTEMPTS):
        latency_ms, error = 0, ""
        try:
            data, _raw, latency_ms = await provider.complete_with_raw(prompt)
            criteria, feedback, flags = parse_grading(data, spec)
        except LLMAuthError:
            raise
        except (GradingOutputError, json.JSONDecodeError) as exc:
            error = f"Unusable grading response: {exc}"
        except Exception:
            logger.warning("Grading call failed", exc_info=True)
            error = "Grading call failed"

        if collector is not None:
            collector.add_call(LLMCallRecord(
                stage="grading", latency_ms=latency_ms, success=not error, error=error,
            ))
        if not error:
            return GradingOutcome(criteria=criteria, feedback=feedback, review_reasons=reasons + flags)
        logger.warning("%s (assignment %s)", error, spec.assignment_id)

    return GradingOutcome(review_reasons=reasons + [GRADING_FAILED])
