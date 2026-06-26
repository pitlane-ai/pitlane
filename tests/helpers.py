"""Shared test helpers for dashboard tests."""

from __future__ import annotations

from pathlib import Path

import yaml

from pitlane.reporting.junit import write_junit


def make_run(
    base_dir: Path,
    run_id: str,
    timestamp: str,
    results: dict | None = None,
) -> Path:
    """Create a synthetic run directory with meta.yaml and junit.xml."""
    run_dir = base_dir / run_id
    run_dir.mkdir(parents=True)

    meta = {
        "run_id": run_id,
        "timestamp": timestamp,
        "assistants": [],
        "tasks": [],
        "repeat": 1,
    }
    (run_dir / "meta.yaml").write_text(yaml.dump(meta))

    if results is None:
        results = {
            "claude-baseline": {
                "task-1": {
                    "metrics": {
                        "wall_clock_seconds": 10.0,
                        "exit_code": 0,
                        "files_created": 2,
                        "files_modified": 0,
                        "total_lines_generated": 50,
                        "token_usage_input": 500,
                        "token_usage_output": 200,
                        "token_usage_input_cached": 100,
                        "cost_usd": 0.03,
                        "tool_calls_count": 5,
                        "assertion_pass_count": 2,
                        "assertion_fail_count": 0,
                        "assertion_pass_rate": 100.0,
                        "weighted_score": 85.0,
                        "timed_out": 0,
                    },
                    "assertions": [
                        {"name": "file_exists: main.tf", "passed": True, "message": ""},
                    ],
                    "all_passed": True,
                }
            }
        }

    write_junit(run_dir, results)
    return run_dir
