"""E2E pipeline tests: full CLI invocation with a real LLM.

Runs `pitlane run` with claude-code/haiku against a real YAML config that
includes an MCP server with a unique marker tool. All pipeline tests share
a single CLI invocation via the module-scoped `pipeline_run` fixture.

Run with: uv run pytest -m e2e -v --tb=long
"""

import json
import subprocess
from pathlib import Path

import pytest
import yaml
from junitparser import JUnitXml


@pytest.fixture(scope="module")
def pipeline_run(tmp_path_factory, require_claude_cli, require_pitlane_cli):
    """Run `pitlane run` once and share the result across all pipeline tests."""
    output_dir = tmp_path_factory.mktemp("e2e_runs")
    config_dir = tmp_path_factory.mktemp("e2e_config")

    fixtures_src = Path(__file__).parent / "fixtures"
    config_path = config_dir / "eval.yaml"
    mcp_server_path = fixtures_src / "mcp_test_server.py"
    workdir_path = fixtures_src / "fixtures" / "empty"

    yaml_content = (fixtures_src / "eval.yaml").read_text()
    yaml_content = yaml_content.replace("__MCP_SERVER_PATH__", str(mcp_server_path))
    yaml_content = yaml_content.replace("./fixtures/empty", str(workdir_path))
    config_path.write_text(yaml_content)

    result = subprocess.run(
        [
            "pitlane",
            "run",
            str(config_path),
            "--output-dir",
            str(output_dir),
            "--no-open",
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )

    run_dirs = sorted(output_dir.iterdir())
    assert len(run_dirs) == 1, (
        f"Expected 1 run dir, got: {[str(d) for d in output_dir.iterdir()]}"
    )
    run_dir = run_dirs[0]

    return result, run_dir


def _workspace(run_dir: Path) -> Path:
    return run_dir / "claude-haiku" / "hello-world" / "iter-0" / "workspace"


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
        assert float(props["cost_usd"]) > 0
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
def test_report_has_metric_groups(pipeline_run):
    _, run_dir = pipeline_run
    report = run_dir / "report.html"
    assert report.exists()
    html = report.read_text()
    assert "claude-haiku" in html
    assert "Cost &amp; Tokens" in html
    assert "cost_usd" in html
    assert "token_usage_input" in html
    assert "badge-pass" in html or "badge-fail" in html
    assert "hello-world" in html


@pytest.mark.e2e
def test_mcp_config_in_workspace(pipeline_run):
    _, run_dir = pipeline_run
    mcp_file = _workspace(run_dir) / ".mcp.json"
    assert mcp_file.exists()
    data = json.loads(mcp_file.read_text())
    assert "pitlane-test-mcp" in data["mcpServers"]


@pytest.mark.e2e
def test_mcp_marker_proves_tool_used(pipeline_run):
    _, run_dir = pipeline_run
    marker = _workspace(run_dir) / ".mcp_marker"
    assert marker.exists(), "MCP marker file not found — MCP tool was not invoked"
    assert "PITLANE_MCP_MARKER_a9f3e7b2" in marker.read_text()


@pytest.mark.e2e
def test_skill_present_in_workspace(pipeline_run):
    _, run_dir = pipeline_run
    skill_file = (
        _workspace(run_dir) / ".agents" / "skills" / "pitlane-test" / "SKILL.md"
    )
    assert skill_file.exists(), "Skill file not copied to workspace"


@pytest.mark.e2e
def test_workspace_has_hello_py(pipeline_run):
    _, run_dir = pipeline_run
    assert (_workspace(run_dir) / "hello.py").exists()


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
