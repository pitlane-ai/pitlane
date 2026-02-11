import json
import pytest
import yaml
from concurrent.futures import as_completed
from pathlib import Path
from unittest.mock import patch, MagicMock
from agent_eval.runner import Runner
from agent_eval.adapters.base import AdapterResult
from agent_eval.config import load_config


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
        stdout="", stderr="", exit_code=0, duration_seconds=1.0,
    )
    with patch("agent_eval.adapters.claude_code.ClaudeCodeAdapter.run", return_value=mock_result):
        run_dir = runner.execute()

    assert run_dir.exists()
    assert (run_dir / "results.json").exists()
    assert (run_dir / "meta.yaml").exists()
    assert (run_dir / "debug.log").exists()


def test_runner_captures_results(tmp_path, eval_config):
    runner = Runner(config=eval_config, output_dir=tmp_path / "runs", verbose=False)

    mock_result = AdapterResult(
        stdout="", stderr="", exit_code=0, duration_seconds=1.0,
        token_usage={"input": 100, "output": 50}, cost_usd=0.01,
    )
    with patch("agent_eval.adapters.claude_code.ClaudeCodeAdapter.run", return_value=mock_result):
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

    runner = Runner(config=parallel_config, output_dir=tmp_path / "runs", verbose=False, parallel_tasks=2)

    mock_result = AdapterResult(
        stdout="", stderr="", exit_code=0, duration_seconds=0.1,
    )
    with patch("agent_eval.adapters.claude_code.ClaudeCodeAdapter.run", return_value=mock_result):
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
    runner = Runner(config=eval_config, output_dir=tmp_path / "runs", verbose=False, parallel_tasks=1)

    mock_result = AdapterResult(
        stdout="", stderr="", exit_code=0, duration_seconds=1.0,
    )
    with patch("agent_eval.adapters.claude_code.ClaudeCodeAdapter.run", return_value=mock_result):
        run_dir = runner.execute()

    results = json.loads((run_dir / "results.json").read_text())
    assert "mock-claude" in results
    assert "simple-test" in results["mock-claude"]


def test_runner_default_parallel_tasks(tmp_path, eval_config):
    """Test that default parallel_tasks is 1 (sequential)."""
    runner = Runner(config=eval_config, output_dir=tmp_path / "runs", verbose=False)
    assert runner.parallel_tasks == 1


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
        "metrics": {"wall_clock_seconds": 0.1},
        "assertions": [{"name": "file_exists: test.txt", "passed": True, "message": "ok"}],
        "all_passed": True,
    }

    original_as_completed = as_completed

    def mock_as_completed(futures):
        """Yield one completed future then raise KeyboardInterrupt."""
        iterator = original_as_completed(futures)
        yield next(iterator)
        raise KeyboardInterrupt()

    runner = Runner(config=config, output_dir=tmp_path / "runs", verbose=False, parallel_tasks=1)

    with patch.object(runner, "_run_task", return_value=completed_result), \
         patch("agent_eval.runner.as_completed", side_effect=mock_as_completed):
        run_dir = runner.execute()

    # Runner should be marked as interrupted
    assert runner.interrupted is True

    # Partial results should be saved
    assert (run_dir / "results.json").exists()
    assert (run_dir / "meta.yaml").exists()

    results = json.loads((run_dir / "results.json").read_text())
    assert "mock-claude" in results
    # At least one task should have completed
    assert len(results["mock-claude"]) >= 1

    # Meta should indicate interrupted
    meta = yaml.safe_load((run_dir / "meta.yaml").read_text())
    assert meta["interrupted"] is True


def test_runner_interrupt_report_generation(tmp_path):
    """Test that a report can be generated from partial results."""
    from agent_eval.reporting.html import generate_report

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
            "wall_clock_seconds": 0.1, "exit_code": 0, "files_created": 0,
            "files_modified": 0, "total_lines_generated": 0,
            "token_usage_input": 0, "token_usage_output": 0,
            "cost_usd": 0.0, "tool_calls_count": 0,
            "assertion_pass_count": 1, "assertion_fail_count": 0,
            "assertion_pass_rate": 100.0,
        },
        "assertions": [{"name": "file_exists: test.txt", "passed": True, "message": "ok"}],
        "all_passed": True,
    }

    original_as_completed = as_completed

    def mock_as_completed(futures):
        iterator = original_as_completed(futures)
        yield next(iterator)
        raise KeyboardInterrupt()

    runner = Runner(config=config, output_dir=tmp_path / "runs", verbose=False, parallel_tasks=1)

    with patch.object(runner, "_run_task", return_value=completed_result), \
         patch("agent_eval.runner.as_completed", side_effect=mock_as_completed):
        run_dir = runner.execute()

    # Report should be generatable from partial results
    report_path = generate_report(run_dir)
    assert report_path.exists()
    html_content = report_path.read_text()
    assert "task-" in html_content
