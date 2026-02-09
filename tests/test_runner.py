import json
import pytest
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
    runner = Runner(config=eval_config, output_dir=tmp_path / "runs")

    mock_result = AdapterResult(
        stdout="", stderr="", exit_code=0, duration_seconds=1.0,
    )
    with patch("agent_eval.adapters.claude_code.ClaudeCodeAdapter.run", return_value=mock_result):
        run_dir = runner.execute()

    assert run_dir.exists()
    assert (run_dir / "results.json").exists()
    assert (run_dir / "meta.yaml").exists()


def test_runner_captures_results(tmp_path, eval_config):
    runner = Runner(config=eval_config, output_dir=tmp_path / "runs")

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
