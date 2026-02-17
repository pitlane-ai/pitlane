import json
import pytest
import yaml
from concurrent.futures import as_completed
from unittest.mock import patch
from pitlane.runner import Runner, IterationResult
from pitlane.metrics import compute_stats, aggregate_results
from pitlane.adapters.base import AdapterResult
from pitlane.config import load_config


@pytest.fixture
def eval_config(tmp_path):
    fixture_dir = tmp_path / "fixtures" / "empty"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / ".gitkeep").write_text("")

    config_file = tmp_path / "eval.yaml"
    config_file.write_text(f"""
assistants:
  mock-claude:
    adapter: claude-code
    args:
      model: sonnet

tasks:
  - name: simple-test
    prompt: "Create hello.py"
    workdir: {fixture_dir}
    timeout: 10
    assertions:
      - file_exists: "hello.py"
""")
    return load_config(config_file)


def test_runner_creates_run_directory(tmp_path, eval_config):
    runner = Runner(config=eval_config, output_dir=tmp_path / "runs", verbose=False)

    mock_result = AdapterResult(
        stdout="",
        stderr="",
        exit_code=0,
        duration_seconds=1.0,
    )
    with patch(
        "pitlane.adapters.claude_code.ClaudeCodeAdapter.run",
        return_value=mock_result,
    ):
        run_dir = runner.execute()

    assert run_dir.exists()
    assert (run_dir / "results.json").exists()
    assert (run_dir / "meta.yaml").exists()
    assert (run_dir / "debug.log").exists()


def test_runner_captures_results(tmp_path, eval_config):
    runner = Runner(config=eval_config, output_dir=tmp_path / "runs", verbose=False)

    mock_result = AdapterResult(
        stdout="",
        stderr="",
        exit_code=0,
        duration_seconds=1.0,
        token_usage={"input": 100, "output": 50},
        cost_usd=0.01,
    )
    with patch(
        "pitlane.adapters.claude_code.ClaudeCodeAdapter.run",
        return_value=mock_result,
    ):
        run_dir = runner.execute()

    results = json.loads((run_dir / "results.json").read_text())
    assert "mock-claude" in results
    assert "simple-test" in results["mock-claude"]
    task_result = results["mock-claude"]["simple-test"]
    assert "metrics" in task_result
    assert "assertions" in task_result


def test_runner_parallel_execution(tmp_path, eval_config):
    """Test that parallel execution works correctly."""
    # Create a config with multiple tasks
    fixture_dir = tmp_path / "fixtures" / "empty"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    (fixture_dir / "test.txt").write_text("test")

    config_file = tmp_path / "parallel_eval.yaml"
    config_file.write_text(f"""
assistants:
  mock-claude:
    adapter: claude-code
    args:
      model: sonnet

tasks:
  - name: task-1
    prompt: "Task 1"
    workdir: {fixture_dir}
    timeout: 10
    assertions:
      - file_exists: "test.txt"
  - name: task-2
    prompt: "Task 2"
    workdir: {fixture_dir}
    timeout: 10
    assertions:
      - file_exists: "test.txt"
  - name: task-3
    prompt: "Task 3"
    workdir: {fixture_dir}
    timeout: 10
    assertions:
      - file_exists: "test.txt"
""")
    parallel_config = load_config(config_file)

    runner = Runner(
        config=parallel_config,
        output_dir=tmp_path / "runs",
        verbose=False,
        parallel_tasks=2,
    )

    mock_result = AdapterResult(
        stdout="",
        stderr="",
        exit_code=0,
        duration_seconds=0.1,
    )
    with patch(
        "pitlane.adapters.claude_code.ClaudeCodeAdapter.run",
        return_value=mock_result,
    ):
        run_dir = runner.execute()

    # Verify all tasks completed successfully
    results = json.loads((run_dir / "results.json").read_text())
    assert "mock-claude" in results
    assert len(results["mock-claude"]) == 3
    assert "task-1" in results["mock-claude"]
    assert "task-2" in results["mock-claude"]
    assert "task-3" in results["mock-claude"]

    # Verify all tasks have results
    for task_name in ["task-1", "task-2", "task-3"]:
        task_result = results["mock-claude"][task_name]
        assert "metrics" in task_result
        assert "assertions" in task_result


