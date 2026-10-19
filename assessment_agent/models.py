from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime
import uuid


ResultStatus = Literal["ai_graded", "needs_review", "instructor_graded"]


class SubmissionFile(BaseModel):
    filename: str
    content: str


class CriterionScore(BaseModel):
    id: str
    name: str
    score: float
    max_points: float
    justification: str = ""
    evidence: str = ""


class AnomalyFlag(BaseModel):
    flag_type: str  # "style_change", "plagiarism", "ai_generated", "complexity_mismatch", "prompt_injection"
    confidence: float = 0.0  # 0.0 - 1.0
    evidence: str = ""
    severity: str = "low"  # low, medium, high


class AnomalyReport(BaseModel):
    flags: list[AnomalyFlag] = []
    overall_risk: str = "low"  # low, medium, high
    recommendation: str = ""


class FeedbackReport(BaseModel):
    summary: str = ""
    strengths: list[str] = []
    improvements: list[str] = []
    next_steps: list[str] = []


class LLMCallRecord(BaseModel):
    # Prompt text and raw responses are not kept: prompts contain the reference solution.
    stage: str
    latency_ms: int
    success: bool = True
    error: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class ProvenanceRecord(BaseModel):
    submission_hash: str
    spec_hash: str
    model_id: str
    llm_calls: list[LLMCallRecord] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class ProvenanceCollector:
    """Runtime accumulator passed through the pipeline to collect LLM call records."""

    def __init__(self, model_id: str, spec_hash: str, submission_hash: str) -> None:
        self.model_id = model_id
        self.spec_hash = spec_hash
        self.submission_hash = submission_hash
        self._calls: list[LLMCallRecord] = []

    def add_call(self, record: LLMCallRecord) -> None:
        self._calls.append(record)

    def build(self) -> ProvenanceRecord:
        return ProvenanceRecord(
            submission_hash=self.submission_hash,
            spec_hash=self.spec_hash,
            model_id=self.model_id,
            llm_calls=self._calls,
        )


class AssessmentResult(BaseModel):
    submission_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    student_id: str
    assignment_id: str
    files: list[str] = []  # filenames only; submitted text is not stored
    model: str = ""  # the model that graded it; "mock" when no API key was provided
    mock: bool = False  # True when graded by the offline mock model: not a real assessment
    criteria: list[CriterionScore] = []
    score: Optional[float] = None  # sum of criterion scores; None when grading failed
    max_score: float = 0.0
    feedback: Optional[FeedbackReport] = None
    anomaly_report: Optional[AnomalyReport] = None
    status: ResultStatus = "ai_graded"
    review_reasons: list[str] = []
    final_score: Optional[float] = None  # set by an instructor; replaces score
    instructor_notes: str = ""
    reviewed_at: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    provenance: Optional[ProvenanceRecord] = None


class AssessmentRequest(BaseModel):
    student_id: str
    assignment_id: str
    files: list[SubmissionFile]


class ReviewRequest(BaseModel):
    final_score: float
    notes: str = ""
