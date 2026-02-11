import pytest
from pathlib import Path
from agent_eval.metrics import collect_metrics
from agent_eval.adapters.base import AdapterResult
from agent_eval.assertions.base import AssertionResult


def test_collect_metrics_basic(tmp_path):
    # Simulate workspace before/after
    workspace_before = {"existing.tf"}
    workspace = tmp_path
    (workspace / "existing.tf").write_text("modified content\nsecond line")
    (workspace / "new.tf").write_text("new file\nline 2\nline 3")

    adapter_result = AdapterResult(
        stdout="output",
        stderr="",
        exit_code=0,
        duration_seconds=12.5,
        conversation=[{"role": "assistant"}, {"role": "assistant", "tool_use": {"name": "Bash"}}],
        token_usage={"input": 500, "output": 200},
        cost_usd=0.03,
        tool_calls_count=1,
    )

    assertion_results = [
        AssertionResult(name="a1", passed=True, message="", score=1.0),
        AssertionResult(name="a2", passed=True, message="", score=1.0),
        AssertionResult(name="a3", passed=False, message="failed", score=0.0),
    ]

    metrics = collect_metrics(
        adapter_result=adapter_result,
        assertion_results=assertion_results,
        workspace=workspace,
        files_before=workspace_before,
    )

    assert metrics["wall_clock_seconds"] == 12.5
    assert metrics["exit_code"] == 0
    assert metrics["files_created"] == 1  # new.tf
    assert metrics["files_modified"] == 1  # existing.tf
    assert metrics["token_usage_input"] == 500
    assert metrics["token_usage_output"] == 200
    assert metrics["cost_usd"] == 0.03
    assert metrics["tool_calls_count"] == 1
    assert metrics["assertion_pass_count"] == 2
    assert metrics["assertion_fail_count"] == 1
    assert metrics["assertion_pass_rate"] == pytest.approx(66.67, abs=0.1)
    # weighted_score: (1.0 + 1.0 + 0.0) / 3.0 * 100 = 66.67
    assert metrics["weighted_score"] == pytest.approx(66.67, abs=0.1)


def test_weighted_score_with_equal_weights(tmp_path):
    """When all weights are 1.0, weighted_score equals pass_rate for binary assertions."""
    workspace = tmp_path
    (workspace / "f.txt").write_text("x")

    adapter_result = AdapterResult(
        stdout="", stderr="", exit_code=0, duration_seconds=1.0,
    )

    assertion_results = [
        AssertionResult(name="a1", passed=True, message="", score=1.0, weight=1.0),
        AssertionResult(name="a2", passed=False, message="", score=0.0, weight=1.0),
    ]

    metrics = collect_metrics(
        adapter_result=adapter_result,
        assertion_results=assertion_results,
        workspace=workspace,
        files_before=set(),
    )

    assert metrics["assertion_pass_rate"] == 50.0
    assert metrics["weighted_score"] == 50.0


def test_weighted_score_with_different_weights(tmp_path):
    """Higher-weighted assertions should contribute more to the score."""
    workspace = tmp_path
    (workspace / "f.txt").write_text("x")

    adapter_result = AdapterResult(
        stdout="", stderr="", exit_code=0, duration_seconds=1.0,
    )

    # a1 passes with weight 3, a2 fails with weight 1
    # weighted_score = (3*1.0 + 1*0.0) / (3+1) * 100 = 75.0
    assertion_results = [
        AssertionResult(name="a1", passed=True, message="", score=1.0, weight=3.0),
        AssertionResult(name="a2", passed=False, message="", score=0.0, weight=1.0),
    ]

    metrics = collect_metrics(
        adapter_result=adapter_result,
        assertion_results=assertion_results,
        workspace=workspace,
        files_before=set(),
    )

    assert metrics["assertion_pass_rate"] == 50.0  # unweighted: 1/2
    assert metrics["weighted_score"] == 75.0  # weighted: 3/4


def test_weighted_score_with_continuous_scores(tmp_path):
    """Similarity assertions contribute their continuous score, not just 0/1."""
    workspace = tmp_path
    (workspace / "f.txt").write_text("x")

    adapter_result = AdapterResult(
        stdout="", stderr="", exit_code=0, duration_seconds=1.0,
    )

    # Binary assertion passes (score=1.0), similarity has normalized score 0.8
    # (e.g. raw 0.56 with min_score 0.7 → min(0.56/0.7, 1.0) = 0.8)
    # weighted_score = (1.0*1.0 + 0.8*1.0) / 2.0 * 100 = 90.0
    assertion_results = [
        AssertionResult(name="file_exists:f", passed=True, message="", score=1.0, weight=1.0),
        AssertionResult(name="rouge:a:b", passed=True, message="score=0.8000", score=0.8, weight=1.0),
    ]

    metrics = collect_metrics(
        adapter_result=adapter_result,
        assertion_results=assertion_results,
        workspace=workspace,
        files_before=set(),
    )

    assert metrics["assertion_pass_rate"] == 100.0  # both passed
    assert metrics["weighted_score"] == 90.0  # but weighted score reflects partial similarity


def test_weighted_score_empty_assertions(tmp_path):
    """No assertions should yield 0.0 weighted score."""
    workspace = tmp_path
    (workspace / "f.txt").write_text("x")

    adapter_result = AdapterResult(
        stdout="", stderr="", exit_code=0, duration_seconds=1.0,
    )

    metrics = collect_metrics(
        adapter_result=adapter_result,
        assertion_results=[],
        workspace=workspace,
        files_before=set(),
    )

    assert metrics["weighted_score"] == 0.0
