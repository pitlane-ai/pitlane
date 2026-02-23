"""Tests for config loading and validation."""

import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from pitlane.config import McpServerConfig, SkillRef, load_config


def _example_configs() -> list[Path]:
    repo_root = Path(__file__).resolve().parents[1]
    examples_dir = repo_root / "examples"
    return sorted(p for p in examples_dir.glob("*.yaml") if p.is_file())


@pytest.fixture()
def tmp_yaml(tmp_path):
    """Helper that writes YAML content to a temp file and returns its path."""

    def _write(content: str) -> Path:
        p = tmp_path / "eval.yaml"
        p.write_text(textwrap.dedent(content))
        return p

    return _write


def test_load_minimal_config(tmp_yaml):
    path = tmp_yaml("""\
        assistants:
          my-assistant:
            adapter: claude-code
        tasks:
          - name: hello
            prompt: Say hello
            workdir: /tmp
            assertions:
              - file_exists: "hello.py"
    """)
    cfg = load_config(path)
    assert "my-assistant" in cfg.assistants
    assistant = cfg.assistants["my-assistant"]
    assert assistant.adapter == "claude-code"
    assert assistant.args == {}
    assert assistant.skills == []
    assert len(cfg.tasks) == 1
    task = cfg.tasks[0]
    assert task.name == "hello"
    assert task.prompt == "Say hello"
    assert task.workdir == "/tmp"
    assert task.timeout == 300
    assert [a.model_dump() for a in task.assertions] == [
        {"file_exists": "hello.py", "weight": 1.0}
    ]


def test_load_config_with_skills(tmp_yaml):
    path = tmp_yaml("""\
        assistants:
          skilled:
            adapter: claude-code
            skills:
              - python
              - source: terraform-ibm-modules/terraform-ibm-modules-skills
                skill: terraform-ibm-modules-solution-builder
        tasks:
          - name: t1
            prompt: do something
            workdir: /tmp
            assertions:
              - command_succeeds: "true"
    """)
    cfg = load_config(path)
    skills = cfg.assistants["skilled"].skills
    assert skills == [
        SkillRef(source="python", skill=None),
        SkillRef(
            source="terraform-ibm-modules/terraform-ibm-modules-skills",
            skill="terraform-ibm-modules-solution-builder",
        ),
    ]


def test_load_config_missing_required_fields(tmp_yaml):
    # empty assistants
    path = tmp_yaml("""\
        assistants: {}
        tasks:
          - name: t
            prompt: p
            workdir: /tmp
            assertions:
              - file_exists: "x"
    """)
    with pytest.raises(Exception):
        load_config(path)

    # empty tasks
    path2 = tmp_yaml("""\
        assistants:
          a:
            adapter: claude-code
        tasks: []
    """)
    with pytest.raises(Exception):
        load_config(path2)


def test_task_default_timeout(tmp_yaml):
    path = tmp_yaml("""\
        assistants:
          a:
            adapter: claude-code
        tasks:
          - name: default
            prompt: p
            workdir: /tmp
            assertions:
              - file_exists: "x"
          - name: custom
            prompt: p
            workdir: /tmp
            timeout: 600
            assertions:
              - file_exists: "y"
    """)
    cfg = load_config(path)
    assert cfg.tasks[0].timeout == 300
    assert cfg.tasks[1].timeout == 600


@pytest.mark.parametrize("path", _example_configs())
def test_example_configs_load(path: Path):
    assert path.exists()
    load_config(path)


def test_assertion_validation_accepts_known(tmp_yaml):
    path = tmp_yaml("""
        assistants:
          a:
            adapter: claude-code
        tasks:
          - name: t
            prompt: p
            workdir: /tmp
            assertions:
              - file_exists: "x.py"
              - file_contains: { path: "x.py", pattern: "def" }
              - command_succeeds: "echo ok"
              - command_fails: "false"
              - bleu: { actual: "a.txt", expected: "b.txt", min_score: 0.1 }
              - rouge: { actual: "a.txt", expected: "b.txt", metric: "rougeL", min_score: 0.1 }
              - bertscore: { actual: "a.txt", expected: "b.txt", min_score: 0.1 }
              - cosine_similarity: { actual: "a.txt", expected: "b.txt", min_score: 0.1 }
    """)
    load_config(path)


def test_assertion_weight_accepted(tmp_yaml):
    path = tmp_yaml("""
        assistants:
          a:
            adapter: claude-code
        tasks:
          - name: t
            prompt: p
            workdir: /tmp
            assertions:
              - file_exists: "x.py"
                weight: 3.0
              - command_succeeds: "echo ok"
                weight: 0.5
              - rouge: { actual: "a.txt", expected: "b.txt", min_score: 0.1 }
                weight: 2.0
    """)
    cfg = load_config(path)
    assertions = cfg.tasks[0].assertions
    assert assertions[0].weight == 3.0
    assert assertions[1].weight == 0.5
    assert assertions[2].weight == 2.0


def test_assertion_weight_defaults_to_one(tmp_yaml):
    path = tmp_yaml("""
        assistants:
          a:
            adapter: claude-code
        tasks:
          - name: t
            prompt: p
            workdir: /tmp
            assertions:
              - file_exists: "x.py"
    """)
    cfg = load_config(path)
    assert cfg.tasks[0].assertions[0].weight == 1.0


def test_assertion_validation_rejects_unknown(tmp_yaml):
    path = tmp_yaml("""
        assistants:
          a:
            adapter: claude-code
        tasks:
          - name: t
            prompt: p
            workdir: /tmp
            assertions:
              - unknown_type: { x: 1 }
    """)
    with pytest.raises(Exception):
        load_config(path)


