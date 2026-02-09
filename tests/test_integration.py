import json
import pytest
from pathlib import Path
from unittest.mock import patch
from agent_eval.adapters.base import AdapterResult
from agent_eval.config import load_config
from agent_eval.runner import Runner
from agent_eval.reporting.html import generate_report


@pytest.fixture
def full_eval_setup(tmp_path):
    """Set up a complete eval scenario with fixtures."""
    fixture = tmp_path / "fixtures" / "test-repo"
    fixture.mkdir(parents=True)
    (fixture / "README.md").write_text("# Test Repo")

    config_file = tmp_path / "eval.yaml"
    config_file.write_text(f"""\
assistants:
  claude-baseline:
    adapter: claude-code
    args:
      model: sonnet
  codex-baseline:
    adapter: codex
    args:
      model: o3

tasks:
  - name: create-script
    prompt: "Create a Python hello world script"
    workdir: {fixture}
    timeout: 10
    assertions:
      - file_exists: "hello.py"
      - command_succeeds: "echo ok"
""")
    return config_file, tmp_path


def _make_mock_result(workdir: Path) -> AdapterResult:
    """Create a mock result that also creates the expected file."""
    (workdir / "hello.py").write_text('print("Hello, World!")')
    return AdapterResult(
        stdout='{"type":"result","result":"Done"}',
        stderr="",
        exit_code=0,
        duration_seconds=5.0,
        conversation=[{"role": "assistant", "content": "Created hello.py"}],
        token_usage={"input": 300, "output": 100},
        cost_usd=0.02,
    )


def test_full_pipeline(full_eval_setup):
    config_file, tmp_path = full_eval_setup
    config = load_config(config_file)

    def mock_run(self, prompt, workdir, config, logger):
        return _make_mock_result(workdir)

    with patch("agent_eval.adapters.claude_code.ClaudeCodeAdapter.run", mock_run), \
         patch("agent_eval.adapters.codex.CodexAdapter.run", mock_run):

        runner = Runner(config=config, output_dir=tmp_path / "runs", verbose=False)
        run_dir = runner.execute()

        # Verify run directory structure
        assert (run_dir / "results.json").exists()
        assert (run_dir / "meta.yaml").exists()

        # Verify results content
        results = json.loads((run_dir / "results.json").read_text())
        assert "claude-baseline" in results
        assert "codex-baseline" in results

        for assistant in ["claude-baseline", "codex-baseline"]:
            task_result = results[assistant]["create-script"]
            assert task_result["all_passed"] is True
            assert task_result["metrics"]["wall_clock_seconds"] == 5.0
            assert task_result["metrics"]["cost_usd"] == 0.02

        # Generate and verify report
        report_path = generate_report(run_dir)
        assert report_path.exists()
        html = report_path.read_text()
        assert "claude-baseline" in html
        assert "codex-baseline" in html
        assert "create-script" in html
        assert "100.0% pass" in html
