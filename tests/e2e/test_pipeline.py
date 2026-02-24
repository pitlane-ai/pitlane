"""E2E pipeline tests: full CLI invocation with all adapters.

Runs `pitlane run --parallel 4` with all 4 adapters against a shared YAML config
that includes an MCP server with a unique marker tool. All pipeline tests share
a single CLI invocation via the module-scoped `pipeline_run` fixture.

Run with: uv run pytest -m e2e -v --tb=long
"""

import json
import subprocess
from pathlib import Path

import pytest
import yaml
from junitparser import JUnitXml

from pitlane.adapters import get_adapter
from tests.e2e.conftest import run_with_tee

ASSISTANTS = ("claude-haiku", "bob-default", "opencode-default", "vibe-default")

_eval_cfg = yaml.safe_load(
    (Path(__file__).parent / "fixtures" / "eval.yaml").read_text()
)
SKILL_ASSISTANTS = tuple(
    name
    for name, cfg in _eval_cfg["assistants"].items()
    if "skills" in get_adapter(cfg["adapter"]).supported_features()
)


@pytest.fixture(scope="module")
def pipeline_run(
    tmp_path_factory,
    require_claude_cli,
    require_bob_cli,
    require_opencode_cli,
    require_vibe_cli,
    require_pitlane_cli,
):
    """Run `pitlane run` once for all adapters and share the result across all tests."""
    output_dir = tmp_path_factory.mktemp("e2e_runs")
    config_dir = tmp_path_factory.mktemp("e2e_config")

    fixtures_src = Path(__file__).parent / "fixtures"
    config_path = config_dir / "eval.yaml"
    mcp_server_path = fixtures_src / "mcp_test_server.py"
    validate_script_path = fixtures_src / "validate_hello.py"
    workdir_path = fixtures_src / "fixtures" / "empty"

    yaml_content = (fixtures_src / "eval.yaml").read_text()
    yaml_content = yaml_content.replace("__MCP_SERVER_PATH__", str(mcp_server_path))
    yaml_content = yaml_content.replace(
        "__VALIDATE_SCRIPT_PATH__", str(validate_script_path)
    )
    yaml_content = yaml_content.replace("./fixtures/empty", str(workdir_path))
    config_path.write_text(yaml_content)

    result = run_with_tee(
        [
            "pitlane",
            "run",
            str(config_path),
            "--output-dir",
            str(output_dir),
            "--parallel",
            "4",
            "--no-open",
        ],
        timeout=600,
    )

    run_dirs = sorted(output_dir.iterdir())
    assert len(run_dirs) == 1, (
        f"Expected 1 run dir, got: {[str(d) for d in output_dir.iterdir()]}"
    )
    run_dir = run_dirs[0]

    return result, run_dir


def _workspace(run_dir: Path, assistant: str, task: str = "hello-world") -> Path:
    return run_dir / assistant / task / "iter-0" / "workspace"


