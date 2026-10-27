from unittest.mock import patch

import pytest

from assessment_agent.agents.grader import GRADING_FAILED
from assessment_agent.agents.orchestrator import assess_submission
from assessment_agent.llm.fake import FakeLLMProvider
from assessment_agent.models import AssessmentRequest, SubmissionFile
from assessment_agent.spec import SpecNotFoundError


class RecordingProvider(FakeLLMProvider):
    def __init__(self):
        self.prompts: list[str] = []

    def _dispatch(self, prompt: str) -> dict:
        self.prompts.append(prompt)
        return super()._dispatch(prompt)


class BrokenGradingProvider(FakeLLMProvider):
    @staticmethod
    def _grading(prompt: str) -> dict:
        return {"criteria": "not a list"}


def make_request(*files, assignment_id="hw1_sorting") -> AssessmentRequest:
    return AssessmentRequest(student_id="test_student", assignment_id=assignment_id, files=list(files))


async def run(request, provider):
    with patch("assessment_agent.agents.orchestrator.get_llm_provider", return_value=provider):
        return await assess_submission(request, api_key="sk-test")


async def test_code_submission_is_graded(fake_provider, submissions):
    result = await run(make_request(submissions["perfect_code"]), fake_provider)
    assert result.status == "ai_graded"
    assert result.review_reasons == []
    assert result.max_score == 100
    assert result.score == 80
    assert len(result.criteria) == 5
    assert result.files == ["student_a_perfect.py"]
    assert result.feedback.summary
    assert result.final_score is None


async def test_code_and_report_in_one_submission(fake_provider, submissions):
    result = await run(make_request(submissions["perfect_code"], submissions["report"]), fake_provider)
    assert result.files == ["student_a_perfect.py", "student_a_report.md"]
    assert result.status == "ai_graded"


async def test_other_languages_are_accepted(fake_provider):
    java = SubmissionFile(
        filename="Sort.java",
        content="import java.util.*;\nclass Sort { public static void main(String[] a) { } }\n",
    )
    result = await run(make_request(java), fake_provider)
    assert result.status == "ai_graded"
    assert result.score == 80


async def test_grading_is_the_only_model_call(submissions):
    provider = RecordingProvider()
    result = await run(make_request(submissions["perfect_code"]), provider)
    assert len(provider.prompts) == 1
    assert provider.prompts[0].startswith("You are grading a student submission")
    assert [c.stage for c in result.provenance.llm_calls] == ["grading"]


async def test_failed_grading_needs_review_without_a_score(submissions):
    result = await run(make_request(submissions["buggy_code"]), BrokenGradingProvider())
    assert result.status == "needs_review"
    assert result.score is None
    assert result.criteria == []
    assert GRADING_FAILED in result.review_reasons


async def test_unknown_assignment_raises(fake_provider, submissions):
    with pytest.raises(SpecNotFoundError):
        await run(make_request(submissions["perfect_code"], assignment_id="nope"), fake_provider)
