"""
Provenance records.

  - Re-running a submission against the same files, spec, prompts and model
    produces an identical provenance record (modulo latency and timestamps).
  - Provenance never stores prompt text or raw responses, since prompts carry
    the reference solution.
"""
import json
from unittest.mock import patch

from assessment_agent.agents.orchestrator import assess_submission, hash_files
from assessment_agent.models import (
    AssessmentRequest,
    LLMCallRecord,
    ProvenanceCollector,
    ProvenanceRecord,
    SubmissionFile,
)
from assessment_agent.spec import load_spec, load_spec_with_hash


def _record(stage="grading", success=True) -> LLMCallRecord:
    return LLMCallRecord(stage=stage, latency_ms=100, success=success, error="" if success else "boom")


async def _run(provider, *files, assignment_id="hw1_sorting"):
    request = AssessmentRequest(student_id="s1", assignment_id=assignment_id, files=list(files))
    with patch("assessment_agent.agents.orchestrator.get_llm_provider", return_value=provider):
        return await assess_submission(request, api_key="sk-test")


# ---------------------------------------------------------------------------
# ProvenanceCollector
# ---------------------------------------------------------------------------

class TestProvenanceCollector:
    def test_build_keeps_inputs_and_every_call(self):
        collector = ProvenanceCollector(model_id="m", spec_hash="spec", submission_hash="sub")
        collector.add_call(_record("grading", success=False))
        collector.add_call(_record("grading"))
        record = collector.build()
        assert isinstance(record, ProvenanceRecord)
        assert (record.model_id, record.spec_hash, record.submission_hash) == ("m", "spec", "sub")
        assert [c.success for c in record.llm_calls] == [False, True]


# ---------------------------------------------------------------------------
# Provenance from a full assessment
# ---------------------------------------------------------------------------

class TestAssessmentProvenance:
    async def test_provenance_is_attached(self, fake_provider, submissions):
        result = await _run(fake_provider, submissions["perfect_code"])
        prov = result.provenance
        assert prov.model_id == fake_provider.model_id
        assert prov.submission_hash == hash_files([submissions["perfect_code"]])
        assert prov.spec_hash == load_spec_with_hash("hw1_sorting")[1]

    async def test_same_inputs_produce_same_hashes(self, fake_provider, submissions):
        first = (await _run(fake_provider, submissions["perfect_code"])).provenance
        second = (await _run(fake_provider, submissions["perfect_code"])).provenance
        assert first.submission_hash == second.submission_hash
        assert first.spec_hash == second.spec_hash

    async def test_different_files_produce_different_hash(self, fake_provider, submissions):
        first = (await _run(fake_provider, submissions["perfect_code"])).provenance
        second = (await _run(fake_provider, submissions["buggy_code"])).provenance
        assert first.submission_hash != second.submission_hash

    async def test_result_never_contains_the_reference_solution(self, fake_provider):
        solution = load_spec("hw2_linked_list").reference_solution[0].content
        files = [SubmissionFile(filename="ll.py", content="class Node:\n    pass\n")]
        result = await _run(fake_provider, *files, assignment_id="hw2_linked_list")
        serialized = json.dumps(result.model_dump())
        assert "prompt_text" not in serialized
        assert "raw_response" not in serialized
        assert "self.tail = prev" in solution
        assert "self.tail = prev" not in serialized