def test_load_config_with_mcps(tmp_yaml):
    path = tmp_yaml("""\
        assistants:
          mcp-assistant:
            adapter: claude-code
            mcps:
              - name: my-server
                type: stdio
                command: npx
                args: ["-y", "@my-org/my-mcp-server"]
                env:
                  API_KEY: "hardcoded"
        tasks:
          - name: t1
            prompt: do something
            workdir: /tmp
            assertions:
              - command_succeeds: "true"
    """)
    cfg = load_config(path)
    mcps = cfg.assistants["mcp-assistant"].mcps
    assert len(mcps) == 1
    mcp = mcps[0]
    assert mcp.name == "my-server"
    assert mcp.type == "stdio"
    assert mcp.command == "npx"
    assert mcp.args == ["-y", "@my-org/my-mcp-server"]
    assert mcp.env == {"API_KEY": "hardcoded"}


def test_load_config_mcps_defaults(tmp_yaml):
    path = tmp_yaml("""\
        assistants:
          a:
            adapter: claude-code
            mcps:
              - name: minimal
        tasks:
          - name: t
            prompt: p
            workdir: /tmp
            assertions:
              - command_succeeds: "true"
    """)
    cfg = load_config(path)
    mcp = cfg.assistants["a"].mcps[0]
    assert mcp.name == "minimal"
    assert mcp.type == "stdio"
    assert mcp.command is None
    assert mcp.args == []
    assert mcp.url is None
    assert mcp.env == {}


def test_load_config_mcps_sse_type(tmp_yaml):
    path = tmp_yaml("""\
        assistants:
          a:
            adapter: claude-code
            mcps:
              - name: remote
                type: sse
                url: "http://localhost:8080/sse"
        tasks:
          - name: t
            prompt: p
            workdir: /tmp
            assertions:
              - command_succeeds: "true"
    """)
    cfg = load_config(path)
    mcp = cfg.assistants["a"].mcps[0]
    assert mcp.type == "sse"
    assert mcp.url == "http://localhost:8080/sse"


def test_load_config_mcps_rejects_extra_fields(tmp_yaml):
    path = tmp_yaml("""\
        assistants:
          a:
            adapter: claude-code
            mcps:
              - name: bad
                unknown_field: oops
        tasks:
          - name: t
            prompt: p
            workdir: /tmp
            assertions:
              - command_succeeds: "true"
    """)
    with pytest.raises(Exception):
        load_config(path)


def test_mcp_server_config_env_expansion(monkeypatch):
    """${VAR} in env values is expanded by workspace_mgr at install time, not parse time."""
    monkeypatch.setenv("MY_TEST_KEY", "secret")
    from pitlane.workspace import _expand_env

    assert _expand_env("${MY_TEST_KEY}") == "secret"
    assert _expand_env("${MISSING_VAR:-fallback}") == "fallback"
    assert _expand_env("plain") == "plain"
    assert _expand_env("prefix-${MY_TEST_KEY}-suffix") == "prefix-secret-suffix"
    with pytest.raises(ValueError, match="MISSING_VAR_NO_DEFAULT"):
        _expand_env("${MISSING_VAR_NO_DEFAULT}")


def test_validate_mcp_env_fails_fast_on_missing_vars(monkeypatch):
    """validate_mcp_env raises listing all missing vars before any work starts."""
    monkeypatch.setenv("SET_VAR", "ok")
    monkeypatch.delenv("MISSING_A", raising=False)
    monkeypatch.delenv("MISSING_B", raising=False)
    from pitlane.workspace import validate_mcp_env
    from pitlane.config import AssistantConfig

    assistants = {
        "a1": AssistantConfig(
            adapter="claude-code",
            mcps=[McpServerConfig(name="m1", env={"K": "${SET_VAR}"})],
        ),
        "a2": AssistantConfig(
            adapter="claude-code",
            mcps=[
                McpServerConfig(
                    name="m2", env={"X": "${MISSING_A}", "Y": "${MISSING_B:-ok}"}
                )
            ],
        ),
    }
    # SET_VAR is fine, MISSING_B has a default — only MISSING_A should fail
    with pytest.raises(ValueError, match="MISSING_A") as exc_info:
        validate_mcp_env(assistants)
    assert "MISSING_B" not in str(exc_info.value)
    assert "a2" in str(exc_info.value)
    assert "m2" in str(exc_info.value)


def test_validate_mcp_env_passes_when_all_set(monkeypatch):
    """validate_mcp_env does not raise when all vars are present."""
    monkeypatch.setenv("TOKEN", "x")
    from pitlane.workspace import validate_mcp_env
    from pitlane.config import AssistantConfig

    assistants = {
        "a1": AssistantConfig(
            adapter="claude-code",
            mcps=[McpServerConfig(name="m1", env={"T": "${TOKEN}"})],
        ),
    }
    validate_mcp_env(assistants)  # should not raise


def test_load_config_no_mcps_defaults_to_empty(tmp_yaml):
    path = tmp_yaml("""\
        assistants:
          a:
            adapter: claude-code
        tasks:
          - name: t
            prompt: p
            workdir: /tmp
            assertions:
              - command_succeeds: "true"
    """)
    cfg = load_config(path)
    assert cfg.assistants["a"].mcps == []


def test_assistant_name_with_comma_raises(tmp_yaml):
    path = tmp_yaml("""\
        assistants:
          foo,bar:
            adapter: claude-code
        tasks:
          - name: t
            prompt: p
            workdir: /tmp
            assertions:
              - file_exists: "x"
    """)
    with pytest.raises(ValidationError, match="must not contain a comma"):
        load_config(path)
