"""Tests for config loading and validation."""

import textwrap
from pathlib import Path

import pytest

from pitlane.config import SkillRef, load_config


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
def test_example_configs_load(path: Path, monkeypatch):
    """Test that example configs load successfully.

    Sets GITHUB_TOKEN for configs that require it.
    """
    assert path.exists()
    # Set GITHUB_TOKEN for terraform-module-eval.yaml which uses MCP servers
    monkeypatch.setenv("GITHUB_TOKEN", "test-token-for-validation")
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
    """${VAR} in env values is expanded by expandvars at install time, not parse time."""
    monkeypatch.setenv("MY_TEST_KEY", "secret")
    monkeypatch.delenv("MISSING_VAR", raising=False)
    monkeypatch.delenv("MISSING_VAR_NO_DEFAULT", raising=False)
    from expandvars import expandvars

    assert expandvars("${MY_TEST_KEY}", nounset=True) == "secret"
    assert expandvars("${MISSING_VAR:-fallback}", nounset=True) == "fallback"
    assert expandvars("plain", nounset=True) == "plain"
    assert (
        expandvars("prefix-${MY_TEST_KEY}-suffix", nounset=True)
        == "prefix-secret-suffix"
    )
    with pytest.raises(Exception):
        expandvars("${MISSING_VAR_NO_DEFAULT}", nounset=True)


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
    load_config(path)


def test_mcp_env_validation_missing_var_no_default(tmp_yaml, monkeypatch):
    """MCP config validation should fail if ${VAR} without default is not set."""
    monkeypatch.delenv("MISSING_TOKEN", raising=False)
    path = tmp_yaml("""\
        assistants:
          bob:
            adapter: bob
            mcps:
              - name: test-mcp
                type: stdio
                command: uvx
                args: ["test-mcp"]
                env:
                  API_KEY: "${MISSING_TOKEN}"
        tasks:
          - name: t
            prompt: p
            workdir: /tmp
            assertions:
              - command_succeeds: "true"
    """)
    with pytest.raises(
        ValueError, match="MCP server 'test-mcp' has missing environment variables"
    ):
        load_config(path)


def test_mcp_env_validation_missing_var_with_default(tmp_yaml, monkeypatch):
    """MCP config validation should pass if ${VAR:-default} is used."""
    monkeypatch.delenv("MISSING_TOKEN", raising=False)
    path = tmp_yaml("""\
        assistants:
          bob:
            adapter: bob
            mcps:
              - name: test-mcp
                type: stdio
                command: uvx
                args: ["test-mcp"]
                env:
                  API_KEY: "${MISSING_TOKEN:-fallback}"
        tasks:
          - name: t
            prompt: p
            workdir: /tmp
            assertions:
              - command_succeeds: "true"
    """)
    cfg = load_config(path)
    assert cfg.assistants["bob"].mcps[0].env["API_KEY"] == "${MISSING_TOKEN:-fallback}"


def test_mcp_env_validation_var_is_set(tmp_yaml, monkeypatch):
    """MCP config validation should pass if ${VAR} is set in environment."""
    monkeypatch.setenv("MY_TOKEN", "secret123")
    path = tmp_yaml("""\
        assistants:
          bob:
            adapter: bob
            mcps:
              - name: test-mcp
                type: stdio
                command: uvx
                args: ["test-mcp"]
                env:
                  API_KEY: "${MY_TOKEN}"
        tasks:
          - name: t
            prompt: p
            workdir: /tmp
            assertions:
              - command_succeeds: "true"
    """)
    cfg = load_config(path)
    assert cfg.assistants["bob"].mcps[0].env["API_KEY"] == "${MY_TOKEN}"


def test_mcp_env_validation_multiple_missing_vars(tmp_yaml, monkeypatch):
    """MCP config validation should report all missing variables at once."""
    monkeypatch.delenv("TOKEN1", raising=False)
    monkeypatch.delenv("TOKEN2", raising=False)
    path = tmp_yaml("""\
        assistants:
          bob:
            adapter: bob
            mcps:
              - name: test-mcp
                type: stdio
                command: uvx
                args: ["test-mcp"]
                env:
                  API_KEY: "${TOKEN1}"
                  SECRET: "${TOKEN2}"
        tasks:
          - name: t
            prompt: p
            workdir: /tmp
            assertions:
              - command_succeeds: "true"
    """)
    with pytest.raises(ValueError) as exc_info:
        load_config(path)
    error_msg = str(exc_info.value)
    assert "MCP server 'test-mcp' has missing environment variables" in error_msg
    assert "API_KEY=${TOKEN1}" in error_msg
    assert "SECRET=${TOKEN2}" in error_msg


def test_mcp_env_validation_plain_text(tmp_yaml):
    """MCP config validation should pass for plain text env values."""
    path = tmp_yaml("""\
        assistants:
          bob:
            adapter: bob
            mcps:
              - name: test-mcp
                type: stdio
                command: uvx
                args: ["test-mcp"]
                env:
                  PLAIN_VALUE: "just-a-string"
        tasks:
          - name: t
            prompt: p
            workdir: /tmp
            assertions:
              - command_succeeds: "true"
    """)
    cfg = load_config(path)
    assert cfg.assistants["bob"].mcps[0].env["PLAIN_VALUE"] == "just-a-string"


def test_mcp_env_validation_mixed_vars(tmp_yaml, monkeypatch):
    """MCP config validation should handle mix of set vars, defaults, and plain text."""
    monkeypatch.setenv("SET_VAR", "value1")
    monkeypatch.delenv("UNSET_VAR", raising=False)
    path = tmp_yaml("""\
        assistants:
          bob:
            adapter: bob
            mcps:
              - name: test-mcp
                type: stdio
                command: uvx
                args: ["test-mcp"]
                env:
                  KEY1: "${SET_VAR}"
                  KEY2: "${UNSET_VAR:-default}"
                  KEY3: "plain-text"
        tasks:
          - name: t
            prompt: p
            workdir: /tmp
            assertions:
              - command_succeeds: "true"
    """)
    cfg = load_config(path)
    mcp = cfg.assistants["bob"].mcps[0]
    assert mcp.env["KEY1"] == "${SET_VAR}"
    assert mcp.env["KEY2"] == "${UNSET_VAR:-default}"
    assert mcp.env["KEY3"] == "plain-text"


def test_mcp_env_validation_empty_env(tmp_yaml):
    """MCP config validation should pass when env dict is empty."""
    path = tmp_yaml("""\
        assistants:
          bob:
            adapter: bob
            mcps:
              - name: test-mcp
                type: stdio
                command: uvx
                args: ["test-mcp"]
        tasks:
          - name: t
            prompt: p
            workdir: /tmp
            assertions:
              - command_succeeds: "true"
    """)
    cfg = load_config(path)
    assert cfg.assistants["bob"].mcps[0].env == {}
