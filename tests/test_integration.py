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
  opencode-baseline:
    adapter: opencode
    args:
      model: gpt-4

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

    with (
        patch("agent_eval.adapters.claude_code.ClaudeCodeAdapter.run", mock_run),
        patch("agent_eval.adapters.opencode.OpenCodeAdapter.run", mock_run),
    ):
        runner = Runner(config=config, output_dir=tmp_path / "runs", verbose=False)
        run_dir = runner.execute()

        # Verify run directory structure
        assert (run_dir / "results.json").exists()
        assert (run_dir / "meta.yaml").exists()

        # Verify results content
        results = json.loads((run_dir / "results.json").read_text())
        assert "claude-baseline" in results
        assert "opencode-baseline" in results

        for assistant in ["claude-baseline", "opencode-baseline"]:
            task_result = results[assistant]["create-script"]
            assert task_result["all_passed"] is True
            assert task_result["metrics"]["wall_clock_seconds"] == 5.0
            assert task_result["metrics"]["cost_usd"] == 0.02

        # Generate and verify report
        report_path = generate_report(run_dir)
        assert report_path.exists()
        html = report_path.read_text()
        assert "claude-baseline" in html
        assert "opencode-baseline" in html
        assert "create-script" in html
        assert "100.0% pass" in html


@pytest.mark.integration
def test_skill_installation_non_interactive(tmp_path):
    """Integration test: Verify skill installation completes without hanging on prompts."""
    from agent_eval.config import SkillRef
    from agent_eval.workspace import WorkspaceManager

    ws = tmp_path / "workspace"
    ws.mkdir()

    manager = WorkspaceManager(tmp_path)

    # This should complete without hanging (npx --yes prevents prompts)
    # Using a lightweight skill for faster test execution
    manager.install_skill(
        workspace=ws,
        skill=SkillRef(source="vercel-labs/skills", skill="find-skills"),
        agent_type="claude-code",
    )

    # Verify skill installation artifacts exist
    # The skills CLI creates .agents/skills/<skillname>/SKILL.md
    skill_files = list((ws / ".agents" / "skills").rglob("SKILL.md"))
    assert (
        len(skill_files) > 0
    ), "Expected SKILL.md file not found under .agents/skills/ after skill installation"


@pytest.mark.integration
def test_simple_codegen_eval_example(tmp_path):
    """Integration test: Run the simple-codegen-eval.yaml example with mocked adapters."""
    from pathlib import Path

    # Load the actual example config
    example_config = Path("examples/simple-codegen-eval.yaml")
    config = load_config(example_config)

    def mock_run(self, prompt, workdir, config, logger):
        """Mock adapter that creates the expected hello.py file."""
        (workdir / "hello.py").write_text('print("Hello, World!")')
        return AdapterResult(
            stdout='{"type":"result","result":"Created hello.py"}',
            stderr="",
            exit_code=0,
            duration_seconds=2.0,
            conversation=[{"role": "assistant", "content": "Created hello.py"}],
            token_usage={"input": 100, "output": 50},
            cost_usd=0.01,
        )

    # Mock all adapters in the example
    with (
        patch("agent_eval.adapters.claude_code.ClaudeCodeAdapter.run", mock_run),
        patch("agent_eval.adapters.mistral_vibe.MistralVibeAdapter.run", mock_run),
        patch("agent_eval.adapters.opencode.OpenCodeAdapter.run", mock_run),
    ):
        runner = Runner(config=config, output_dir=tmp_path / "runs", verbose=False)
        run_dir = runner.execute()

        # Verify run completed successfully
        assert (run_dir / "results.json").exists()
        assert (run_dir / "meta.yaml").exists()

        # Verify all assistants ran
        results = json.loads((run_dir / "results.json").read_text())
        assert "claude-baseline" in results
        assert "vibe-devstral-2" in results
        assert "vibe-devstral-small" in results
        assert "opencode-baseline" in results

        # Verify task completed for all assistants
        for assistant in [
            "claude-baseline",
            "vibe-devstral-2",
            "vibe-devstral-small",
            "opencode-baseline",
        ]:
            task_result = results[assistant]["hello-world-python"]
            assert task_result["all_passed"] is True
            assert task_result["metrics"]["cost_usd"] == 0.01

        # Verify HTML report can be generated
        report_path = generate_report(run_dir)
        assert report_path.exists()
        html = report_path.read_text()
        assert "hello-world-python" in html
        assert "100.0% pass" in html
