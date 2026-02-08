"""Tests for config loading and validation."""

import textwrap
from pathlib import Path

import pytest
import yaml

from agent_eval.config import EvalConfig, load_config


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
              - type: contains
                value: hello
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
    assert task.assertions == [{"type": "contains", "value": "hello"}]


def test_load_config_with_skills(tmp_yaml):
    path = tmp_yaml("""\
        assistants:
          skilled:
            adapter: codex
            skills:
              - python
              - rust
        tasks:
          - name: t1
            prompt: do something
            workdir: /tmp
            assertions:
              - type: exit_code
                value: 0
    """)
    cfg = load_config(path)
    assert cfg.assistants["skilled"].skills == ["python", "rust"]


def test_load_config_missing_required_fields(tmp_yaml):
    # empty assistants
    path = tmp_yaml("""\
        assistants: {}
        tasks:
          - name: t
            prompt: p
            workdir: /tmp
            assertions:
              - type: x
                value: 1
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
              - type: x
                value: 1
          - name: custom
            prompt: p
            workdir: /tmp
            timeout: 600
            assertions:
              - type: x
                value: 1
    """)
    cfg = load_config(path)
    assert cfg.tasks[0].timeout == 300
    assert cfg.tasks[1].timeout == 600


def test_valid_adapter_types(tmp_yaml):
    path = tmp_yaml("""\
        assistants:
          bad:
            adapter: unknown-adapter
        tasks:
          - name: t
            prompt: p
            workdir: /tmp
            assertions:
              - type: x
                value: 1
    """)
    with pytest.raises(Exception):
        load_config(path)
