"""
Offline LLM provider with canned responses, for running the agent without the
`claude` CLI or an API key (demos, UI development). Select it with
DEFAULT_LLM_PROVIDER=fake. Every criterion gets 80% of its points.
"""
from __future__ import annotations

import json
import re

# Matches the criterion lines the grading prompt renders, e.g. "- [correctness] Correctness (0-40 points): ..."
_CRITERION_LINE = re.compile(r"^- \[([^\]]+)\] .*?\(0-([\d.]+) points\)", re.MULTILINE)


class FakeLLMProvider:
    model_id: str = "fake-model-v1"

    _ANOMALY = {
        "flags": [],
        "overall_risk": "low",
        "recommendation": "[fake] No concerns detected.",
    }

    async def complete(self, prompt: str, system: str = "") -> str:
        return json.dumps(self._dispatch(prompt))

    async def complete_with_raw(self, prompt: str, system: str = "") -> tuple[dict, str, int]:
        result = self._dispatch(prompt)
        return result, json.dumps(result), 1

    async def complete_json(self, prompt: str, system: str = "") -> dict:
        return self._dispatch(prompt)

    def _dispatch(self, prompt: str) -> dict:
        if prompt.startswith("You are grading a student submission"):
            return self._grading(prompt)
        if "academic integrity analyst" in prompt:
            return self._ANOMALY
        return {}

    @staticmethod
    def _grading(prompt: str) -> dict:
        criteria = [
            {
                "id": criterion_id,
                "evidence": "[fake] submission",
                "justification": "[fake] Mostly meets the criterion.",
                "score": round(float(max_points) * 0.8, 2),
            }
            for criterion_id, max_points in _CRITERION_LINE.findall(prompt)
        ]
        return {
            "criteria": criteria,
            "feedback": {
                "summary": "[fake] Good work overall.",
                "strengths": ["Correct output", "Clean code"],
                "improvements": ["Add comments"],
                "next_steps": ["Try edge cases"],
            },
            "review_flags": [],
        }