@pytest.mark.e2e
def test_cli_exits_zero(pipeline_run):
    result, _ = pipeline_run
    assert result.returncode == 0, (
        f"pitlane run exited with code {result.returncode}\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )


@pytest.mark.e2e
def test_cli_output_shows_run_complete(pipeline_run):
    result, _ = pipeline_run
    assert "Run complete:" in result.stdout, f"stdout: {result.stdout}"


@pytest.mark.e2e
def test_junit_has_all_properties(pipeline_run):
    _, run_dir = pipeline_run
    xml = JUnitXml.fromfile(str(run_dir / "junit.xml"))
    required_keys = (
        "cost_usd",
        "token_usage_input",
        "token_usage_output",
        "weighted_score",
        "assertion_pass_rate",
        "files_created",
        "files_modified",
        "tool_calls_count",
        "timed_out",
    )
    for suite in xml:
        props = {p.name: p.value for p in suite.properties()}
        for key in required_keys:
            assert key in props, f"Missing property '{key}' in suite '{suite.name}'"
        assert float(props["cost_usd"]) >= 0
        assert float(props["token_usage_input"]) > 0
        assert float(props["assertion_pass_rate"]) > 0
        assert suite.time > 0


@pytest.mark.e2e
def test_assertions_pass(pipeline_run):
    _, run_dir = pipeline_run
    xml = JUnitXml.fromfile(str(run_dir / "junit.xml"))
    for suite in xml:
        assert suite.failures == 0, (
            f"Suite '{suite.name}' had {suite.failures} failure(s). "
            "The LLM may not have completed all required tasks."
        )


@pytest.mark.e2e
def test_meta_yaml_complete(pipeline_run):
    _, run_dir = pipeline_run
    meta = yaml.safe_load((run_dir / "meta.yaml").read_text())
    for key in (
        "run_id",
        "timestamp",
        "assistants",
        "tasks",
        "cli_versions",
        "pitlane_version",
    ):
        assert key in meta, f"Missing key '{key}' in meta.yaml"


@pytest.mark.e2e
def test_report_has_all_assistants(pipeline_run):
    _, run_dir = pipeline_run
    report = run_dir / "report.html"
    assert report.exists()
    html = report.read_text()
    for assistant in ASSISTANTS:
        assert assistant in html, f"Assistant '{assistant}' not found in report.html"
    assert "Cost &amp; Tokens" in html
    assert "cost_usd" in html
    assert "token_usage_input" in html
    assert "badge-pass" in html or "badge-fail" in html
    assert "hello-world" in html


@pytest.mark.e2e
@pytest.mark.parametrize("assistant", ASSISTANTS)
def test_mcp_marker_proves_tool_used(pipeline_run, assistant):
    _, run_dir = pipeline_run
    marker = _workspace(run_dir, assistant) / ".mcp_marker"
    assert marker.exists(), (
        f"MCP marker file not found for '{assistant}' — MCP tool was not invoked"
    )
    assert "PITLANE_MCP_MARKER_a9f3e7b2" in marker.read_text()


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
@pytest.mark.parametrize("assistant", SKILL_ASSISTANTS)
def test_skill_present_in_workspace(pipeline_run, assistant):
    _, run_dir = pipeline_run
    skill_file = (
        _workspace(run_dir, assistant)
        / ".agents"
        / "skills"
        / "pitlane-test"
        / "SKILL.md"
    )
    assert skill_file.exists(), f"Skill file not copied to workspace for '{assistant}'"


@pytest.mark.e2e
@pytest.mark.parametrize("assistant", ASSISTANTS)
def test_mcp_tool_call_in_conversation(pipeline_run, assistant):
    _, run_dir = pipeline_run
    conv_file = run_dir / assistant / "hello-world" / "iter-0" / "conversation.json"
    assert conv_file.exists(), f"conversation.json not found for '{assistant}'"
    conversation = json.loads(conv_file.read_text())
    assert _has_tool_call(conversation, "write_marker"), (
        f"No 'write_marker' tool call found in conversation for '{assistant}'"
    )


@pytest.mark.e2e
@pytest.mark.parametrize("assistant", ASSISTANTS)
def test_workspace_has_hello_py(pipeline_run, assistant):
    _, run_dir = pipeline_run
    assert (_workspace(run_dir, assistant) / "hello.py").exists()


@pytest.mark.e2e
@pytest.mark.parametrize("assistant", ASSISTANTS)
def test_workspace_has_fail_py(pipeline_run, assistant):
    _, run_dir = pipeline_run
    assert (_workspace(run_dir, assistant) / "fail.py").exists()


@pytest.mark.e2e
@pytest.mark.parametrize("assistant", ASSISTANTS)
def test_conversation_json_exists(pipeline_run, assistant):
    _, run_dir = pipeline_run
    conv_file = run_dir / assistant / "hello-world" / "iter-0" / "conversation.json"
    assert conv_file.exists(), f"conversation.json not found for '{assistant}'"
    json.loads(conv_file.read_text())


@pytest.mark.e2e
def test_debug_log_exists(pipeline_run):
    _, run_dir = pipeline_run
    assert (run_dir / "debug.log").exists()


@pytest.mark.e2e
def test_cli_run_invalid_config(require_pitlane_cli):
    result = subprocess.run(
        ["pitlane", "run", "nonexistent.yaml"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert "not found" in result.stderr


@pytest.mark.e2e
def test_cli_report_regenerates(pipeline_run):
    _, run_dir = pipeline_run
    result = subprocess.run(
        ["pitlane", "report", str(run_dir)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "Report generated:" in result.stdout


@pytest.mark.e2e
@pytest.mark.parametrize("assistant", ASSISTANTS)
def test_conversation_has_content(pipeline_run, assistant):
    """Conversation must have at least 2 entries (tool calls + text)."""
    _, run_dir = pipeline_run
    conv_file = run_dir / assistant / "hello-world" / "iter-0" / "conversation.json"
    conversation = json.loads(conv_file.read_text())
    assert len(conversation) >= 2, (
        f"Conversation for '{assistant}' has only {len(conversation)} entries, expected ≥2"
    )


@pytest.mark.e2e
@pytest.mark.parametrize("assistant", ASSISTANTS)
def test_conversation_tool_calls_have_names(pipeline_run, assistant):
    """Every tool_use entry must have a non-empty tool name."""
    _, run_dir = pipeline_run
    conv_file = run_dir / assistant / "hello-world" / "iter-0" / "conversation.json"
    conversation = json.loads(conv_file.read_text())
    for i, entry in enumerate(conversation):
        if "tool_use" in entry:
            name = entry["tool_use"].get("name", "")
            assert name, f"Entry {i} for '{assistant}' has empty tool_use.name: {entry}"


@pytest.mark.e2e
@pytest.mark.parametrize("assistant", ASSISTANTS)
def test_conversation_has_assistant_text(pipeline_run, assistant):
    """At least one entry must have non-empty text content from the assistant."""
    _, run_dir = pipeline_run
    conv_file = run_dir / assistant / "hello-world" / "iter-0" / "conversation.json"
    conversation = json.loads(conv_file.read_text())
    has_text = any(entry.get("content") for entry in conversation)
    assert has_text, f"No assistant text content in conversation for '{assistant}'"


@pytest.mark.e2e
@pytest.mark.parametrize("assistant", ASSISTANTS)
def test_conversation_tool_count_matches_junit(pipeline_run, assistant):
    """tool_calls_count in JUnit must match number of tool_use entries in conversation."""
    _, run_dir = pipeline_run
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
def test_report_shows_tool_calls(pipeline_run):
    """Report HTML must render TOOL badges and tool names in transcripts."""
    _, run_dir = pipeline_run
    html = (run_dir / "report.html").read_text()
    assert "badge-role-tool" in html, "No TOOL badges found in report"
    assert "write_marker" in html, "Tool name 'write_marker' not found in report"
