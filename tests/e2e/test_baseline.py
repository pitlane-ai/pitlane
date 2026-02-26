"""E2E baseline tests: basic codegen with all 4 adapters, no MCP, no skills.

Run with: uv run pytest -m e2e -k baseline -v --tb=long
"""

import json
import subprocess
from pathlib import Path

import pytest
import yaml
from junitparser import JUnitXml

from tests.e2e.conftest import run_pipeline, workspace

ASSISTANTS = ("claude-baseline", "bob-baseline", "opencode-baseline", "vibe-baseline")


@pytest.fixture(scope="module")
def baseline_run(tmp_path_factory):
    fixtures_src = Path(__file__).parent / "fixtures"
    return run_pipeline(
        tmp_path_factory,
        "eval-baseline.yaml",
        replacements={
            "__VALIDATE_SCRIPT_PATH__": str(fixtures_src / "validate_hello.py"),
            "__WORKDIR_PATH__": str(fixtures_src / "fixtures" / "empty"),
        },
    )


@pytest.mark.e2e
def test_cli_exits_zero(baseline_run):
    result, _ = baseline_run
    assert result.returncode == 0, (
        f"pitlane run exited with code {result.returncode}\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )


@pytest.mark.e2e
def test_cli_output_shows_run_complete(baseline_run):
    result, _ = baseline_run
    assert "Run complete:" in result.stdout, f"stdout: {result.stdout}"


@pytest.mark.e2e
def test_junit_has_all_properties(baseline_run):
    _, run_dir = baseline_run
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
def test_assertions_pass(baseline_run):
    _, run_dir = baseline_run
    xml = JUnitXml.fromfile(str(run_dir / "junit.xml"))
    for suite in xml:
        assert suite.failures == 0, (
            f"Suite '{suite.name}' had {suite.failures} failure(s). "
            "The LLM may not have completed all required tasks."
        )


@pytest.mark.e2e
def test_meta_yaml_complete(baseline_run):
    _, run_dir = baseline_run
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
def test_report_has_all_assistants(baseline_run):
    _, run_dir = baseline_run
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
def test_debug_log_exists(baseline_run):
    _, run_dir = baseline_run
    assert (run_dir / "debug.log").exists()


@pytest.mark.e2e
@pytest.mark.parametrize("assistant", ASSISTANTS)
def test_workspace_has_hello_py(baseline_run, assistant):
    _, run_dir = baseline_run
    assert (workspace(run_dir, assistant) / "hello.py").exists()


@pytest.mark.e2e
@pytest.mark.parametrize("assistant", ASSISTANTS)
def test_workspace_has_fail_py(baseline_run, assistant):
    _, run_dir = baseline_run
    assert (workspace(run_dir, assistant) / "fail.py").exists()


@pytest.mark.e2e
@pytest.mark.parametrize("assistant", ASSISTANTS)
def test_conversation_json_exists(baseline_run, assistant):
    _, run_dir = baseline_run
    conv_file = run_dir / assistant / "hello-world" / "iter-0" / "conversation.json"
    assert conv_file.exists(), f"conversation.json not found for '{assistant}'"
    json.loads(conv_file.read_text())


@pytest.mark.e2e
@pytest.mark.parametrize("assistant", ASSISTANTS)
def test_conversation_has_content(baseline_run, assistant):
    """Conversation must have at least 2 entries (tool calls + text)."""
    _, run_dir = baseline_run
    conv_file = run_dir / assistant / "hello-world" / "iter-0" / "conversation.json"
    conversation = json.loads(conv_file.read_text())
    assert len(conversation) >= 2, (
        f"Conversation for '{assistant}' has only {len(conversation)} entries, expected ≥2"
    )


@pytest.mark.e2e
@pytest.mark.parametrize("assistant", ASSISTANTS)
def test_conversation_has_assistant_text(baseline_run, assistant):
    """At least one entry must have non-empty text content from the assistant."""
    _, run_dir = baseline_run
    conv_file = run_dir / assistant / "hello-world" / "iter-0" / "conversation.json"
    conversation = json.loads(conv_file.read_text())
    has_text = any(entry.get("content") for entry in conversation)
    assert has_text, f"No assistant text content in conversation for '{assistant}'"


@pytest.mark.e2e
def test_cli_run_invalid_config():
    result = subprocess.run(
        ["pitlane", "run", "nonexistent.yaml"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert "not found" in result.stderr


@pytest.mark.e2e
def test_cli_report_regenerates(baseline_run):
    _, run_dir = baseline_run
    result = subprocess.run(
        ["pitlane", "report", str(run_dir)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "Report generated:" in result.stdout
