"""E2E tests for --repeat: verify all iterations run cleanly for every adapter.

Runs `pitlane run --repeat 3 --parallel 4` with all 4 adapters against the
shared eval fixture. All tests in this module share a single CLI invocation
via the module-scoped `pipeline_run_repeat` fixture.

Run with: uv run pytest -m e2e -v --tb=long
"""

import itertools
import json
from pathlib import Path

import pytest
import yaml
from junitparser import JUnitXml

from tests.e2e.conftest import run_with_tee

_ASSISTANTS = ("claude-haiku", "bob-default", "opencode-default", "vibe-default")
_REPEAT_COUNT = 3


@pytest.fixture(scope="module")
def pipeline_run_repeat(
    tmp_path_factory,
    require_claude_cli,
    require_bob_cli,
    require_opencode_cli,
    require_vibe_cli,
    require_pitlane_cli,
):
    """Run `pitlane run --repeat 3` for all adapters and share the result."""
    output_dir = tmp_path_factory.mktemp("e2e_repeat_runs")
    config_dir = tmp_path_factory.mktemp("e2e_repeat_config")

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
            "--repeat",
            str(_REPEAT_COUNT),
            "--parallel",
            "4",
            "--no-open",
        ],
        timeout=900,
    )

    run_dirs = sorted(output_dir.iterdir())
    assert len(run_dirs) == 1, (
        f"Expected 1 run dir, got: {[str(d) for d in output_dir.iterdir()]}"
    )
    run_dir = run_dirs[0]

    return result, run_dir


@pytest.mark.e2e
def test_repeat_cli_exits_zero(pipeline_run_repeat):
    result, _ = pipeline_run_repeat
    assert result.returncode == 0, (
        f"pitlane run --repeat {_REPEAT_COUNT} exited with code {result.returncode}\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )


@pytest.mark.e2e
def test_repeat_meta_yaml_records_repeat_count(pipeline_run_repeat):
    _, run_dir = pipeline_run_repeat
    meta = yaml.safe_load((run_dir / "meta.yaml").read_text())
    assert meta.get("repeat") == _REPEAT_COUNT


@pytest.mark.e2e
@pytest.mark.parametrize(
    "assistant,iteration",
    list(itertools.product(_ASSISTANTS, range(_REPEAT_COUNT))),
)
def test_repeat_workspace_exists(pipeline_run_repeat, assistant, iteration):
    _, run_dir = pipeline_run_repeat
    ws = run_dir / assistant / "hello-world" / f"iter-{iteration}" / "workspace"
    assert ws.exists(), f"Workspace missing for {assistant} iter-{iteration}"


@pytest.mark.e2e
@pytest.mark.parametrize(
    "assistant,iteration",
    list(itertools.product(_ASSISTANTS, range(_REPEAT_COUNT))),
)
def test_repeat_conversation_json_exists(pipeline_run_repeat, assistant, iteration):
    _, run_dir = pipeline_run_repeat
    conv_file = (
        run_dir / assistant / "hello-world" / f"iter-{iteration}" / "conversation.json"
    )
    assert conv_file.exists(), (
        f"conversation.json missing for {assistant} iter-{iteration}"
    )
    json.loads(conv_file.read_text())


@pytest.mark.e2e
def test_repeat_junit_has_all_assistants(pipeline_run_repeat):
    _, run_dir = pipeline_run_repeat
    xml = JUnitXml.fromfile(str(run_dir / "junit.xml"))
    suite_names = {suite.name for suite in xml}
    for assistant in _ASSISTANTS:
        assert any(assistant in name for name in suite_names), (
            f"Assistant '{assistant}' missing from JUnit output"
        )
