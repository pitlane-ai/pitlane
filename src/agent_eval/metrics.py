from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_eval.adapters.base import AdapterResult
from agent_eval.assertions.base import AssertionResult


def collect_metrics(
    adapter_result: AdapterResult,
    assertion_results: list[AssertionResult],
    workspace: Path,
    files_before: set[str],
) -> dict[str, Any]:
    """Collect all metrics for a single adapter run."""
    # File diff
    files_after = {
        str(f.relative_to(workspace))
        for f in workspace.rglob("*")
        if f.is_file()
    }
    files_created = len(files_after - files_before)
    files_modified = len(files_before & files_after)  # simplified: assumes all pre-existing were touched

    # Count lines in new/modified files
    total_lines = 0
    for f in workspace.rglob("*"):
        if f.is_file():
            try:
                total_lines += len(f.read_text().splitlines())
            except (UnicodeDecodeError, PermissionError):
                pass

    # Assertions
    passed = sum(1 for r in assertion_results if r.passed)
    failed = sum(1 for r in assertion_results if not r.passed)
    total = passed + failed
    pass_rate = (passed / total * 100) if total > 0 else 0.0

    # Weighted score: sum(weight_i * score_i) / sum(weight_i) * 100
    # Uses continuous scores (0.0-1.0) rather than binary pass/fail,
    # so similarity metrics contribute proportionally to their score.
    total_weight = sum(r.weight for r in assertion_results)
    if total_weight > 0:
        weighted_score = sum(r.weight * r.score for r in assertion_results) / total_weight * 100
    else:
        weighted_score = 0.0

    # Token usage
    tu = adapter_result.token_usage or {}

    return {
        "wall_clock_seconds": adapter_result.duration_seconds,
        "exit_code": adapter_result.exit_code,
        "files_created": files_created,
        "files_modified": files_modified,
        "total_lines_generated": total_lines,
        "token_usage_input": tu.get("input"),
        "token_usage_output": tu.get("output"),
        "cost_usd": adapter_result.cost_usd,
        "tool_calls_count": adapter_result.tool_calls_count,
        "assertion_pass_count": passed,
        "assertion_fail_count": failed,
        "assertion_pass_rate": round(pass_rate, 2),
        "weighted_score": round(weighted_score, 2),
    }
