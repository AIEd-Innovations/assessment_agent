"""Per-assignment instructor controls for the Assessment Agent.

These values influence the grader's communication and review preferences. The
rubric and the non-negotiable grading safeguards remain part of the base prompt.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from assessment_agent import config
from assessment_agent.spec import check_id


Tone = Literal["Encouraging", "Neutral", "Direct", "Analytical"]
Strictness = Literal["Flexible", "Balanced", "High"]
SupportStyle = Literal["Socratic questions", "Progressive hints", "Concise feedback", "Detailed explanations"]
FeedbackFocus = Literal["Build understanding", "Build confidence", "Improve accuracy", "Encourage reflection"]
Guardrail = Literal[
    "Never give a full answer",
    "Ask for an attempt first",
    "Escalate uncertainty to the instructor",
    "Only use approved course materials",
]


class AgentConfig(BaseModel):
    tone: Tone = "Analytical"
    strictness: Strictness = "High"
    support_style: SupportStyle = "Concise feedback"
    feedback_focus: FeedbackFocus = "Improve accuracy"
    guardrail: Guardrail = "Escalate uncertainty to the instructor"
    instructions: str = Field(default="", max_length=12_000)

    def prompt_instructions(self) -> str:
        """Create the bounded behavior block included in the grading prompt."""
        if self.instructions.strip():
            return f"Instructor-provided assessment guidance:\n{self.instructions.strip()}"
        return (
            f"Use a {self.tone.lower()} tone in feedback. Use {self.support_style.lower()} "
            f"to {self.feedback_focus.lower()}. Apply this preference with "
            f"{self.strictness.lower()} consistency. {self.guardrail}."
        )


def _config_path(assignment_id: str) -> Path:
    check_id(assignment_id)
    return Path(config.DATA_DIR) / "agent_configs" / f"{assignment_id}.json"


def load_agent_config(assignment_id: str) -> AgentConfig:
    path = _config_path(assignment_id)
    if not path.is_file():
        return AgentConfig()
    return AgentConfig.model_validate_json(path.read_text(encoding="utf-8"))


def save_agent_config(assignment_id: str, agent_config: AgentConfig) -> AgentConfig:
    path = _config_path(assignment_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(agent_config.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return agent_config
