from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from junitparser import JUnitXml


@dataclass
class SuiteSummary:
    """Metrics for a single assistant/task pair within a run."""

    assistant: str
    task: str
    weighted_score: float | None
    assertion_pass_rate: float | None
    cost_usd: float | None
    wall_clock_seconds: float | None
    token_usage_input: float | None
    token_usage_output: float | None
    token_usage_input_cached: float | None
    tool_calls_count: float | None
    files_created: float | None
    files_modified: float | None
    timed_out: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RunSummary:
    """Summary of a single evaluation run."""

    run_id: str
    timestamp: str
    assistants: list[str]
    tasks: list[str]
    repeat: int
    suites: list[SuiteSummary]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "assistants": self.assistants,
            "tasks": self.tasks,
            "repeat": self.repeat,
            "suites": [s.to_dict() for s in self.suites],
        }


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _parse_timestamp(meta: dict) -> datetime | None:
    """Extract a timezone-aware datetime from meta.yaml data."""
    ts = meta.get("timestamp")
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts))
    except (ValueError, TypeError):
        return None


def _parse_date_bound(date_str: str) -> datetime:
    """Parse a YYYY-MM-DD string into a timezone-aware datetime."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.replace(tzinfo=timezone.utc)


def _extract_suites(junit_path: Path) -> list[SuiteSummary]:
    """Parse junit.xml and extract suite-level metrics."""
    xml = JUnitXml.fromfile(str(junit_path))
    suites: list[SuiteSummary] = []

    for suite in xml:
        parts = suite.name.split(" / ", 1)
        if len(parts) != 2:
            continue
        assistant, task = parts

        props = {p.name: p.value for p in suite.properties()}

        suites.append(
            SuiteSummary(
                assistant=assistant,
                task=task,
                weighted_score=_parse_float(props.get("weighted_score")),
                assertion_pass_rate=_parse_float(props.get("assertion_pass_rate")),
                cost_usd=_parse_float(props.get("cost_usd")),
                wall_clock_seconds=suite.time if suite.time else None,
                token_usage_input=_parse_float(props.get("token_usage_input")),
                token_usage_output=_parse_float(props.get("token_usage_output")),
                token_usage_input_cached=_parse_float(
                    props.get("token_usage_input_cached")
                ),
                tool_calls_count=_parse_float(props.get("tool_calls_count")),
                files_created=_parse_float(props.get("files_created")),
                files_modified=_parse_float(props.get("files_modified")),
                timed_out=_parse_float(props.get("timed_out")),
            )
        )

    return suites


def scan_runs(
    runs_dir: Path,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[RunSummary]:
    """Scan runs directory and return summaries filtered by optional date range.

    Args:
        runs_dir: Directory containing timestamped run subdirectories.
        date_from: Optional inclusive start date (YYYY-MM-DD).
        date_to: Optional inclusive end date (YYYY-MM-DD).

    Returns:
        List of RunSummary sorted by timestamp ascending.
    """
    from_dt = _parse_date_bound(date_from) if date_from else None
    # Make to_dt inclusive of the full day
    to_dt = None
    if date_to:
        to_dt = _parse_date_bound(date_to).replace(
            hour=23, minute=59, second=59, microsecond=999999
        )

    results: list[RunSummary] = []

    if not runs_dir.is_dir():
        return results

    for entry in sorted(runs_dir.iterdir()):
        if not entry.is_dir():
            continue

        meta_path = entry / "meta.yaml"
        junit_path = entry / "junit.xml"
        if not meta_path.exists() or not junit_path.exists():
            continue

        try:
            meta = yaml.safe_load(meta_path.read_text()) or {}
        except Exception:
            continue

        run_ts = _parse_timestamp(meta)
        if run_ts is None:
            continue

        # Ensure timezone-aware for comparison
        if run_ts.tzinfo is None:
            run_ts = run_ts.replace(tzinfo=timezone.utc)

        if from_dt and run_ts < from_dt:
            continue
        if to_dt and run_ts > to_dt:
            continue

        try:
            suites = _extract_suites(junit_path)
        except Exception:
            continue

        repeat_count = meta.get("repeat", 1)
        if not isinstance(repeat_count, int):
            repeat_count = 1

        results.append(
            RunSummary(
                run_id=meta.get("run_id", entry.name),
                timestamp=run_ts.isoformat(),
                assistants=sorted(set(s.assistant for s in suites)),
                tasks=sorted(set(s.task for s in suites)),
                repeat=repeat_count,
                suites=suites,
            )
        )

    results.sort(key=lambda r: r.timestamp)
    return results
