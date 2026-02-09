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
                },
                "assertions": [
                    {"name": "file_exists: main.tf", "passed": True, "message": ""},
                    {"name": "file_exists: variables.tf", "passed": True, "message": ""},
                    {"name": "command_succeeds: terraform validate", "passed": True, "message": ""},
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
                },
                "assertions": [
                    {"name": "file_exists: main.tf", "passed": True, "message": ""},
                    {"name": "file_exists: variables.tf", "passed": False, "message": "File not found"},
                    {"name": "command_succeeds: terraform validate", "passed": True, "message": ""},
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
