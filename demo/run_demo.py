"""
AIEIC Assessment Agent — Demo Script

Grades the four demo submissions for hw1_sorting and prints the results:
  1. Alice  — correct code + report
  2. Bob    — buggy code (lexicographic sort)
  3. Carol  — suspiciously advanced code (integrity check)
  4. Diana  — partial solution (bubble sort with a bare except)

Run (with the claude CLI logged in, or DEFAULT_LLM_PROVIDER=anthropic / fake):
    python demo/run_demo.py
"""
import asyncio
import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assessment_agent.agents.orchestrator import assess_submission
from assessment_agent.models import AssessmentRequest, SubmissionFile

DEMO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "submissions")

SUBMISSIONS = [
    ("alice", ["student_a_perfect.py", "student_a_report.md"]),
    ("bob", ["student_b_buggy.py"]),
    ("carol", ["student_c_suspicious.py"]),
    ("diana", ["student_d_partial.py"]),
]

BOLD = "\033[1m"
DIM = "\033[2m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def read_file(name: str) -> SubmissionFile:
    with open(os.path.join(DEMO_DIR, name), encoding="utf-8") as f:
        return SubmissionFile(filename=name, content=f.read())


async def grade(student_id: str, filenames: list[str]) -> None:
    request = AssessmentRequest(
        student_id=student_id,
        assignment_id="hw1_sorting",
        files=[read_file(name) for name in filenames],
    )
    start = time.time()
    result = await assess_submission(request)
    elapsed = time.time() - start

    score = "—" if result.score is None else f"{result.score:g}"
    print(f"\n{BOLD}{student_id}{RESET}  {', '.join(result.files)}  ({elapsed:.1f}s)")
    print(f"  Score: {BOLD}{score}/{result.max_score:g}{RESET}  status: {result.status}")
    for c in result.criteria:
        print(f"    {c.name}: {c.score:g}/{c.max_points:g}  {DIM}{c.justification}{RESET}")
    for reason in result.review_reasons:
        print(f"  {YELLOW}Review: {reason}{RESET}")
    if result.feedback and result.feedback.summary:
        print(f"  Feedback: {result.feedback.summary}")


async def main() -> None:
    for student_id, filenames in SUBMISSIONS:
        await grade(student_id, filenames)


if __name__ == "__main__":
    asyncio.run(main())
