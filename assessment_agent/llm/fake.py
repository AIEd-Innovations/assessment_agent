"""
Offline mock model with canned responses, used when a grading request carries
no API key (demos, UI development, tests). Every criterion gets 80% of its
points; results graded with it are marked as mock grades.
"""
from __future__ import annotations

import json
import re

# Matches the criterion lines the grading prompt renders, e.g. "- [correctness] Correctness (0-40 points): ..."
_CRITERION_LINE = re.compile(r"^- \[([^\]]+)\] .*?\(0-([\d.]+) points\)", re.MULTILINE)


class FakeLLMProvider:
    model_id: str = "mock"

    _ANOMALY = {
        "flags": [],
        "overall_risk": "low",
        "recommendation": "[mock] No concerns detected.",
    }

    async def complete_with_raw(self, prompt: str) -> tuple[dict, str, int]:
        result = self._dispatch(prompt)
        return result, json.dumps(result), 1

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
                "evidence": "[mock] submission",
                "justification": "[mock] Mostly meets the criterion.",
                "score": round(float(max_points) * 0.8, 2),
            }
            for criterion_id, max_points in _CRITERION_LINE.findall(prompt)
        ]
        return {
            "criteria": criteria,
            "feedback": {
                "summary": "[mock] Good work overall.",
                "strengths": ["Correct output", "Clean code"],
                "improvements": ["Add comments"],
                "next_steps": ["Try edge cases"],
            },
            "review_flags": [],
        }
