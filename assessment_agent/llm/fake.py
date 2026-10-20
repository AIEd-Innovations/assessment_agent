"""
Offline LLM provider with canned responses, for running the agent without the
`claude` CLI or an API key (demos, UI development). Select it with
DEFAULT_LLM_PROVIDER=fake. Scores come from exact-match test execution only.
"""
from __future__ import annotations

import json


class FakeLLMProvider:
    model_id: str = "fake-model-v1"

    _CANNED: list[tuple[str, dict]] = [
        ("expert CS grader", {"test_evaluations": [], "reasoning": "[fake provider] exact-match scoring only."}),
        ("BEGIN STUDENT REPORT", {
            "criteria": [
                {"name": "Logical Clarity", "score": 8, "justification": "[fake] Well structured argument."},
                {"name": "Completeness", "score": 9, "justification": "[fake] All aspects addressed."},
                {"name": "Technical Accuracy", "score": 7, "justification": "[fake] Minor inaccuracies."},
                {"name": "Writing Quality", "score": 9, "justification": "[fake] Clear prose."},
            ],
            "reasoning": "[fake] Solid report with minor technical gaps.",
        }),
        ("academic integrity analyst", {
            "flags": [],
            "overall_risk": "low",
            "recommendation": "[fake] No concerns detected.",
        }),
        ("supportive but rigorous", {
            "summary": "[fake] Good work overall.",
            "strengths": ["Correct output", "Clean code"],
            "improvements": ["Add comments"],
            "next_steps": ["Try edge cases"],
        }),
        ("Assessment Orchestrator", {
            "reasoning": "[fake] Score looks appropriate.",
            "score_adjustment": 0,
            "review_priority": "normal",
            "instructor_notes": "[fake] No issues.",
        }),
    ]

    async def complete(self, prompt: str, system: str = "") -> str:
        return json.dumps(self._dispatch(prompt))

    async def complete_with_raw(self, prompt: str, system: str = "") -> tuple[dict, str, int]:
        result = self._dispatch(prompt)
        return result, json.dumps(result), 1

    async def complete_json(self, prompt: str, system: str = "") -> dict:
        return self._dispatch(prompt)

    def _dispatch(self, prompt: str) -> dict:
        for keyword, response in self._CANNED:
            if keyword in prompt:
                return response
        return {
            "reasoning": "[fake] fallback",
            "score_adjustment": 0,
            "review_priority": "normal",
            "instructor_notes": "",
        }