def test_runner_sequential_execution(tmp_path, eval_config):
    """Test that sequential execution works when parallel_tasks=1."""
    runner = Runner(
        config=eval_config,
        output_dir=tmp_path / "runs",
        verbose=False,
        parallel_tasks=1,
    )

    mock_result = AdapterResult(
        stdout="",
        stderr="",
        exit_code=0,
        duration_seconds=1.0,
    )
    with patch(
        "pitlane.adapters.claude_code.ClaudeCodeAdapter.run",
        return_value=mock_result,
    ):
        run_dir = runner.execute()

    results = json.loads((run_dir / "results.json").read_text())
    assert "mock-claude" in results
    assert "simple-test" in results["mock-claude"]


def test_runner_default_parallel_tasks(tmp_path, eval_config):
    """Test that default parallel_tasks is 1 (sequential)."""
    runner = Runner(config=eval_config, output_dir=tmp_path / "runs", verbose=False)
    assert runner.parallel_tasks == 1


def test_runner_default_repeat(tmp_path, eval_config):
    """Test that default repeat is 1."""
    runner = Runner(config=eval_config, output_dir=tmp_path / "runs", verbose=False)
    assert runner.repeat == 1


def test_runner_repeat_execution(tmp_path, eval_config):
    """Test that repeat=3 runs the task 3 times and aggregates results."""
    runner = Runner(
        config=eval_config, output_dir=tmp_path / "runs", verbose=False, repeat=3
    )

    call_count = 0

    def mock_run(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return AdapterResult(
            stdout="",
            stderr="",
            exit_code=0,
            duration_seconds=float(call_count),
            token_usage={"input": 100 * call_count, "output": 50 * call_count},
            cost_usd=0.01 * call_count,
        )

    with patch(
        "pitlane.adapters.claude_code.ClaudeCodeAdapter.run", side_effect=mock_run
    ):
        run_dir = runner.execute()

    assert call_count == 3

    results = json.loads((run_dir / "results.json").read_text())
    task_result = results["mock-claude"]["simple-test"]

    # Should have aggregated structure
    assert "repeat" in task_result
    assert task_result["repeat"]["count"] == 3
    assert len(task_result["repeat"]["iterations"]) == 3
    assert "metrics_stats" in task_result

    # Metrics should be averages
    assert task_result["metrics"]["wall_clock_seconds"] is not None

    # Stats should have avg, min, max, stddev
    wc_stats = task_result["metrics_stats"]["wall_clock_seconds"]
    assert "avg" in wc_stats
    assert "min" in wc_stats
    assert "max" in wc_stats
    assert "stddev" in wc_stats


def test_runner_repeat_meta_includes_repeat_count(tmp_path, eval_config):
    """Test that meta.yaml includes the repeat count."""
    import yaml

    runner = Runner(
        config=eval_config, output_dir=tmp_path / "runs", verbose=False, repeat=5
    )

    mock_result = AdapterResult(
        stdout="",
        stderr="",
        exit_code=0,
        duration_seconds=1.0,
    )
    with patch(
        "pitlane.adapters.claude_code.ClaudeCodeAdapter.run",
        return_value=mock_result,
    ):
        run_dir = runner.execute()

    meta = yaml.safe_load((run_dir / "meta.yaml").read_text())
    assert meta["repeat"] == 5


def test_compute_stats_basic():
    """Test compute_stats with normal values."""
    stats = compute_stats([1.0, 2.0, 3.0])
    assert stats.avg == 2.0
    assert stats.min == 1.0
    assert stats.max == 3.0
    assert stats.stddev == 0.8165  # population std dev


def test_compute_stats_single_value():
    """Test compute_stats with a single value."""
    stats = compute_stats([5.0])
    assert stats.avg == 5.0
    assert stats.min == 5.0
    assert stats.max == 5.0
    assert stats.stddev == 0.0


def test_compute_stats_with_nones():
    """Test compute_stats filters out None values."""
    stats = compute_stats([1.0, None, 3.0])
    assert stats.avg == 2.0
    assert stats.min == 1.0
    assert stats.max == 3.0


def test_compute_stats_all_nones():
    """Test compute_stats with all None values."""
    stats = compute_stats([None, None])
    assert stats.avg is None
    assert stats.min is None
    assert stats.max is None
    assert stats.stddev is None


def test_aggregate_results():
    """Test aggregate_results produces correct structure."""

    run_results = [
        IterationResult(
            metrics={
                "wall_clock_seconds": 1.0,
                "exit_code": 0,
                "assertion_pass_rate": 100.0,
            },
            assertions=[
                {"name": "file_exists:test.py", "passed": True, "message": "exists"}
            ],
            all_passed=True,
        ),
        IterationResult(
            metrics={
                "wall_clock_seconds": 3.0,
                "exit_code": 0,
                "assertion_pass_rate": 100.0,
            },
            assertions=[
                {"name": "file_exists:test.py", "passed": True, "message": "exists"}
            ],
            all_passed=True,
        ),
        IterationResult(
            metrics={
                "wall_clock_seconds": 2.0,
                "exit_code": 1,
                "assertion_pass_rate": 0.0,
            },
            assertions=[
                {"name": "file_exists:test.py", "passed": False, "message": "not found"}
            ],
            all_passed=False,
        ),
    ]

    result = aggregate_results(run_results)

    assert result.repeat.count == 3
    assert result.repeat.all_passed_count == 2
    assert result.repeat.all_passed_rate == pytest.approx(66.7, abs=0.1)
    assert result.all_passed is False

    # Metrics should be averages
    assert result.metrics["wall_clock_seconds"] == 2.0

    # Stats
    assert result.metrics_stats["wall_clock_seconds"].avg == 2.0
    assert result.metrics_stats["wall_clock_seconds"].min == 1.0
    assert result.metrics_stats["wall_clock_seconds"].max == 3.0

    # Assertions summary
    assert len(result.assertions) == 1
    assert result.assertions[0].pass_rate == pytest.approx(66.7, abs=0.1)
    assert result.assertions[0].message == "Passed 2/3 iterations"

    # Iterations preserved
    assert len(result.repeat.iterations) == 3


def test_runner_interrupt_saves_partial_results(tmp_path):
    """Test that interrupting a run saves partial results and generates report."""
    fixture_dir = tmp_path / "fixtures" / "empty"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "test.txt").write_text("test")

    config_file = tmp_path / "eval.yaml"
    config_file.write_text(f"""
assistants:
  mock-claude:
    adapter: claude-code
    args:
      model: sonnet

tasks:
  - name: task-1
    prompt: "Task 1"
    workdir: {fixture_dir}
    timeout: 10
    assertions:
      - file_exists: "test.txt"
  - name: task-2
    prompt: "Task 2"
    workdir: {fixture_dir}
    timeout: 10
    assertions:
      - file_exists: "test.txt"
  - name: task-3
    prompt: "Task 3"
    workdir: {fixture_dir}
    timeout: 10
    assertions:
      - file_exists: "test.txt"
""")
    config = load_config(config_file)

    completed_result = {
        "metrics": {
            "wall_clock_seconds": 0.1,
            "exit_code": 0,
            "files_created": 0,
            "files_modified": 0,
            "total_lines_generated": 0,
            "token_usage_input": 0,
            "token_usage_output": 0,
            "cost_usd": 0.0,
            "tool_calls_count": 0,
            "assertion_pass_count": 1,
            "assertion_fail_count": 0,
            "assertion_pass_rate": 100.0,
            "weighted_score": 100.0,
        },
        "assertions": [
            {
                "name": "file_exists: test.txt",
                "passed": True,
                "message": "ok",
                "score": 1.0,
                "weight": 1.0,
            }
        ],
        "all_passed": True,
    }

    original_as_completed = as_completed

    def mock_as_completed(futures):
        """Yield one completed future then raise KeyboardInterrupt."""
        iterator = original_as_completed(futures)
        yield next(iterator)
        raise KeyboardInterrupt()

    runner = Runner(
        config=config, output_dir=tmp_path / "runs", verbose=False, parallel_tasks=1
    )

    with (
        patch.object(runner, "_run_task", return_value=completed_result),
        patch("pitlane.runner.as_completed", side_effect=mock_as_completed),
    ):
        run_dir = runner.execute()

    # Runner should be marked as interrupted
    assert runner.interrupted is True

    # Partial results should be saved
    assert (run_dir / "results.json").exists()
    assert (run_dir / "meta.yaml").exists()

    results = json.loads((run_dir / "results.json").read_text())
    assert "mock-claude" in results
    # At least one task should have completed (results are now aggregated)
    assert len(results["mock-claude"]) >= 1

    # Verify aggregated structure exists for completed tasks
    for task_name, task_result in results["mock-claude"].items():
        assert "repeat" in task_result
        assert "metrics" in task_result
        assert "assertions" in task_result

    # Meta should indicate interrupted
    meta = yaml.safe_load((run_dir / "meta.yaml").read_text())
    assert meta["interrupted"] is True


