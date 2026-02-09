"""Tests for config loading and validation."""

import textwrap
from pathlib import Path

import pytest
import yaml

from agent_eval.config import EvalConfig, SkillRef, load_config


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
        {"file_exists": "hello.py"}
    ]


def test_load_config_with_skills(tmp_yaml):
    path = tmp_yaml("""\
        assistants:
          skilled:
            adapter: codex
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
