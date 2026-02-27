from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, TYPE_CHECKING

import numpy as np

from pitlane.assistants.base import AssistantResult
from pitlane.assertions.base import AssertionResult

if TYPE_CHECKING:
    from pitlane.runner import IterationResult


@dataclass
class MetricStatistics:
    """Statistics for a single metric across iterations."""

    avg: float | None
    min: float | None
    max: float | None
    stddev: float | None

    def to_dict(self) -> dict[str, float | None]:
        return asdict(self)


@dataclass
class AssertionSummary:
    """Summary of assertion results across iterations."""

    name: str
    passed: bool
    message: str
    pass_rate: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RepeatSummary:
    """Summary of repeated iterations."""

    count: int
    all_passed_count: int
    all_passed_rate: float
    iterations: list[IterationResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "all_passed_count": self.all_passed_count,
            "all_passed_rate": self.all_passed_rate,
            "iterations": [it.to_dict() for it in self.iterations],
        }


@dataclass
class AggregatedResult:
    """Aggregated results across multiple iterations."""

    metrics: dict[str, float | None]
    metrics_stats: dict[str, MetricStatistics]
    assertions: list[AssertionSummary]
    all_passed: bool
    repeat: RepeatSummary

    def to_dict(self) -> dict[str, Any]:
        return {
            "metrics": self.metrics,
            "metrics_stats": {k: v.to_dict() for k, v in self.metrics_stats.items()},
            "assertions": [a.to_dict() for a in self.assertions],
            "all_passed": self.all_passed,
            "repeat": self.repeat.to_dict(),
        }


def compute_stats(values: list[float | int | None]) -> MetricStatistics:
    """Compute avg, min, max, stddev for a list of numeric values."""
    nums = [v for v in values if v is not None]
    if not nums:
        return MetricStatistics(avg=None, min=None, max=None, stddev=None)

    arr = np.array(nums)
    return MetricStatistics(
        avg=round(float(np.mean(arr)), 4),
        min=round(float(np.min(arr)), 4),
        max=round(float(np.max(arr)), 4),
        stddev=round(float(np.std(arr)), 4),
    )


def aggregate_results(run_results: list[IterationResult]) -> AggregatedResult:  # type: ignore[name-defined]
    """Aggregate multiple iteration results into a single result with stats."""
    iteration_count = len(run_results)
    metric_names = list(run_results[0].metrics.keys())

    # Build per-metric stats (combine duplicate loops)
    averaged_metrics: dict[str, float | None] = {}
    metric_statistics: dict[str, MetricStatistics] = {}

    for metric_name in metric_names:
        metric_values = [run.metrics.get(metric_name) for run in run_results]
        statistics = compute_stats(metric_values)
        averaged_metrics[metric_name] = statistics.avg
        metric_statistics[metric_name] = statistics

    # Aggregate assertions: report per-assertion pass rate across iterations
    first_run_assertions = run_results[0].assertions
    assertion_summaries: list[AssertionSummary] = []

    for assertion_index, assertion in enumerate(first_run_assertions):
        pass_count = sum(
            1
            for run in run_results
            if assertion_index < len(run.assertions)
            and run.assertions[assertion_index]["passed"]
        )

        summary = AssertionSummary(
            name=assertion["name"],
            passed=pass_count == iteration_count,
            message=f"Passed {pass_count}/{iteration_count} iterations",
            pass_rate=round(pass_count / iteration_count * 100, 1),
        )
        assertion_summaries.append(summary)

    successful_iteration_count = sum(1 for run in run_results if run.all_passed)

    repeat_summary = RepeatSummary(
        count=iteration_count,
        all_passed_count=successful_iteration_count,
        all_passed_rate=round(successful_iteration_count / iteration_count * 100, 1),
        iterations=run_results,
    )

    return AggregatedResult(
        metrics=averaged_metrics,
        metrics_stats=metric_statistics,
        assertions=assertion_summaries,
        all_passed=all(run.all_passed for run in run_results),
        repeat=repeat_summary,
    )


def collect_metrics(
    assistant_result: AssistantResult,
    assertion_results: list[AssertionResult],
    workspace: Path,
    files_before: set[str],
) -> dict[str, Any]:
    """Collect all metrics for a single assistant run."""
    # File diff
    files_after = {
        str(f.relative_to(workspace)) for f in workspace.rglob("*") if f.is_file()
    }
    files_created = len(files_after - files_before)
    files_modified = len(
        files_before & files_after
    )  # simplified: assumes all pre-existing were touched

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
        weighted_score = (
            sum(r.weight * r.score for r in assertion_results) / total_weight * 100
        )
    else:
        weighted_score = 0.0

    # Token usage
    tu = assistant_result.token_usage or {}

    return {
        "wall_clock_seconds": assistant_result.duration_seconds,
        "exit_code": assistant_result.exit_code,
        "files_created": files_created,
        "files_modified": files_modified,
        "total_lines_generated": total_lines,
        "token_usage_input": tu.get("input"),
        "token_usage_output": tu.get("output"),
        "token_usage_input_cached": tu.get("input_cached"),
        "cost_usd": assistant_result.cost_usd,
        "tool_calls_count": assistant_result.tool_calls_count,
        "timed_out": assistant_result.timed_out,
        "assertion_pass_count": passed,
        "assertion_fail_count": failed,
        "assertion_pass_rate": round(pass_rate, 2),
        "weighted_score": round(weighted_score, 2),
    }
