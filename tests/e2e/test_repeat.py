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

from tests.e2e.conftest import run_pipeline

_ASSISTANTS = ("claude-baseline", "bob-baseline", "opencode-baseline", "vibe-baseline")
_REPEAT_COUNT = 3


@pytest.fixture(scope="module")
def pipeline_run_repeat(tmp_path_factory):
    """Run `pitlane run --repeat 3` for all adapters and share the result."""
    fixtures_src = Path(__file__).parent / "fixtures"
    return run_pipeline(
        tmp_path_factory,
        "eval-baseline.yaml",
        replacements={
            "__VALIDATE_SCRIPT_PATH__": str(fixtures_src / "validate_hello.py"),
            "__WORKDIR_PATH__": str(fixtures_src / "fixtures" / "empty"),
        },
        extra_args=["--repeat", str(_REPEAT_COUNT)],
        timeout=900,
    )


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
