import ast
import json
import logging

from assessment_agent.models import AnomalyReport, AnomalyFlag, LLMCallRecord, ProvenanceCollector, SubmissionFile
from assessment_agent.llm import LLMProvider
from assessment_agent.spec import GradingSpec
from assessment_agent.prompt_loader import load_prompt
from assessment_agent.agents.grader import format_files, new_boundary
from assessment_agent import config

logger = logging.getLogger(__name__)


def extract_style_metrics(code: str) -> dict:
    """Extract code style fingerprint using AST analysis."""
    metrics = {
        "num_functions": 0,
        "num_classes": 0,
        "num_imports": 0,
        "avg_line_length": 0,
        "max_line_length": 0,
        "num_comments": 0,
        "naming_conventions": [],
        "complexity_indicators": 0,
        "total_lines": 0,
        "blank_lines": 0,
    }

    lines = code.split("\n")
    metrics["total_lines"] = len(lines)
    metrics["blank_lines"] = sum(1 for l in lines if not l.strip())
    line_lengths = [len(l) for l in lines if l.strip()]
    metrics["avg_line_length"] = round(sum(line_lengths) / max(len(line_lengths), 1), 1)
    metrics["max_line_length"] = max(line_lengths) if line_lengths else 0
    metrics["num_comments"] = sum(1 for l in lines if l.strip().startswith("#"))

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return metrics

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            metrics["num_functions"] += 1
            metrics["naming_conventions"].append(
                "snake_case" if "_" in node.name else "camelCase" if node.name[0].islower() else "PascalCase"
            )
        elif isinstance(node, ast.ClassDef):
            metrics["num_classes"] += 1
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            metrics["num_imports"] += 1
        elif isinstance(node, ast.For):
            for child in ast.walk(node):
                if isinstance(child, ast.For) and child is not node:
                    metrics["complexity_indicators"] += 1
        elif isinstance(node, ast.ListComp):
            metrics["complexity_indicators"] += 1

    return metrics


async def detect_anomalies(
    files: list[SubmissionFile],
    spec: GradingSpec,
    provider: LLMProvider,
    collector: ProvenanceCollector | None = None,
) -> AnomalyReport:
    """Analyze a submission for style anomalies and potential academic integrity issues."""
    python_code = "\n".join(f.content for f in files if f.filename.endswith(".py"))
    metrics = json.dumps(extract_style_metrics(python_code), indent=2) if python_code else "None (no Python files)."
    submission_block, _ = format_files(files, config.MAX_SUBMISSION_CHARS)
    boundary = new_boundary()

    prompt = load_prompt(
        "anomaly_detection",
        assignment_id=spec.assignment_id,
        course_id=config.COURSE_ID,
        title=spec.title or spec.assignment_id,
        description=spec.description or "Not provided.",
        skill_level=spec.skill_level or "Not specified; judge from the task and guidance.",
        grading_guidance=spec.guidance or "None.",
        metrics=metrics,
        boundary=boundary,
        submission_block=submission_block,
    )

    latency_ms, error = 0, ""
    try:
        result, _raw, latency_ms = await provider.complete_with_raw(prompt)
        report = AnomalyReport(
            flags=[
                AnomalyFlag(
                    flag_type=str(f.get("flag_type", "unknown")).lower(),
                    confidence=min(max(float(f.get("confidence", 0)), 0), 1),
                    evidence=f.get("evidence", ""),
                    severity=f.get("severity", "low"),
                )
                for f in result.get("flags", [])
            ],
            overall_risk=str(result.get("overall_risk", "low")).lower(),
            recommendation=result.get("recommendation", ""),
        )
    except Exception:
        logger.warning("Anomaly detection failed", exc_info=True)
        error = "Anomaly detection failed"
        report = AnomalyReport(recommendation="Failed to analyze submission.")

    if collector is not None:
        collector.add_call(LLMCallRecord(
            stage="anomaly_detection", latency_ms=latency_ms, success=not error, error=error,
        ))
    return report