def test_runner_interrupt_report_generation(tmp_path):
    """Test that a report can be generated from partial results."""
    from pitlane.reporting.html import generate_report

    fixture_dir = tmp_path / "fixtures" / "empty"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "test.txt").write_text("test")

    config_file = tmp_path / "eval.yaml"
    config_file.write_text(f"""
assistants:
  mock-claude:
    adapter: claude-code
    args:
      model: sonnet

tasks:
  - name: task-1
    prompt: "Task 1"
    workdir: {fixture_dir}
    timeout: 10
    assertions:
      - file_exists: "test.txt"
  - name: task-2
    prompt: "Task 2"
    workdir: {fixture_dir}
    timeout: 10
    assertions:
      - file_exists: "test.txt"
""")
    config = load_config(config_file)

    completed_result = {
        "metrics": {
            "wall_clock_seconds": 0.1,
            "exit_code": 0,
            "files_created": 0,
            "files_modified": 0,
            "total_lines_generated": 0,
            "token_usage_input": 0,
            "token_usage_output": 0,
            "cost_usd": 0.0,
            "tool_calls_count": 0,
            "assertion_pass_count": 1,
            "assertion_fail_count": 0,
            "assertion_pass_rate": 100.0,
            "weighted_score": 100.0,
        },
        "assertions": [
            {
                "name": "file_exists: test.txt",
                "passed": True,
                "message": "ok",
                "score": 1.0,
                "weight": 1.0,
            }
        ],
        "all_passed": True,
    }

    original_as_completed = as_completed

    def mock_as_completed(futures):
        iterator = original_as_completed(futures)
        yield next(iterator)
        raise KeyboardInterrupt()

    runner = Runner(
        config=config, output_dir=tmp_path / "runs", verbose=False, parallel_tasks=1
    )

    with (
        patch.object(runner, "_run_task", return_value=completed_result),
        patch("pitlane.runner.as_completed", side_effect=mock_as_completed),
    ):
        run_dir = runner.execute()

    # Report should be generatable from partial results
    report_path = generate_report(run_dir)
    assert report_path.exists()
    html_content = report_path.read_text()
    assert "task-" in html_content
