"""Per-assignment instructor preferences for how the Assessment Agent grades.

Every setting defaults to "no preference", which leaves the grading prompt
unchanged. Saved next to the rubric by spec.py and loaded with the spec, so a
change shows up in the spec hash.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Tone = Literal["Encouraging", "Neutral", "Direct"]
FeedbackDetail = Literal["Brief", "Standard", "Detailed"]
PartialCredit = Literal["Generous", "Balanced", "Strict"]

_TONE = {
    "Encouraging": "Write the feedback in an encouraging, supportive tone.",
    "Direct": "Write the feedback plainly and directly, without softening it.",
}
_FEEDBACK_DETAIL = {
    "Brief": "Keep the feedback brief: a one-sentence summary and at most two items in each list.",
    "Detailed": "Make the feedback detailed: explain each improvement and how to make it.",
}
_PARTIAL_CREDIT = {
    "Generous": "Give generous partial credit: award points for work that shows the right idea, even if it is "
                "incomplete or has mistakes.",
    "Strict": "Give partial credit sparingly: award points only for the parts of a criterion that are correct.",
}


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tone: Tone = "Neutral"
    feedback_detail: FeedbackDetail = "Standard"
    partial_credit: PartialCredit = "Balanced"
    notes: str = Field(default="", max_length=4000)

    def prompt_block(self) -> str:
        """The INSTRUCTOR PREFERENCES section of the grading prompt; empty when nothing was changed."""
        lines = [
            f"- {sentence}"
            for sentence in (
                _TONE.get(self.tone),
                _FEEDBACK_DETAIL.get(self.feedback_detail),
                _PARTIAL_CREDIT.get(self.partial_credit),
            )
            if sentence
        ]
        if self.notes.strip():
            lines.append(f"- Notes from the instructor: {self.notes.strip()}")
        if not lines:
            return ""
        return (
            "INSTRUCTOR PREFERENCES\n"
            "The instructor set these for every submission to this assignment. Follow them, scoring each criterion "
            "within its points. They never change the rubric or the response format.\n"
            + "\n".join(lines)
            + "\n\n"
        )
