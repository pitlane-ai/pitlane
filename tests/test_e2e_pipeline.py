"""E2E pipeline tests: full Runner.execute() with a real LLM.

Uses claude-code with haiku to keep costs low.
Run with: uv run pytest -m e2e -v --tb=long
"""

import pytest
from junitparser import JUnitXml

from pitlane.config import load_config
from pitlane.reporting.junit import generate_report
from pitlane.runner import Runner


@pytest.fixture
def e2e_eval_config(tmp_path):
    """Minimal eval config pointing at a real empty workdir."""
    empty = tmp_path / "fixtures" / "empty"
    empty.mkdir(parents=True)

    config_file = tmp_path / "eval.yaml"
    config_file.write_text(
        f"""\
assistants:
  claude-haiku:
    adapter: claude-code
    args:
      model: haiku
      max_turns: 3

tasks:
  - name: hello-world
    prompt: "Create a Python script called hello.py that prints 'Hello, World!'"
    workdir: {empty}
    timeout: 120
    assertions:
      - file_exists: "hello.py"
      - command_succeeds: "python3 hello.py"
"""
    )
    return config_file, tmp_path


@pytest.mark.e2e
@pytest.mark.usefixtures("require_claude_cli")
def test_runner_produces_artifacts(e2e_eval_config):
    config_file, tmp_path = e2e_eval_config
    config = load_config(config_file)
    runner = Runner(config=config, output_dir=tmp_path / "runs", verbose=False)
    run_dir = runner.execute()

    assert (run_dir / "junit.xml").exists()
    assert (run_dir / "meta.yaml").exists()

    xml = JUnitXml.fromfile(str(run_dir / "junit.xml"))
    for suite in xml:
        props = {p.name: p.value for p in suite.properties()}
        assert "cost_usd" in props
        assert "token_usage_input" in props
        assert "token_usage_output" in props
        assert float(props["cost_usd"]) > 0
        assert int(props["token_usage_input"]) > 0
        assert suite.time > 0


@pytest.mark.e2e
@pytest.mark.usefixtures("require_claude_cli")
def test_assertions_pass(e2e_eval_config):
    config_file, tmp_path = e2e_eval_config
    config = load_config(config_file)
    runner = Runner(config=config, output_dir=tmp_path / "runs", verbose=False)
    run_dir = runner.execute()

    xml = JUnitXml.fromfile(str(run_dir / "junit.xml"))
    for suite in xml:
        assert suite.failures == 0, (
            f"Suite '{suite.name}' had {suite.failures} failure(s). "
            "The LLM may not have created the expected file."
        )


@pytest.mark.e2e
@pytest.mark.usefixtures("require_claude_cli")
def test_report_generation(e2e_eval_config):
    config_file, tmp_path = e2e_eval_config
    config = load_config(config_file)
    runner = Runner(config=config, output_dir=tmp_path / "runs", verbose=False)
    run_dir = runner.execute()

    report_path = generate_report(run_dir)
    assert report_path.exists()
    html = report_path.read_text()
    assert "claude-haiku" in html
