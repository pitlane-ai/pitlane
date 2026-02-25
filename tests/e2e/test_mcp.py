"""E2E MCP integration tests: all 4 adapters with MCP server, no skills.

Run with: uv run pytest -m e2e -k mcp -v --tb=long
"""

import json
from pathlib import Path

import pytest
from junitparser import JUnitXml

from tests.e2e.conftest import run_pipeline, workspace

ASSISTANTS = ("claude-mcp", "bob-mcp", "opencode-mcp", "vibe-mcp")


@pytest.fixture(scope="module")
def mcp_run(
    tmp_path_factory,
    require_claude_cli,
    require_bob_cli,
    require_opencode_cli,
    require_vibe_cli,
    require_pitlane_cli,
):
    fixtures_src = Path(__file__).parent / "fixtures"
    return run_pipeline(
        tmp_path_factory,
        "eval-mcp.yaml",
        replacements={
            "__MCP_SERVER_PATH__": str(fixtures_src / "mcp_test_server.py"),
            "__VALIDATE_SCRIPT_PATH__": str(fixtures_src / "validate_hello.py"),
            "__WORKDIR_PATH__": str(fixtures_src / "fixtures" / "empty"),
        },
    )


def _has_tool_call(conversation: list[dict], tool_name: str) -> bool:
    """Check if a tool call with the given name exists in the conversation.

    Handles both formats:
    - {"tool_use": {"name": ...}} (claude, opencode, vibe)
    - {"tool_name": ...} (bob)

    Uses substring match to handle adapter-specific prefixes:
    - claude: mcp__pitlane-test-mcp__write_marker
    - vibe: pitlane-test-mcp_write_marker
    - bob: write_marker (bare)
    """
    for entry in conversation:
        name = entry.get("tool_use", {}).get("name", "")
        if tool_name in name:
            return True
        if tool_name in entry.get("tool_name", ""):
            return True
    return False


@pytest.mark.e2e
def test_cli_exits_zero(mcp_run):
    result, _ = mcp_run
    assert result.returncode == 0, (
        f"pitlane run exited with code {result.returncode}\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )


@pytest.mark.e2e
def test_assertions_pass(mcp_run):
    _, run_dir = mcp_run
    xml = JUnitXml.fromfile(str(run_dir / "junit.xml"))
    for suite in xml:
        assert suite.failures == 0, (
            f"Suite '{suite.name}' had {suite.failures} failure(s). "
            "The LLM may not have completed all required tasks."
        )


@pytest.mark.e2e
@pytest.mark.parametrize("assistant", ASSISTANTS)
def test_mcp_marker_proves_tool_used(mcp_run, assistant):
    _, run_dir = mcp_run
    marker = workspace(run_dir, assistant) / ".mcp_marker"
    assert marker.exists(), (
        f"MCP marker file not found for '{assistant}' — MCP tool was not invoked"
    )
    assert "PITLANE_MCP_MARKER_a9f3e7b2" in marker.read_text()


@pytest.mark.e2e
@pytest.mark.parametrize("assistant", ASSISTANTS)
def test_mcp_tool_call_in_conversation(mcp_run, assistant):
    _, run_dir = mcp_run
    conv_file = run_dir / assistant / "hello-world" / "iter-0" / "conversation.json"
    assert conv_file.exists(), f"conversation.json not found for '{assistant}'"
    conversation = json.loads(conv_file.read_text())
    assert _has_tool_call(conversation, "write_marker"), (
        f"No 'write_marker' tool call found in conversation for '{assistant}'"
    )


@pytest.mark.e2e
@pytest.mark.parametrize("assistant", ASSISTANTS)
def test_conversation_tool_calls_have_names(mcp_run, assistant):
    """Every tool_use entry must have a non-empty tool name."""
    _, run_dir = mcp_run
    conv_file = run_dir / assistant / "hello-world" / "iter-0" / "conversation.json"
    conversation = json.loads(conv_file.read_text())
    for i, entry in enumerate(conversation):
        if "tool_use" in entry:
            name = entry["tool_use"].get("name", "")
            assert name, f"Entry {i} for '{assistant}' has empty tool_use.name: {entry}"


@pytest.mark.e2e
@pytest.mark.parametrize("assistant", ASSISTANTS)
def test_conversation_tool_count_matches_junit(mcp_run, assistant):
    """tool_calls_count in JUnit must match number of tool_use entries in conversation."""
    _, run_dir = mcp_run
    xml = JUnitXml.fromfile(str(run_dir / "junit.xml"))
    junit_count = None
    for suite in xml:
        if assistant in suite.name:
            for p in suite.properties():
                if p.name == "tool_calls_count":
                    junit_count = int(float(p.value))
            break
    assert junit_count is not None, f"No tool_calls_count in JUnit for '{assistant}'"

    conv_file = run_dir / assistant / "hello-world" / "iter-0" / "conversation.json"
    conversation = json.loads(conv_file.read_text())
    conv_count = sum(1 for e in conversation if "tool_use" in e)

    assert conv_count == junit_count, (
        f"Mismatch for '{assistant}': {conv_count} tool_use entries in conversation "
        f"vs {junit_count} tool_calls_count in JUnit"
    )


@pytest.mark.e2e
def test_report_shows_tool_calls(mcp_run):
    """Report HTML must render TOOL badges and tool names in transcripts."""
    _, run_dir = mcp_run
    html = (run_dir / "report.html").read_text()
    assert "badge-role-tool" in html, "No TOOL badges found in report"
    assert "write_marker" in html, "Tool name 'write_marker' not found in report"
