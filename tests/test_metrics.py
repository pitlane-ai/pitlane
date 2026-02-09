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
    )

    assertion_results = [
        AssertionResult(name="a1", passed=True, message=""),
        AssertionResult(name="a2", passed=True, message=""),
        AssertionResult(name="a3", passed=False, message="failed"),
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
