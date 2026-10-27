"""
Import an approved curriculum designer lab as assessment specs. The import is a
saved copy: grading never calls the curriculum designer, so it keeps working if
that service is down or the lab changes later.
"""
from __future__ import annotations

import re

import httpx

from assessment_agent import config
from assessment_agent.spec import Criterion, GradingSpec, check_id, save_material_text, save_spec

IMPORTED_MATERIAL = "curriculum-designer.txt"


class CurriculumError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


async def fetch_lab(lab_id: str) -> dict:
    if not config.CURRICULUM_URL:
        raise CurriculumError(503, "CURRICULUM_URL is not set, so labs cannot be imported")
    url = f"{config.CURRICULUM_URL.rstrip('/')}/curriculum/{lab_id}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        raise CurriculumError(502, f"Could not reach the curriculum designer: {exc}") from exc
    if response.status_code == 404:
        raise CurriculumError(404, f"The curriculum designer has no lab {lab_id!r}")
    if response.status_code != 200:
        raise CurriculumError(502, f"The curriculum designer returned HTTP {response.status_code}")
    return response.json()


def _slug(name: str, used: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "criterion"
    slug, n = base, 2
    while slug in used:
        slug, n = f"{base}_{n}", n + 1
    used.add(slug)
    return slug


def lab_to_specs(lab: dict, assignment_id: str) -> list[GradingSpec]:
    """The lab's rubric as one spec, plus its quiz as a separate {assignment_id}-quiz spec when it has one."""
    if lab.get("approval_status") != "approved":
        raise CurriculumError(409, f"Lab {lab.get('lab_id')!r} is not approved yet")

    title = lab.get("title", "")
    common = {
        "guidance": lab.get("agent_instructions") or "",
        "source": f"curriculum-designer {lab.get('lab_id')} v{lab.get('version', 1)}",
    }

    # Their criteria carry fractional weights and a separate code/report/manual split; the split is
    # ignored and the weights are scaled so the rubric totals 100 points.
    rubric = [c for c in (lab.get("rubric") or {}).get("criteria") or [] if float(c.get("weight", 0)) > 0]
    total_weight = sum(float(c["weight"]) for c in rubric)
    if not rubric:
        raise CurriculumError(422, f"Lab {lab.get('lab_id')!r} has no weighted rubric criteria")
    used: set[str] = set()
    specs = [GradingSpec(
        assignment_id=assignment_id,
        title=title,
        description=lab.get("spec_markdown", ""),
        criteria=[
            Criterion(
                id=_slug(c["name"], used),
                name=c["name"],
                description=c.get("description", ""),
                max_points=round(float(c["weight"]) / total_weight * 100, 1),
            )
            for c in rubric
        ],
        **common,
    )]

    questions = [q for q in lab.get("quiz") or [] if q.get("rubric_points", 0) > 0]
    if questions:
        specs.append(GradingSpec(
            assignment_id=f"{assignment_id}-quiz",
            title=f"{title} quiz",
            description="Answer each quiz question. The submission holds the student's answers.",
            criteria=[
                Criterion(
                    id=q["id"],
                    name=f"Question {q['id']}",
                    description=f"({q.get('type', 'question')}) {q['question']}",
                    max_points=q["rubric_points"],
                    expected_answer=q.get("expected_answer", ""),
                )
                for q in questions
            ],
            **common,
        ))
    return specs


async def import_lab(lab_id: str, assignment_id: str | None = None) -> dict:
    """Fetch an approved lab and save it as specs. Re-importing replaces the specs and keeps uploaded solutions."""
    assignment_id = assignment_id or lab_id
    check_id(lab_id)
    check_id(assignment_id)
    lab = await fetch_lab(lab_id)
    specs = lab_to_specs(lab, assignment_id)
    for spec in specs:
        save_spec(spec)
    material = lab.get("material_content")
    if material:
        for spec in specs:
            save_material_text(spec.assignment_id, IMPORTED_MATERIAL, material)
    return {"imported": [s.assignment_id for s in specs], "material": bool(material)}
