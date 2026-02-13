import json
import pytest
from pathlib import Path
from agent_eval.reporting.html import generate_report


@pytest.fixture
def sample_run_dir(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    results = {
        "claude-baseline": {
            "task-1": {
                "metrics": {
                    "wall_clock_seconds": 10.5,
                    "exit_code": 0,
                    "files_created": 2,
                    "files_modified": 0,
                    "total_lines_generated": 50,
                    "token_usage_input": 500,
                    "token_usage_output": 200,
                    "cost_usd": 0.03,
                    "tool_calls_count": 5,
                    "assertion_pass_count": 3,
                    "assertion_fail_count": 0,
                    "assertion_pass_rate": 100.0,
                    "weighted_score": 100.0,
                },
                "assertions": [
                    {"name": "file_exists: main.tf", "passed": True, "message": "", "score": 1.0, "weight": 1.0},
                    {"name": "file_exists: variables.tf", "passed": True, "message": "", "score": 1.0, "weight": 1.0},
                    {"name": "command_succeeds: terraform validate", "passed": True, "message": "", "score": 1.0, "weight": 1.0},
                ],
                "all_passed": True,
            }
        },
        "codex-baseline": {
            "task-1": {
                "metrics": {
                    "wall_clock_seconds": 15.2,
                    "exit_code": 0,
                    "files_created": 1,
                    "files_modified": 0,
                    "total_lines_generated": 30,
                    "token_usage_input": 800,
                    "token_usage_output": 300,
                    "cost_usd": None,
                    "tool_calls_count": 8,
                    "assertion_pass_count": 2,
                    "assertion_fail_count": 1,
                    "assertion_pass_rate": 66.67,
                    "weighted_score": 66.67,
                },
                "assertions": [
                    {"name": "file_exists: main.tf", "passed": True, "message": "", "score": 1.0, "weight": 1.0},
                    {"name": "file_exists: variables.tf", "passed": False, "message": "File not found", "score": 0.0, "weight": 1.0},
                    {"name": "command_succeeds: terraform validate", "passed": True, "message": "", "score": 1.0, "weight": 1.0},
                ],
                "all_passed": False,
            }
        },
    }
    (run_dir / "results.json").write_text(json.dumps(results, indent=2))
    return run_dir


def test_generate_report_creates_html(sample_run_dir):
    report_path = generate_report(sample_run_dir)
    assert report_path.exists()
    assert report_path.suffix == ".html"


def test_report_contains_assistant_names(sample_run_dir):
    report_path = generate_report(sample_run_dir)
    html = report_path.read_text()
    assert "claude-baseline" in html
    assert "codex-baseline" in html


def test_report_contains_task_names(sample_run_dir):
    report_path = generate_report(sample_run_dir)
    html = report_path.read_text()
    assert "task-1" in html


def test_report_is_self_contained(sample_run_dir):
    report_path = generate_report(sample_run_dir)
    html = report_path.read_text()
    assert "<style>" in html


@pytest.fixture
def repeat_run_dir(tmp_path):
    """Run dir with repeat=3 aggregated results."""
    import yaml

    run_dir = tmp_path / "repeat_run"
    run_dir.mkdir()

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
                    "cost_usd": 0.03,
                    "tool_calls_count": 5,
                    "assertion_pass_count": 3,
                    "assertion_fail_count": 0,
                    "assertion_pass_rate": 100.0,
                    "weighted_score": 100.0,
                },
                "metrics_stats": {
                    "wall_clock_seconds": {"avg": 10.0, "min": 8.0, "max": 12.0, "stddev": 2.0},
                    "exit_code": {"avg": 0, "min": 0, "max": 0, "stddev": 0},
                    "files_created": {"avg": 2, "min": 2, "max": 2, "stddev": 0},
                    "files_modified": {"avg": 0, "min": 0, "max": 0, "stddev": 0},
                    "total_lines_generated": {"avg": 50, "min": 45, "max": 55, "stddev": 5},
                    "token_usage_input": {"avg": 500, "min": 400, "max": 600, "stddev": 100},
                    "token_usage_output": {"avg": 200, "min": 150, "max": 250, "stddev": 50},
                    "cost_usd": {"avg": 0.03, "min": 0.02, "max": 0.04, "stddev": 0.01},
                    "tool_calls_count": {"avg": 5, "min": 4, "max": 6, "stddev": 1},
                    "assertion_pass_count": {"avg": 3, "min": 3, "max": 3, "stddev": 0},
                    "assertion_fail_count": {"avg": 0, "min": 0, "max": 0, "stddev": 0},
                    "assertion_pass_rate": {"avg": 100.0, "min": 100.0, "max": 100.0, "stddev": 0},
                    "weighted_score": {"avg": 100.0, "min": 100.0, "max": 100.0, "stddev": 0},
                },
                "assertions": [
                    {"name": "file_exists: main.tf", "passed": True, "message": "Passed 3/3 iterations", "pass_rate": 100.0},
                ],
                "all_passed": True,
                "repeat": {
                    "count": 3,
                    "all_passed_count": 3,
                    "all_passed_rate": 100.0,
                    "iterations": [
                        {"metrics": {"wall_clock_seconds": 8.0}, "assertions": [{"name": "file_exists: main.tf", "passed": True, "message": ""}], "all_passed": True},
                        {"metrics": {"wall_clock_seconds": 10.0}, "assertions": [{"name": "file_exists: main.tf", "passed": True, "message": ""}], "all_passed": True},
                        {"metrics": {"wall_clock_seconds": 12.0}, "assertions": [{"name": "file_exists: main.tf", "passed": True, "message": ""}], "all_passed": True},
                    ],
                },
            }
        },
    }
    (run_dir / "results.json").write_text(json.dumps(results, indent=2))
    (run_dir / "meta.yaml").write_text(yaml.dump({"repeat": 3}))
    return run_dir


def test_report_repeat_mode_shows_badge(repeat_run_dir):
    """Test that repeat report shows the repeat badge."""
    report_path = generate_report(repeat_run_dir)
    html = report_path.read_text()
    assert "3x repeat" in html
    assert "repeat-badge" in html


def test_report_repeat_mode_shows_stats(repeat_run_dir):
    """Test that repeat report shows avg +/- stddev."""
    report_path = generate_report(repeat_run_dir)
    html = report_path.read_text()
    assert "avg" in html.lower()
    assert "stddev" in html.lower()


def test_report_repeat_mode_shows_iterations(repeat_run_dir):
    """Test that repeat report includes iteration details."""
    report_path = generate_report(repeat_run_dir)
    html = report_path.read_text()
    assert "Iteration 1" in html
    assert "Iteration 2" in html
    assert "Iteration 3" in html


def test_report_single_mode_no_repeat_badge(sample_run_dir):
    """Test that single-run report does not show repeat badge."""
    report_path = generate_report(sample_run_dir)
    html = report_path.read_text()
    assert "x repeat</span>" not in html
