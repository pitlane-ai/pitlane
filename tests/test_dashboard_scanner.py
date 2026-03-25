from __future__ import annotations

import yaml

from tests.helpers import make_run
from pitlane.reporting.junit import write_junit
from pitlane.dashboard.scanner import scan_runs


def test_scan_runs_empty_dir(tmp_path):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    assert scan_runs(runs_dir) == []


def test_scan_runs_nonexistent_dir(tmp_path):
    assert scan_runs(tmp_path / "nonexistent") == []


def test_scan_runs_finds_valid_run(tmp_path):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    make_run(runs_dir, "2026-01-15_100000", "2026-01-15T10:00:00+00:00")

    results = scan_runs(runs_dir)
    assert len(results) == 1
    assert results[0].run_id == "2026-01-15_100000"
    assert len(results[0].suites) == 1
    assert results[0].suites[0].assistant == "claude-baseline"
    assert results[0].suites[0].task == "task-1"


def test_scan_runs_skips_dir_without_meta(tmp_path):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    # Create a dir with only junit.xml, no meta.yaml
    bad_run = runs_dir / "bad-run"
    bad_run.mkdir()
    write_junit(
        bad_run,
        {
            "a": {
                "t": {
                    "metrics": {"weighted_score": 50.0},
                    "assertions": [],
                    "all_passed": True,
                }
            }
        },
    )

    assert scan_runs(runs_dir) == []


def test_scan_runs_skips_dir_without_junit(tmp_path):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    bad_run = runs_dir / "bad-run"
    bad_run.mkdir()
    (bad_run / "meta.yaml").write_text(
        yaml.dump({"timestamp": "2026-01-01T00:00:00+00:00"})
    )

    assert scan_runs(runs_dir) == []


def test_scan_runs_extracts_metrics(tmp_path):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    make_run(runs_dir, "run1", "2026-01-15T10:00:00+00:00")

    results = scan_runs(runs_dir)
    suite = results[0].suites[0]
    assert suite.weighted_score == 85.0
    assert suite.assertion_pass_rate == 100.0
    assert suite.cost_usd == 0.03
    assert suite.token_usage_input == 500.0
    assert suite.token_usage_output == 200.0
    assert suite.tool_calls_count == 5.0


def test_scan_runs_sorted_by_timestamp(tmp_path):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    make_run(runs_dir, "run-late", "2026-03-01T12:00:00+00:00")
    make_run(runs_dir, "run-early", "2026-01-01T12:00:00+00:00")
    make_run(runs_dir, "run-mid", "2026-02-01T12:00:00+00:00")

    results = scan_runs(runs_dir)
    assert len(results) == 3
    assert results[0].run_id == "run-early"
    assert results[1].run_id == "run-mid"
    assert results[2].run_id == "run-late"


def test_scan_runs_date_filter_from(tmp_path):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    make_run(runs_dir, "old", "2026-01-01T10:00:00+00:00")
    make_run(runs_dir, "new", "2026-03-01T10:00:00+00:00")

    results = scan_runs(runs_dir, date_from="2026-02-01")
    assert len(results) == 1
    assert results[0].run_id == "new"


def test_scan_runs_date_filter_to(tmp_path):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    make_run(runs_dir, "old", "2026-01-01T10:00:00+00:00")
    make_run(runs_dir, "new", "2026-03-01T10:00:00+00:00")

    results = scan_runs(runs_dir, date_to="2026-02-01")
    assert len(results) == 1
    assert results[0].run_id == "old"


def test_scan_runs_date_filter_range(tmp_path):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    make_run(runs_dir, "jan", "2026-01-15T10:00:00+00:00")
    make_run(runs_dir, "feb", "2026-02-15T10:00:00+00:00")
    make_run(runs_dir, "mar", "2026-03-15T10:00:00+00:00")

    results = scan_runs(runs_dir, date_from="2026-02-01", date_to="2026-02-28")
    assert len(results) == 1
    assert results[0].run_id == "feb"


def test_scan_runs_to_date_inclusive(tmp_path):
    """The to date should include runs from that entire day."""
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    make_run(runs_dir, "run", "2026-02-15T23:59:00+00:00")

    results = scan_runs(runs_dir, date_to="2026-02-15")
    assert len(results) == 1


def test_scan_runs_multiple_assistants(tmp_path):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    results_data = {
        "claude-baseline": {
            "task-1": {
                "metrics": {"weighted_score": 80.0, "assertion_pass_rate": 100.0},
                "assertions": [{"name": "a", "passed": True, "message": ""}],
                "all_passed": True,
            }
        },
        "claude-with-skill": {
            "task-1": {
                "metrics": {"weighted_score": 95.0, "assertion_pass_rate": 100.0},
                "assertions": [{"name": "a", "passed": True, "message": ""}],
                "all_passed": True,
            }
        },
    }
    make_run(runs_dir, "run1", "2026-01-15T10:00:00+00:00", results_data)

    results = scan_runs(runs_dir)
    assert len(results) == 1
    assert len(results[0].suites) == 2
    assert set(results[0].assistants) == {"claude-baseline", "claude-with-skill"}


def test_scan_runs_default_repeat(tmp_path):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    make_run(runs_dir, "run1", "2026-01-15T10:00:00+00:00")

    results = scan_runs(runs_dir)
    assert results[0].repeat == 1


def test_scan_runs_repeat_from_meta(tmp_path):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    run_dir = make_run(runs_dir, "run1", "2026-01-15T10:00:00+00:00")
    # Overwrite meta.yaml with repeat=3
    meta = yaml.safe_load((run_dir / "meta.yaml").read_text())
    meta["repeat"] = 3
    (run_dir / "meta.yaml").write_text(yaml.dump(meta))

    results = scan_runs(runs_dir)
    assert results[0].repeat == 3


def test_run_summary_to_dict(tmp_path):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    make_run(runs_dir, "run1", "2026-01-15T10:00:00+00:00")

    results = scan_runs(runs_dir)
    d = results[0].to_dict()
    assert isinstance(d, dict)
    assert d["run_id"] == "run1"
    assert d["repeat"] == 1
    assert isinstance(d["suites"], list)
    assert isinstance(d["suites"][0], dict)
    assert "weighted_score" in d["suites"][0]
