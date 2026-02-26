"""E2E skill integration tests: claude, opencode, vibe with pitlane-test skill, no MCP.

Run with: uv run pytest -m e2e -k skill -v --tb=long
"""

from pathlib import Path

import pytest
from junitparser import JUnitXml

from tests.e2e.conftest import run_pipeline, workspace

ASSISTANTS = ("claude-skill", "opencode-skill", "vibe-skill")


@pytest.fixture(scope="module")
def skill_run(tmp_path_factory):
    fixtures_src = Path(__file__).parent / "fixtures"
    return run_pipeline(
        tmp_path_factory,
        "eval-skill.yaml",
        replacements={
            "__SKILL_SOURCE_PATH__": str(fixtures_src / "skills" / "pitlane-test"),
            "__VALIDATE_SCRIPT_PATH__": str(fixtures_src / "validate_hello.py"),
            "__WORKDIR_PATH__": str(fixtures_src / "fixtures" / "empty"),
        },
    )


@pytest.mark.e2e
def test_cli_exits_zero(skill_run):
    result, _ = skill_run
    assert result.returncode == 0, (
        f"pitlane run exited with code {result.returncode}\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )


@pytest.mark.e2e
def test_assertions_pass(skill_run):
    _, run_dir = skill_run
    xml = JUnitXml.fromfile(str(run_dir / "junit.xml"))
    for suite in xml:
        assert suite.failures == 0, (
            f"Suite '{suite.name}' had {suite.failures} failure(s). "
            "The LLM may not have completed all required tasks."
        )


@pytest.mark.e2e
@pytest.mark.parametrize("assistant", ASSISTANTS)
def test_skill_marker_in_generated_files(skill_run, assistant):
    """Skill instructions must be followed: generated files contain the skill marker."""
    _, run_dir = skill_run
    hello_py = workspace(run_dir, assistant) / "hello.py"
    assert hello_py.exists(), f"hello.py not found for '{assistant}'"
    content = hello_py.read_text()
    assert "Generated with pitlane-test skill" in content, (
        f"Skill marker not found in hello.py for '{assistant}' — "
        f"agent did not follow pitlane-test skill instructions"
    )
