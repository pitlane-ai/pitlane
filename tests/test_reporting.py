from __future__ import annotations

import json

import pytest
import yaml
from junitparser import JUnitXml, Failure

from pitlane.reporting.junit import write_junit, generate_report


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_results() -> dict:
    return {
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
                    {"name": "file_exists: main.tf", "passed": True, "message": ""},
                    {
                        "name": "file_exists: variables.tf",
                        "passed": True,
                        "message": "",
                    },
                    {
                        "name": "command_succeeds: terraform validate",
                        "passed": True,
                        "message": "",
                    },
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
                    {"name": "file_exists: main.tf", "passed": True, "message": ""},
                    {
                        "name": "file_exists: variables.tf",
                        "passed": False,
                        "message": "File not found",
                    },
                    {
                        "name": "command_succeeds: terraform validate",
                        "passed": True,
                        "message": "",
                    },
                ],
                "all_passed": False,
            }
        },
    }


@pytest.fixture
def sample_run_dir(tmp_path, sample_results):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    write_junit(run_dir, sample_results)
    return run_dir


@pytest.fixture
def repeat_results() -> dict:
    return {
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
                    "wall_clock_seconds": {
                        "avg": 10.0,
                        "min": 8.0,
                        "max": 12.0,
                        "stddev": 2.0,
                    },
                    "cost_usd": {
                        "avg": 0.03,
                        "min": 0.02,
                        "max": 0.04,
                        "stddev": 0.01,
                    },
                },
                "assertions": [
                    {
                        "name": "file_exists: main.tf",
                        "passed": True,
                        "message": "Passed 3/3 iterations",
                        "pass_rate": 100.0,
                    },
                ],
                "all_passed": True,
            }
        }
    }


@pytest.fixture
def repeat_run_dir(tmp_path, repeat_results):
    run_dir = tmp_path / "repeat_run"
    run_dir.mkdir()
    (run_dir / "meta.yaml").write_text(yaml.dump({"repeat": 3}))
    write_junit(run_dir, repeat_results)
    return run_dir


# ---------------------------------------------------------------------------
# write_junit tests
# ---------------------------------------------------------------------------


def test_write_junit_creates_file(sample_run_dir):
    assert (sample_run_dir / "junit.xml").exists()


def test_write_junit_returns_path(tmp_path, sample_results):
    run_dir = tmp_path / "run2"
    run_dir.mkdir()
    path = write_junit(run_dir, sample_results)
    assert path == run_dir / "junit.xml"


def test_junit_testsuites_count(sample_run_dir):
    xml = JUnitXml.fromfile(str(sample_run_dir / "junit.xml"))
    suites = list(xml)
    assert len(suites) == 2


def test_junit_testsuite_names(sample_run_dir):
    xml = JUnitXml.fromfile(str(sample_run_dir / "junit.xml"))
    names = {s.name for s in xml}
    assert "claude-baseline / task-1" in names
    assert "codex-baseline / task-1" in names


def test_junit_testcase_count(sample_run_dir):
    xml = JUnitXml.fromfile(str(sample_run_dir / "junit.xml"))
    for suite in xml:
        assert suite.tests == 3


def test_junit_failure_recorded(sample_run_dir):
    xml = JUnitXml.fromfile(str(sample_run_dir / "junit.xml"))
    codex_suite = next(s for s in xml if s.name == "codex-baseline / task-1")
    assert codex_suite.failures == 1
    failing_case = next(c for c in codex_suite if c.name == "file_exists: variables.tf")
    assert any(isinstance(r, Failure) for r in failing_case.result)


def test_junit_failure_message(sample_run_dir):
    xml = JUnitXml.fromfile(str(sample_run_dir / "junit.xml"))
    codex_suite = next(s for s in xml if s.name == "codex-baseline / task-1")
    failing_case = next(c for c in codex_suite if c.name == "file_exists: variables.tf")
    failure = next(r for r in failing_case.result if isinstance(r, Failure))
    assert failure.message == "File not found"


def test_junit_passing_suite_no_failures(sample_run_dir):
    xml = JUnitXml.fromfile(str(sample_run_dir / "junit.xml"))
    claude_suite = next(s for s in xml if s.name == "claude-baseline / task-1")
    assert claude_suite.failures == 0


def test_junit_testcase_classname(sample_run_dir):
    xml = JUnitXml.fromfile(str(sample_run_dir / "junit.xml"))
    suite = next(s for s in xml if s.name == "claude-baseline / task-1")
    for case in suite:
        assert case.classname == "task-1"


def test_junit_suite_time(sample_run_dir):
    xml = JUnitXml.fromfile(str(sample_run_dir / "junit.xml"))
    claude_suite = next(s for s in xml if s.name == "claude-baseline / task-1")
    assert claude_suite.time == 10.5


def test_junit_properties_present(sample_run_dir):
    xml = JUnitXml.fromfile(str(sample_run_dir / "junit.xml"))
    claude_suite = next(s for s in xml if s.name == "claude-baseline / task-1")
    prop_names = {p.name for p in claude_suite.properties()}
    assert "weighted_score" in prop_names
    assert "assertion_pass_rate" in prop_names
    assert "cost_usd" in prop_names


def test_junit_repeat_stats_properties(repeat_run_dir):
    xml = JUnitXml.fromfile(str(repeat_run_dir / "junit.xml"))
    suite = next(iter(xml))
    prop_names = {p.name for p in suite.properties()}
    assert "wall_clock_seconds_avg" in prop_names
    assert "wall_clock_seconds_stddev" in prop_names
    assert "cost_usd_avg" in prop_names


# ---------------------------------------------------------------------------
# generate_report tests
# ---------------------------------------------------------------------------


def test_generate_report_creates_html(sample_run_dir):
    report_path = generate_report(sample_run_dir)
    assert report_path.exists()
    assert report_path.suffix == ".html"


def test_generate_report_returns_path(sample_run_dir):
    report_path = generate_report(sample_run_dir)
    assert report_path == sample_run_dir / "report.html"


def test_generate_report_html_non_empty(sample_run_dir):
    report_path = generate_report(sample_run_dir)
    assert len(report_path.read_text()) > 100


# ---------------------------------------------------------------------------
# Report reframing: multi-metric optimization view
# ---------------------------------------------------------------------------


def test_report_no_pass_fail_summary_cards(sample_run_dir):
    """Report should NOT contain Passed/Failed summary cards."""
    html = generate_report(sample_run_dir).read_text()
    assert '<div class="card passed">' not in html
    assert '<div class="card failed">' not in html
    # Should have the new cards instead
    assert '<div class="card configurations">' in html
    assert '<div class="card avg-score">' in html


def test_report_has_score_pills(sample_run_dir):
    """Report should contain color-coded score pills."""
    html = generate_report(sample_run_dir).read_text()
    assert "score-pill" in html


def test_report_has_charts(sample_run_dir):
    """Report should have cost-vs-time chart and explore chart with mini-tabs."""
    html = generate_report(sample_run_dir).read_text()
    assert "chart-cost-time" in html
    assert "chart-explore" in html
    assert "chart-tabs" in html
    assert "renderExploreChart" in html
    # No top-level tab navigation
    assert '<nav class="tab-bar">' not in html


def test_report_has_unified_config_section(sample_run_dir):
    """Report should have a single unified configuration results section."""
    html = generate_report(sample_run_dir).read_text()
    # Unified section with agent cards (not a separate collapsible details section)
    assert "agent-card" in html
    assert "agent-detail" in html
    # No duplicate summary table
    assert "summary-table" not in html


def test_report_sorts_by_score_descending(sample_run_dir):
    """Summary table should show highest-scoring configurations first."""
    html = generate_report(sample_run_dir).read_text()
    # claude-baseline scores 100.0, codex-baseline scores 66.67
    # claude-baseline should appear before codex-baseline
    claude_pos = html.index("claude-baseline")
    codex_pos = html.index("codex-baseline")
    assert claude_pos < codex_pos


def test_report_has_chart_canvas(sample_run_dir):
    """Report should contain canvas elements for both charts."""
    html = generate_report(sample_run_dir).read_text()
    assert "<canvas" in html
    assert "chart-cost-time" in html
    assert "chart-explore" in html


def test_report_has_chart_data_json(sample_run_dir):
    """Report should contain valid chart data JSON."""
    html = generate_report(sample_run_dir).read_text()
    assert "var chartData = " in html
    # Extract the JSON from the script and validate it
    marker = "var chartData = "
    start = html.index(marker) + len(marker)
    end = html.index(";", start)
    chart_json = html[start:end]
    data = json.loads(chart_json)
    assert isinstance(data, list)
    assert len(data) > 0
    assert "score" in data[0]
    assert "assistant" in data[0]


def test_report_summary_shows_configurations_count(sample_run_dir):
    """Summary should show 'N configurations' not 'N tests'."""
    html = generate_report(sample_run_dir).read_text()
    # Header badge should say "configurations"
    assert "configurations" in html
    # Should NOT have the old "all passed" badge
    assert "all passed" not in html


def test_report_task_header_shows_avg_score(sample_run_dir):
    """Task header should show average score instead of pass/fail count."""
    html = generate_report(sample_run_dir).read_text()
    # Task headers should NOT have "X failed" or "X/Y passed" text
    assert (
        "failed</span>" not in html
        or "badge-fail" not in html.split("task-header")[1].split("</div>")[0]
    )
    # Should have Avg metric in task header area
    assert "Avg:" in html


def test_report_agent_summary_has_score_pill(sample_run_dir):
    """Agent summary should show score pills with data-score attributes for client-side coloring."""
    html = generate_report(sample_run_dir).read_text()
    assert "score-pill" in html
    assert 'data-score="100.0"' in html
    assert 'data-score="66.67"' in html


def test_report_preserves_per_assertion_pass_fail(sample_run_dir):
    """Individual assertion PASS/FAIL badges should still be present in test cases."""
    html = generate_report(sample_run_dir).read_text()
    assert "badge badge-pass" in html
    assert "PASS" in html
    assert "FAIL" in html


def test_report_chart_data_includes_cost_and_latency(sample_run_dir):
    """Chart data should include cost and latency fields."""
    html = generate_report(sample_run_dir).read_text()
    marker = "var chartData = "
    start = html.index(marker) + len(marker)
    end = html.index(";", start)
    data = json.loads(html[start:end])
    # claude-baseline has cost_usd=0.03 and time=10.5
    claude_entry = next(d for d in data if "claude" in d["assistant"])
    assert claude_entry["cost"] == 0.03
    assert claude_entry["latency"] == 10.5
