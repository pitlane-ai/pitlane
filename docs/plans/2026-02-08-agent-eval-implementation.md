# agent-eval Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python CLI tool that evaluates AI coding assistants (Claude Code, Codex, Mistral Vibe) by running them against the same tasks and comparing results via a static HTML report.

**Architecture:** Subprocess-based adapter pattern. YAML config defines assistants + tasks. Runner orchestrates workspace isolation, skill installation, adapter invocation, assertion evaluation, and HTML report generation. Each adapter drives one CLI tool and normalizes output into a common format.

**Tech Stack:** Python 3.11+, uv, typer, pydantic, pyyaml, jinja2. Optional: evaluate, sentence-transformers, bert-score.

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/agent_eval/__init__.py`
- Create: `src/agent_eval/cli.py`
- Create: `tests/__init__.py`

**Step 1: Initialize uv project**

Run:
```bash
cd /Users/vincent/git/agent-eval/.worktrees/design
uv init --lib --name agent-eval --package
```

If uv init creates files in the wrong structure, move them. We want `src/agent_eval/` layout.

**Step 2: Edit pyproject.toml**

```toml
[project]
name = "agent-eval"
version = "0.1.0"
description = "Lightweight harness to evaluate AI coding assistants"
requires-python = ">=3.11"
dependencies = [
    "typer>=0.15",
    "pyyaml>=6.0",
    "jinja2>=3.1",
    "pydantic>=2.0",
]

[project.optional-dependencies]
similarity = ["evaluate", "sentence-transformers", "bert-score"]

[project.scripts]
agent-eval = "agent_eval.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/agent_eval"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

**Step 3: Create minimal CLI entrypoint**

`src/agent_eval/cli.py`:
```python
import typer

app = typer.Typer(name="agent-eval", help="Evaluate AI coding assistants")


@app.command()
def run(config: str = typer.Argument(help="Path to eval YAML config")):
    """Run evaluation tasks against configured assistants."""
    typer.echo(f"Running eval from {config}")


@app.command()
def report(run_dir: str = typer.Argument(help="Path to run output directory")):
    """Regenerate HTML report from a previous run."""
    typer.echo(f"Generating report from {run_dir}")


@app.command()
def init():
    """Initialize a new eval project with example config."""
    typer.echo("Initialized eval project")
```

`src/agent_eval/__init__.py`:
```python
"""agent-eval: Lightweight harness to evaluate AI coding assistants."""
```

`tests/__init__.py`: empty file.

**Step 4: Install dev dependencies and verify**

Run:
```bash
uv add --dev pytest ruff
uv sync
uv run agent-eval --help
```

Expected: help output showing `run`, `report`, `init` commands.

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: project scaffolding with uv, typer CLI skeleton"
```

---

### Task 2: Config Models (Pydantic)

**Files:**
- Create: `src/agent_eval/config.py`
- Create: `tests/test_config.py`

**Step 1: Write the failing tests**

`tests/test_config.py`:
```python
import pytest
from pathlib import Path
from agent_eval.config import load_config, EvalConfig, AssistantConfig, TaskConfig


def test_load_minimal_config(tmp_path):
    config_file = tmp_path / "eval.yaml"
    config_file.write_text("""
assistants:
  claude-baseline:
    adapter: claude-code
    args:
      model: sonnet

tasks:
  - name: hello-world
    prompt: "Create a hello world script"
    workdir: ./fixtures/empty
    assertions:
      - file_exists: "hello.py"
""")
    config = load_config(config_file)
    assert isinstance(config, EvalConfig)
    assert "claude-baseline" in config.assistants
    assert config.assistants["claude-baseline"].adapter == "claude-code"
    assert config.assistants["claude-baseline"].args["model"] == "sonnet"
    assert len(config.tasks) == 1
    assert config.tasks[0].name == "hello-world"
    assert config.tasks[0].timeout == 300  # default


def test_load_config_with_skills(tmp_path):
    config_file = tmp_path / "eval.yaml"
    config_file.write_text("""
assistants:
  claude-with-skills:
    adapter: claude-code
    args:
      model: sonnet
    skills:
      - org/repo
      - ./local-skill

tasks:
  - name: test-task
    prompt: "Do something"
    workdir: ./fixtures/empty
    assertions:
      - command_succeeds: "echo ok"
""")
    config = load_config(config_file)
    assert config.assistants["claude-with-skills"].skills == ["org/repo", "./local-skill"]


def test_load_config_missing_required_fields(tmp_path):
    config_file = tmp_path / "eval.yaml"
    config_file.write_text("""
assistants: {}
tasks: []
""")
    with pytest.raises(Exception):
        load_config(config_file)


def test_task_default_timeout(tmp_path):
    config_file = tmp_path / "eval.yaml"
    config_file.write_text("""
assistants:
  test:
    adapter: claude-code
    args:
      model: sonnet
tasks:
  - name: t1
    prompt: "test"
    workdir: ./fixtures
    timeout: 600
    assertions:
      - file_exists: "x"
""")
    config = load_config(config_file)
    assert config.tasks[0].timeout == 600


def test_valid_adapter_types(tmp_path):
    config_file = tmp_path / "eval.yaml"
    config_file.write_text("""
assistants:
  bad:
    adapter: unknown-assistant
    args: {}
tasks:
  - name: t1
    prompt: "test"
    workdir: ./fixtures
    assertions:
      - file_exists: "x"
""")
    with pytest.raises(Exception):
        load_config(config_file)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL (module not found)

**Step 3: Implement config models**

`src/agent_eval/config.py`:
```python
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, field_validator, model_validator

VALID_ADAPTERS = {"claude-code", "codex", "mistral-vibe"}


class AssistantConfig(BaseModel):
    adapter: str
    args: dict[str, Any] = {}
    skills: list[str] = []

    @field_validator("adapter")
    @classmethod
    def validate_adapter(cls, v: str) -> str:
        if v not in VALID_ADAPTERS:
            raise ValueError(f"Unknown adapter '{v}'. Valid: {VALID_ADAPTERS}")
        return v


class TaskConfig(BaseModel):
    name: str
    prompt: str
    workdir: str
    timeout: int = 300
    assertions: list[dict[str, Any]]

    @field_validator("assertions")
    @classmethod
    def validate_assertions_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("Tasks must have at least one assertion")
        return v


class EvalConfig(BaseModel):
    assistants: dict[str, AssistantConfig]
    tasks: list[TaskConfig]

    @model_validator(mode="after")
    def validate_not_empty(self) -> EvalConfig:
        if not self.assistants:
            raise ValueError("At least one assistant must be configured")
        if not self.tasks:
            raise ValueError("At least one task must be defined")
        return self


def load_config(path: Path) -> EvalConfig:
    """Load and validate an eval config from a YAML file."""
    with open(path) as f:
        raw = yaml.safe_load(f)
    return EvalConfig(**raw)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add src/agent_eval/config.py tests/test_config.py
git commit -m "feat: config loading and validation with pydantic models"
```

---

### Task 3: Base Adapter & AdapterResult

**Files:**
- Create: `src/agent_eval/adapters/__init__.py`
- Create: `src/agent_eval/adapters/base.py`
- Create: `tests/test_adapters.py`

**Step 1: Write the failing tests**

`tests/test_adapters.py`:
```python
import pytest
from agent_eval.adapters.base import AdapterResult, BaseAdapter, get_adapter
from pathlib import Path


def test_adapter_result_creation():
    result = AdapterResult(
        stdout="hello",
        stderr="",
        exit_code=0,
        duration_seconds=1.5,
        conversation=[],
        token_usage={"input": 100, "output": 50},
        cost_usd=0.01,
    )
    assert result.exit_code == 0
    assert result.duration_seconds == 1.5


def test_adapter_result_defaults():
    result = AdapterResult(
        stdout="",
        stderr="",
        exit_code=0,
        duration_seconds=0.0,
    )
    assert result.conversation == []
    assert result.token_usage is None
    assert result.cost_usd is None


def test_get_adapter_returns_correct_type():
    adapter = get_adapter("claude-code")
    assert isinstance(adapter, BaseAdapter)


def test_get_adapter_unknown_raises():
    with pytest.raises(ValueError, match="Unknown adapter"):
        get_adapter("nonexistent")
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_adapters.py -v`
Expected: FAIL

**Step 3: Implement base adapter**

`src/agent_eval/adapters/__init__.py`:
```python
"""Adapter system for driving AI assistant CLIs."""
```

`src/agent_eval/adapters/base.py`:
```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AdapterResult:
    stdout: str
    stderr: str
    exit_code: int
    duration_seconds: float
    conversation: list[dict[str, Any]] = field(default_factory=list)
    token_usage: dict[str, int] | None = None
    cost_usd: float | None = None


class BaseAdapter(ABC):
    """Base class for all assistant adapters."""

    @abstractmethod
    def run(self, prompt: str, workdir: Path, config: dict[str, Any]) -> AdapterResult:
        """Run the assistant with the given prompt in the given working directory."""
        ...

    @abstractmethod
    def cli_name(self) -> str:
        """Return the CLI command name (e.g. 'claude', 'codex', 'vibe')."""
        ...

    @abstractmethod
    def agent_type(self) -> str:
        """Return the agent type for npx skills install (e.g. 'claude-code', 'codex')."""
        ...

    @abstractmethod
    def skills_dir_name(self) -> str:
        """Return the skills directory name (e.g. '.claude', '.codex', '.vibe')."""
        ...


def get_adapter(adapter_name: str) -> BaseAdapter:
    """Factory function to get an adapter by name."""
    from agent_eval.adapters.claude_code import ClaudeCodeAdapter
    from agent_eval.adapters.codex import CodexAdapter
    from agent_eval.adapters.mistral_vibe import MistralVibeAdapter

    adapters: dict[str, type[BaseAdapter]] = {
        "claude-code": ClaudeCodeAdapter,
        "codex": CodexAdapter,
        "mistral-vibe": MistralVibeAdapter,
    }
    if adapter_name not in adapters:
        raise ValueError(f"Unknown adapter '{adapter_name}'. Valid: {set(adapters.keys())}")
    return adapters[adapter_name]()
```

**Step 4: Create stub adapters so get_adapter works**

`src/agent_eval/adapters/claude_code.py`:
```python
from __future__ import annotations
from pathlib import Path
from typing import Any
from agent_eval.adapters.base import AdapterResult, BaseAdapter


class ClaudeCodeAdapter(BaseAdapter):
    def run(self, prompt: str, workdir: Path, config: dict[str, Any]) -> AdapterResult:
        raise NotImplementedError

    def cli_name(self) -> str:
        return "claude"

    def agent_type(self) -> str:
        return "claude-code"

    def skills_dir_name(self) -> str:
        return ".claude"
```

`src/agent_eval/adapters/codex.py`:
```python
from __future__ import annotations
from pathlib import Path
from typing import Any
from agent_eval.adapters.base import AdapterResult, BaseAdapter


class CodexAdapter(BaseAdapter):
    def run(self, prompt: str, workdir: Path, config: dict[str, Any]) -> AdapterResult:
        raise NotImplementedError

    def cli_name(self) -> str:
        return "codex"

    def agent_type(self) -> str:
        return "codex"

    def skills_dir_name(self) -> str:
        return ".codex"
```

`src/agent_eval/adapters/mistral_vibe.py`:
```python
from __future__ import annotations
from pathlib import Path
from typing import Any
from agent_eval.adapters.base import AdapterResult, BaseAdapter


class MistralVibeAdapter(BaseAdapter):
    def run(self, prompt: str, workdir: Path, config: dict[str, Any]) -> AdapterResult:
        raise NotImplementedError

    def cli_name(self) -> str:
        return "vibe"

    def agent_type(self) -> str:
        return "mistral-vibe"

    def skills_dir_name(self) -> str:
        return ".vibe"
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_adapters.py -v`
Expected: all PASS

**Step 6: Commit**

```bash
git add src/agent_eval/adapters/ tests/test_adapters.py
git commit -m "feat: base adapter interface, adapter factory, stub adapters"
```

---

### Task 4: Deterministic Assertions

**Files:**
- Create: `src/agent_eval/assertions/__init__.py`
- Create: `src/agent_eval/assertions/base.py`
- Create: `src/agent_eval/assertions/deterministic.py`
- Create: `tests/test_assertions.py`

**Step 1: Write the failing tests**

`tests/test_assertions.py`:
```python
import pytest
from pathlib import Path
from agent_eval.assertions.base import AssertionResult
from agent_eval.assertions.deterministic import (
    check_file_exists,
    check_file_contains,
    check_command_succeeds,
    check_command_fails,
    evaluate_assertion,
)


def test_file_exists_pass(tmp_path):
    (tmp_path / "main.tf").write_text("resource {}")
    result = check_file_exists(tmp_path, "main.tf")
    assert result.passed
    assert "main.tf" in result.name


def test_file_exists_fail(tmp_path):
    result = check_file_exists(tmp_path, "missing.tf")
    assert not result.passed


def test_file_contains_pass(tmp_path):
    (tmp_path / "main.tf").write_text('resource "ibm_is_vpc" "main" {}')
    result = check_file_contains(tmp_path, "main.tf", "resource.*ibm_is_vpc")
    assert result.passed


def test_file_contains_fail(tmp_path):
    (tmp_path / "main.tf").write_text("nothing here")
    result = check_file_contains(tmp_path, "main.tf", "resource.*ibm_is_vpc")
    assert not result.passed


def test_file_contains_missing_file(tmp_path):
    result = check_file_contains(tmp_path, "missing.tf", "anything")
    assert not result.passed


def test_command_succeeds_pass(tmp_path):
    result = check_command_succeeds(tmp_path, "echo hello")
    assert result.passed


def test_command_succeeds_fail(tmp_path):
    result = check_command_succeeds(tmp_path, "false")
    assert not result.passed


def test_command_fails_pass(tmp_path):
    result = check_command_fails(tmp_path, "false")
    assert result.passed


def test_command_fails_fail(tmp_path):
    result = check_command_fails(tmp_path, "echo hello")
    assert not result.passed


def test_evaluate_assertion_file_exists(tmp_path):
    (tmp_path / "x.py").write_text("")
    result = evaluate_assertion(tmp_path, {"file_exists": "x.py"})
    assert result.passed


def test_evaluate_assertion_file_contains(tmp_path):
    (tmp_path / "x.py").write_text("def main(): pass")
    result = evaluate_assertion(tmp_path, {"file_contains": {"path": "x.py", "pattern": "def main"}})
    assert result.passed


def test_evaluate_assertion_command_succeeds(tmp_path):
    result = evaluate_assertion(tmp_path, {"command_succeeds": "true"})
    assert result.passed


def test_evaluate_assertion_unknown_type(tmp_path):
    with pytest.raises(ValueError, match="Unknown assertion type"):
        evaluate_assertion(tmp_path, {"unknown_check": "value"})
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_assertions.py -v`
Expected: FAIL

**Step 3: Implement assertions**

`src/agent_eval/assertions/__init__.py`:
```python
"""Assertion system for evaluating assistant outputs."""
```

`src/agent_eval/assertions/base.py`:
```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AssertionResult:
    name: str
    passed: bool
    message: str
```

`src/agent_eval/assertions/deterministic.py`:
```python
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from agent_eval.assertions.base import AssertionResult


def check_file_exists(workdir: Path, filename: str) -> AssertionResult:
    path = workdir / filename
    passed = path.exists()
    return AssertionResult(
        name=f"file_exists: {filename}",
        passed=passed,
        message="" if passed else f"File not found: {filename}",
    )


def check_file_contains(workdir: Path, filename: str, pattern: str) -> AssertionResult:
    path = workdir / filename
    name = f"file_contains: {filename} ~ {pattern}"
    if not path.exists():
        return AssertionResult(name=name, passed=False, message=f"File not found: {filename}")
    content = path.read_text()
    passed = bool(re.search(pattern, content))
    return AssertionResult(
        name=name,
        passed=passed,
        message="" if passed else f"Pattern '{pattern}' not found in {filename}",
    )


def check_command_succeeds(workdir: Path, command: str) -> AssertionResult:
    name = f"command_succeeds: {command}"
    try:
        result = subprocess.run(
            command, shell=True, cwd=workdir, capture_output=True, text=True, timeout=60,
        )
        passed = result.returncode == 0
        msg = "" if passed else f"Exit code {result.returncode}: {result.stderr[:200]}"
    except subprocess.TimeoutExpired:
        passed = False
        msg = "Command timed out after 60s"
    return AssertionResult(name=name, passed=passed, message=msg)


def check_command_fails(workdir: Path, command: str) -> AssertionResult:
    name = f"command_fails: {command}"
    try:
        result = subprocess.run(
            command, shell=True, cwd=workdir, capture_output=True, text=True, timeout=60,
        )
        passed = result.returncode != 0
        msg = "" if passed else "Command succeeded but was expected to fail"
    except subprocess.TimeoutExpired:
        passed = True
        msg = "Command timed out (treated as failure)"
    return AssertionResult(name=name, passed=passed, message=msg)


def evaluate_assertion(workdir: Path, assertion: dict[str, Any]) -> AssertionResult:
    """Evaluate a single assertion dict from the config."""
    assert len(assertion) == 1, f"Assertion must have exactly one key, got: {assertion}"
    atype, avalue = next(iter(assertion.items()))

    if atype == "file_exists":
        return check_file_exists(workdir, avalue)
    elif atype == "file_contains":
        return check_file_contains(workdir, avalue["path"], avalue["pattern"])
    elif atype == "command_succeeds":
        return check_command_succeeds(workdir, avalue)
    elif atype == "command_fails":
        return check_command_fails(workdir, avalue)
    else:
        # Similarity assertions handled elsewhere
        similarity_types = {"bleu", "rouge", "bertscore", "cosine_similarity"}
        if atype in similarity_types:
            # Defer to similarity module
            from agent_eval.assertions.similarity import evaluate_similarity_assertion
            return evaluate_similarity_assertion(workdir, atype, avalue)
        raise ValueError(f"Unknown assertion type: '{atype}'")
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_assertions.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add src/agent_eval/assertions/ tests/test_assertions.py
git commit -m "feat: deterministic assertions (file_exists, file_contains, command_succeeds/fails)"
```

---

### Task 5: Workspace Manager (isolation + skill installation)

**Files:**
- Create: `src/agent_eval/workspace.py`
- Create: `tests/test_workspace.py`

**Step 1: Write the failing tests**

`tests/test_workspace.py`:
```python
import pytest
from pathlib import Path
from agent_eval.workspace import WorkspaceManager


def test_create_isolated_workspace(tmp_path):
    # Create a fixture directory with some files
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "existing.tf").write_text("# existing")
    (fixture / "subdir").mkdir()
    (fixture / "subdir" / "nested.tf").write_text("# nested")

    mgr = WorkspaceManager(base_dir=tmp_path / "runs")
    workspace = mgr.create_workspace(
        source_dir=fixture,
        run_id="test-run",
        assistant_name="claude-baseline",
        task_name="test-task",
    )

    assert workspace.exists()
    assert (workspace / "existing.tf").read_text() == "# existing"
    assert (workspace / "subdir" / "nested.tf").read_text() == "# nested"


def test_install_local_skill(tmp_path):
    # Create a fixture workspace
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # Create a local skill
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# My Skill")
    (skill_dir / "references").mkdir()
    (skill_dir / "references" / "guide.md").write_text("# Guide")

    mgr = WorkspaceManager(base_dir=tmp_path)
    mgr.install_local_skill(
        workspace=workspace,
        skill_path=skill_dir,
        skills_dir_name=".claude",
    )

    installed = workspace / ".claude" / "skills" / "my-skill" / "SKILL.md"
    assert installed.exists()
    assert installed.read_text() == "# My Skill"
    assert (workspace / ".claude" / "skills" / "my-skill" / "references" / "guide.md").exists()


def test_install_local_skill_missing_skill_md(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    bad_skill = tmp_path / "bad-skill"
    bad_skill.mkdir()

    mgr = WorkspaceManager(base_dir=tmp_path)
    with pytest.raises(FileNotFoundError, match="SKILL.md"):
        mgr.install_local_skill(workspace, bad_skill, ".claude")


def test_workspace_cleanup(tmp_path):
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "f.txt").write_text("x")

    mgr = WorkspaceManager(base_dir=tmp_path / "runs")
    workspace = mgr.create_workspace(fixture, "run1", "asst1", "task1")
    assert workspace.exists()

    mgr.cleanup_workspace(workspace)
    assert not workspace.exists()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_workspace.py -v`
Expected: FAIL

**Step 3: Implement workspace manager**

`src/agent_eval/workspace.py`:
```python
from __future__ import annotations

import shutil
from pathlib import Path


class WorkspaceManager:
    """Manages isolated temporary workspaces for adapter runs."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir

    def create_workspace(
        self,
        source_dir: Path,
        run_id: str,
        assistant_name: str,
        task_name: str,
    ) -> Path:
        """Create an isolated workspace by copying source_dir."""
        workspace = self.base_dir / run_id / assistant_name / task_name / "workspace"
        if workspace.exists():
            shutil.rmtree(workspace)
        shutil.copytree(source_dir, workspace)
        return workspace

    def install_local_skill(
        self,
        workspace: Path,
        skill_path: Path,
        skills_dir_name: str,
    ) -> None:
        """Copy a local skill directory into the workspace's agent skill directory."""
        skill_md = skill_path / "SKILL.md"
        if not skill_md.exists():
            raise FileNotFoundError(
                f"SKILL.md not found in {skill_path}. "
                "Skills must contain a SKILL.md file."
            )
        skill_name = skill_path.name
        dest = workspace / skills_dir_name / "skills" / skill_name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(skill_path, dest)

    def install_github_skill(
        self,
        workspace: Path,
        skill_ref: str,
        agent_type: str,
    ) -> None:
        """Install a skill from GitHub using npx skills."""
        import subprocess

        result = subprocess.run(
            ["npx", "skills", "install", skill_ref, "--agent", agent_type, "--yes"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to install skill '{skill_ref}': {result.stderr}"
            )

    def cleanup_workspace(self, workspace: Path) -> None:
        """Remove a workspace directory."""
        if workspace.exists():
            shutil.rmtree(workspace)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_workspace.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add src/agent_eval/workspace.py tests/test_workspace.py
git commit -m "feat: workspace manager with isolation and skill installation"
```

---

### Task 6: Claude Code Adapter

**Files:**
- Modify: `src/agent_eval/adapters/claude_code.py`
- Create: `tests/test_adapter_claude.py`

**Step 1: Write the failing tests**

`tests/test_adapter_claude.py`:
```python
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from agent_eval.adapters.claude_code import ClaudeCodeAdapter


def test_build_command_minimal():
    adapter = ClaudeCodeAdapter()
    cmd = adapter._build_command("Write hello world", {"model": "sonnet"})
    assert cmd[0] == "claude"
    assert "-p" in cmd
    assert "--output-format" in cmd
    assert "stream-json" in cmd
    assert "--dangerously-skip-permissions" in cmd
    assert "--model" in cmd
    assert "sonnet" in cmd
    assert cmd[-1] == "Write hello world"


def test_build_command_with_mcp():
    adapter = ClaudeCodeAdapter()
    cmd = adapter._build_command("test", {"model": "sonnet", "mcp_config": "./mcp.json"})
    assert "--mcp-config" in cmd
    assert "./mcp.json" in cmd


def test_build_command_with_system_prompt():
    adapter = ClaudeCodeAdapter()
    cmd = adapter._build_command("test", {"model": "sonnet", "system_prompt": "Be helpful"})
    assert "--append-system-prompt" in cmd
    assert "Be helpful" in cmd


def test_parse_stream_json_result():
    adapter = ClaudeCodeAdapter()
    lines = [
        json.dumps({"type": "system", "subtype": "init", "session_id": "abc"}),
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello"}]}}),
        json.dumps({
            "type": "result", "subtype": "success",
            "duration_ms": 1500, "total_cost_usd": 0.02,
            "usage": {"input_tokens": 100, "output_tokens": 50,
                      "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
            "result": "Done",
        }),
    ]
    stdout = "\n".join(lines)
    conversation, token_usage, cost = adapter._parse_output(stdout)
    assert len(conversation) >= 1
    assert token_usage["input"] == 100
    assert token_usage["output"] == 50
    assert cost == 0.02
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_adapter_claude.py -v`
Expected: FAIL

**Step 3: Implement Claude Code adapter**

`src/agent_eval/adapters/claude_code.py`:
```python
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from agent_eval.adapters.base import AdapterResult, BaseAdapter


class ClaudeCodeAdapter(BaseAdapter):

    def cli_name(self) -> str:
        return "claude"

    def agent_type(self) -> str:
        return "claude-code"

    def skills_dir_name(self) -> str:
        return ".claude"

    def _build_command(self, prompt: str, config: dict[str, Any]) -> list[str]:
        cmd = [
            "claude", "-p",
            "--output-format", "stream-json",
            "--dangerously-skip-permissions",
        ]
        if model := config.get("model"):
            cmd.extend(["--model", model])
        if mcp_config := config.get("mcp_config"):
            cmd.extend(["--mcp-config", mcp_config])
        if system_prompt := config.get("system_prompt"):
            cmd.extend(["--append-system-prompt", system_prompt])
        if max_turns := config.get("max_turns"):
            cmd.extend(["--max-turns", str(max_turns)])
        if max_budget := config.get("max_budget_usd"):
            cmd.extend(["--max-budget-usd", str(max_budget)])
        cmd.append(prompt)
        return cmd

    def _parse_output(self, stdout: str) -> tuple[list[dict], dict | None, float | None]:
        """Parse stream-json NDJSON output into conversation, token_usage, cost."""
        conversation: list[dict] = []
        token_usage = None
        cost = None

        for line in stdout.strip().splitlines():
            if not line.strip():
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")
            if msg_type == "assistant":
                message = msg.get("message", {})
                for block in message.get("content", []):
                    if block.get("type") == "text":
                        conversation.append({
                            "role": "assistant",
                            "content": block["text"],
                        })
                    elif block.get("type") == "tool_use":
                        conversation.append({
                            "role": "assistant",
                            "content": "",
                            "tool_use": {
                                "name": block.get("name", ""),
                                "input": block.get("input", {}),
                            },
                        })
            elif msg_type == "result":
                usage = msg.get("usage", {})
                if usage:
                    token_usage = {
                        "input": usage.get("input_tokens", 0),
                        "output": usage.get("output_tokens", 0),
                    }
                cost = msg.get("total_cost_usd")

        return conversation, token_usage, cost

    def run(self, prompt: str, workdir: Path, config: dict[str, Any]) -> AdapterResult:
        cmd = self._build_command(prompt, config)
        start = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=config.get("timeout", 300),
            )
        except subprocess.TimeoutExpired as e:
            duration = time.monotonic() - start
            return AdapterResult(
                stdout=e.stdout or "",
                stderr=e.stderr or "",
                exit_code=-1,
                duration_seconds=duration,
                conversation=[],
                token_usage=None,
                cost_usd=None,
            )
        duration = time.monotonic() - start
        conversation, token_usage, cost = self._parse_output(proc.stdout)
        return AdapterResult(
            stdout=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
            duration_seconds=duration,
            conversation=conversation,
            token_usage=token_usage,
            cost_usd=cost,
        )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_adapter_claude.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add src/agent_eval/adapters/claude_code.py tests/test_adapter_claude.py
git commit -m "feat: Claude Code adapter with stream-json parsing"
```

---

### Task 7: Codex Adapter

**Files:**
- Modify: `src/agent_eval/adapters/codex.py`
- Create: `tests/test_adapter_codex.py`

**Step 1: Write the failing tests**

`tests/test_adapter_codex.py`:
```python
import json
import pytest
from pathlib import Path
from agent_eval.adapters.codex import CodexAdapter


def test_build_command_minimal():
    adapter = CodexAdapter()
    cmd = adapter._build_command("Write code", {"model": "o3"})
    assert cmd[0] == "codex"
    assert "exec" in cmd
    assert "--json" in cmd
    assert "-m" in cmd
    assert "o3" in cmd


def test_build_command_with_sandbox():
    adapter = CodexAdapter()
    cmd = adapter._build_command("test", {"model": "o3", "sandbox": "danger-full-access"})
    assert "-s" in cmd
    assert "danger-full-access" in cmd


def test_generate_config_toml_with_mcp(tmp_path):
    adapter = CodexAdapter()
    adapter._generate_config(tmp_path, {
        "mcp_servers": {
            "my-server": {"command": "npx", "args": ["-y", "my-mcp-server"]},
        }
    })
    config_file = tmp_path / ".codex" / "config.toml"
    assert config_file.exists()
    content = config_file.read_text()
    assert "mcp_servers" in content
    assert "my-server" in content


def test_parse_jsonl_output():
    adapter = CodexAdapter()
    lines = [
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 200, "output_tokens": 80, "cached_input_tokens": 10}}),
        json.dumps({"type": "agent_message", "content": "Done writing code"}),
    ]
    stdout = "\n".join(lines)
    conversation, token_usage, cost = adapter._parse_output(stdout)
    assert token_usage["input"] == 200
    assert token_usage["output"] == 80
    assert cost is None  # Codex doesn't report cost directly
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_adapter_codex.py -v`
Expected: FAIL

**Step 3: Implement Codex adapter**

`src/agent_eval/adapters/codex.py`:
```python
from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from agent_eval.adapters.base import AdapterResult, BaseAdapter


class CodexAdapter(BaseAdapter):

    def cli_name(self) -> str:
        return "codex"

    def agent_type(self) -> str:
        return "codex"

    def skills_dir_name(self) -> str:
        return ".codex"

    def _build_command(self, prompt: str, config: dict[str, Any]) -> list[str]:
        cmd = ["codex", "exec", "--json"]
        if model := config.get("model"):
            cmd.extend(["-m", model])
        sandbox = config.get("sandbox", "workspace-write")
        cmd.extend(["-s", sandbox])
        approval = config.get("approval", "never")
        cmd.extend(["-a", approval])
        cmd.append(prompt)
        return cmd

    def _generate_config(self, workdir: Path, config: dict[str, Any]) -> None:
        """Generate .codex/config.toml in the workspace if needed."""
        sections = []

        if mcp_servers := config.get("mcp_servers"):
            for name, server_config in mcp_servers.items():
                section = f'[mcp_servers."{name}"]\n'
                for key, value in server_config.items():
                    if isinstance(value, str):
                        section += f'{key} = "{value}"\n'
                    elif isinstance(value, list):
                        items = ", ".join(f'"{v}"' for v in value)
                        section += f"{key} = [{items}]\n"
                    else:
                        section += f"{key} = {value}\n"
                sections.append(section)

        if model_instructions := config.get("model_instructions_file"):
            sections.append(f'model_instructions_file = "{model_instructions}"\n')

        if sections:
            config_dir = workdir / ".codex"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "config.toml").write_text("\n".join(sections))

    def _parse_output(self, stdout: str) -> tuple[list[dict], dict | None, float | None]:
        """Parse JSONL output from codex exec --json."""
        conversation: list[dict] = []
        token_usage = None

        for line in stdout.strip().splitlines():
            if not line.strip():
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")

            if msg_type == "turn.completed":
                usage = msg.get("usage", {})
                if usage:
                    prev_input = token_usage["input"] if token_usage else 0
                    prev_output = token_usage["output"] if token_usage else 0
                    token_usage = {
                        "input": prev_input + usage.get("input_tokens", 0),
                        "output": prev_output + usage.get("output_tokens", 0),
                    }

            # Defensive: handle both documented and actual field names
            if msg_type in ("agent_message", "assistant_message"):
                conversation.append({
                    "role": "assistant",
                    "content": msg.get("content", ""),
                })

        return conversation, token_usage, None  # Codex doesn't report cost

    def run(self, prompt: str, workdir: Path, config: dict[str, Any]) -> AdapterResult:
        self._generate_config(workdir, config)
        cmd = self._build_command(prompt, config)

        codex_home = tempfile.mkdtemp(prefix="codex-home-")
        env = {"CODEX_HOME": codex_home, "PATH": ""}  # PATH populated below

        import os
        env["PATH"] = os.environ.get("PATH", "")

        start = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=config.get("timeout", 300),
                env={**os.environ, **env},
            )
        except subprocess.TimeoutExpired as e:
            duration = time.monotonic() - start
            return AdapterResult(
                stdout=e.stdout or "", stderr=e.stderr or "",
                exit_code=-1, duration_seconds=duration,
            )
        duration = time.monotonic() - start
        conversation, token_usage, cost = self._parse_output(proc.stdout)
        return AdapterResult(
            stdout=proc.stdout, stderr=proc.stderr,
            exit_code=proc.returncode, duration_seconds=duration,
            conversation=conversation, token_usage=token_usage, cost_usd=cost,
        )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_adapter_codex.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add src/agent_eval/adapters/codex.py tests/test_adapter_codex.py
git commit -m "feat: Codex adapter with config.toml generation and JSONL parsing"
```

---

### Task 8: Mistral Vibe Adapter

**Files:**
- Modify: `src/agent_eval/adapters/mistral_vibe.py`
- Create: `tests/test_adapter_vibe.py`

**Step 1: Write the failing tests**

`tests/test_adapter_vibe.py`:
```python
import json
import pytest
from pathlib import Path
from agent_eval.adapters.mistral_vibe import MistralVibeAdapter


def test_build_command_minimal():
    adapter = MistralVibeAdapter()
    cmd = adapter._build_command("Write code", {"model": "devstral-2"})
    assert cmd[0] == "vibe"
    assert "--prompt" in cmd
    assert "--output" in cmd
    assert "json" in cmd


def test_build_command_with_max_turns():
    adapter = MistralVibeAdapter()
    cmd = adapter._build_command("test", {"model": "devstral-2", "max_turns": 30})
    assert "--max-turns" in cmd
    assert "30" in cmd


def test_generate_config_toml_with_mcp(tmp_path):
    adapter = MistralVibeAdapter()
    adapter._generate_config(tmp_path, {
        "model": "devstral-2",
        "mcp_servers": [
            {"name": "my-server", "transport": "stdio", "command": "npx my-server"},
        ],
    })
    config_file = tmp_path / ".vibe" / "config.toml"
    assert config_file.exists()
    content = config_file.read_text()
    assert "mcp_servers" in content
    assert "devstral-2" in content


def test_parse_json_output():
    adapter = MistralVibeAdapter()
    output = json.dumps([
        {"role": "assistant", "content": "Here is the code"},
        {"type": "result", "usage": {"prompt_tokens": 100, "completion_tokens": 50},
         "total_cost_usd": 0.005, "duration_ms": 2000},
    ])
    conversation, token_usage, cost = adapter._parse_output(output)
    assert len(conversation) >= 1
    assert cost == 0.005
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_adapter_vibe.py -v`
Expected: FAIL

**Step 3: Implement Mistral Vibe adapter**

`src/agent_eval/adapters/mistral_vibe.py`:
```python
from __future__ import annotations

import json
import subprocess
import tempfile
import time
import os
from pathlib import Path
from typing import Any

from agent_eval.adapters.base import AdapterResult, BaseAdapter


class MistralVibeAdapter(BaseAdapter):

    def cli_name(self) -> str:
        return "vibe"

    def agent_type(self) -> str:
        return "mistral-vibe"

    def skills_dir_name(self) -> str:
        return ".vibe"

    def _build_command(self, prompt: str, config: dict[str, Any]) -> list[str]:
        cmd = ["vibe", "--prompt", prompt, "--output", "json"]
        if max_turns := config.get("max_turns"):
            cmd.extend(["--max-turns", str(max_turns)])
        if max_price := config.get("max_price"):
            cmd.extend(["--max-price", str(max_price)])
        return cmd

    def _generate_config(self, workdir: Path, config: dict[str, Any]) -> None:
        """Generate .vibe/config.toml in the workspace."""
        lines = []

        if model := config.get("model"):
            lines.append(f'active_model = "{model}"')

        if mcp_servers := config.get("mcp_servers"):
            for server in mcp_servers:
                lines.append("")
                lines.append("[[mcp_servers]]")
                for key, value in server.items():
                    if isinstance(value, str):
                        lines.append(f'{key} = "{value}"')
                    else:
                        lines.append(f"{key} = {value}")

        if lines:
            config_dir = workdir / ".vibe"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "config.toml").write_text("\n".join(lines) + "\n")

    def _parse_output(self, stdout: str) -> tuple[list[dict], dict | None, float | None]:
        """Parse JSON output from vibe --output json."""
        conversation: list[dict] = []
        token_usage = None
        cost = None

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return conversation, token_usage, cost

        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue

            if item.get("role") == "assistant":
                conversation.append({
                    "role": "assistant",
                    "content": item.get("content", ""),
                })

            if item.get("type") == "result":
                usage = item.get("usage", {})
                if usage:
                    token_usage = {
                        "input": usage.get("prompt_tokens", 0),
                        "output": usage.get("completion_tokens", 0),
                    }
                cost = item.get("total_cost_usd")

        return conversation, token_usage, cost

    def run(self, prompt: str, workdir: Path, config: dict[str, Any]) -> AdapterResult:
        self._generate_config(workdir, config)
        cmd = self._build_command(prompt, config)

        vibe_home = tempfile.mkdtemp(prefix="vibe-home-")

        start = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=config.get("timeout", 300),
                env={**os.environ, "VIBE_HOME": vibe_home},
            )
        except subprocess.TimeoutExpired as e:
            duration = time.monotonic() - start
            return AdapterResult(
                stdout=e.stdout or "", stderr=e.stderr or "",
                exit_code=-1, duration_seconds=duration,
            )
        duration = time.monotonic() - start
        conversation, token_usage, cost = self._parse_output(proc.stdout)
        return AdapterResult(
            stdout=proc.stdout, stderr=proc.stderr,
            exit_code=proc.returncode, duration_seconds=duration,
            conversation=conversation, token_usage=token_usage, cost_usd=cost,
        )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_adapter_vibe.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add src/agent_eval/adapters/mistral_vibe.py tests/test_adapter_vibe.py
git commit -m "feat: Mistral Vibe adapter with config.toml generation and JSON parsing"
```

---

### Task 9: Metrics Collector

**Files:**
- Create: `src/agent_eval/metrics.py`
- Create: `tests/test_metrics.py`

**Step 1: Write the failing tests**

`tests/test_metrics.py`:
```python
import pytest
from pathlib import Path
from agent_eval.metrics import collect_metrics
from agent_eval.adapters.base import AdapterResult
from agent_eval.assertions.base import AssertionResult


def test_collect_metrics_basic(tmp_path):
    # Simulate workspace before/after
    workspace_before = {"existing.tf"}
    workspace = tmp_path
    (workspace / "existing.tf").write_text("modified content\nsecond line")
    (workspace / "new.tf").write_text("new file\nline 2\nline 3")

    adapter_result = AdapterResult(
        stdout="output",
        stderr="",
        exit_code=0,
        duration_seconds=12.5,
        conversation=[{"role": "assistant"}, {"role": "assistant", "tool_use": {"name": "Bash"}}],
        token_usage={"input": 500, "output": 200},
        cost_usd=0.03,
    )

    assertion_results = [
        AssertionResult(name="a1", passed=True, message=""),
        AssertionResult(name="a2", passed=True, message=""),
        AssertionResult(name="a3", passed=False, message="failed"),
    ]

    metrics = collect_metrics(
        adapter_result=adapter_result,
        assertion_results=assertion_results,
        workspace=workspace,
        files_before=workspace_before,
    )

    assert metrics["wall_clock_seconds"] == 12.5
    assert metrics["exit_code"] == 0
    assert metrics["files_created"] == 1  # new.tf
    assert metrics["files_modified"] == 1  # existing.tf
    assert metrics["token_usage_input"] == 500
    assert metrics["token_usage_output"] == 200
    assert metrics["cost_usd"] == 0.03
    assert metrics["tool_calls_count"] == 1
    assert metrics["assertion_pass_count"] == 2
    assert metrics["assertion_fail_count"] == 1
    assert metrics["assertion_pass_rate"] == pytest.approx(66.67, abs=0.1)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_metrics.py -v`
Expected: FAIL

**Step 3: Implement metrics collector**

`src/agent_eval/metrics.py`:
```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_eval.adapters.base import AdapterResult
from agent_eval.assertions.base import AssertionResult


def _count_lines(directory: Path) -> int:
    total = 0
    for f in directory.rglob("*"):
        if f.is_file():
            try:
                total += len(f.read_text().splitlines())
            except (UnicodeDecodeError, PermissionError):
                pass
    return total


def collect_metrics(
    adapter_result: AdapterResult,
    assertion_results: list[AssertionResult],
    workspace: Path,
    files_before: set[str],
) -> dict[str, Any]:
    """Collect all metrics for a single adapter run."""
    # File diff
    files_after = {
        str(f.relative_to(workspace))
        for f in workspace.rglob("*")
        if f.is_file()
    }
    files_created = len(files_after - files_before)
    files_modified = len(files_before & files_after)  # simplified: assumes all pre-existing were touched

    # Count lines in new/modified files
    total_lines = 0
    for f in workspace.rglob("*"):
        if f.is_file():
            rel = str(f.relative_to(workspace))
            if rel not in files_before or rel in files_before:
                try:
                    total_lines += len(f.read_text().splitlines())
                except (UnicodeDecodeError, PermissionError):
                    pass

    # Tool calls
    tool_calls = sum(
        1 for entry in adapter_result.conversation
        if "tool_use" in entry
    )

    # Assertions
    passed = sum(1 for r in assertion_results if r.passed)
    failed = sum(1 for r in assertion_results if not r.passed)
    total = passed + failed
    pass_rate = (passed / total * 100) if total > 0 else 0.0

    # Token usage
    tu = adapter_result.token_usage or {}

    return {
        "wall_clock_seconds": adapter_result.duration_seconds,
        "exit_code": adapter_result.exit_code,
        "files_created": files_created,
        "files_modified": files_modified,
        "total_lines_generated": total_lines,
        "token_usage_input": tu.get("input"),
        "token_usage_output": tu.get("output"),
        "cost_usd": adapter_result.cost_usd,
        "tool_calls_count": tool_calls,
        "assertion_pass_count": passed,
        "assertion_fail_count": failed,
        "assertion_pass_rate": round(pass_rate, 2),
    }
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_metrics.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add src/agent_eval/metrics.py tests/test_metrics.py
git commit -m "feat: metrics collector (timing, tokens, cost, assertions, file diff)"
```

---

### Task 10: Runner (Orchestrator)

**Files:**
- Create: `src/agent_eval/runner.py`
- Create: `tests/test_runner.py`

**Step 1: Write the failing tests**

`tests/test_runner.py`:
```python
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from agent_eval.runner import Runner
from agent_eval.adapters.base import AdapterResult
from agent_eval.config import load_config


@pytest.fixture
def eval_config(tmp_path):
    fixture_dir = tmp_path / "fixtures" / "empty"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / ".gitkeep").write_text("")

    config_file = tmp_path / "eval.yaml"
    config_file.write_text(f"""
assistants:
  mock-claude:
    adapter: claude-code
    args:
      model: sonnet

tasks:
  - name: simple-test
    prompt: "Create hello.py"
    workdir: {fixture_dir}
    timeout: 10
    assertions:
      - file_exists: "hello.py"
""")
    return load_config(config_file)


def test_runner_creates_run_directory(tmp_path, eval_config):
    runner = Runner(config=eval_config, output_dir=tmp_path / "runs")

    mock_result = AdapterResult(
        stdout="", stderr="", exit_code=0, duration_seconds=1.0,
    )
    with patch("agent_eval.adapters.claude_code.ClaudeCodeAdapter.run", return_value=mock_result):
        run_dir = runner.execute()

    assert run_dir.exists()
    assert (run_dir / "results.json").exists()
    assert (run_dir / "meta.yaml").exists()


def test_runner_captures_results(tmp_path, eval_config):
    runner = Runner(config=eval_config, output_dir=tmp_path / "runs")

    mock_result = AdapterResult(
        stdout="", stderr="", exit_code=0, duration_seconds=1.0,
        token_usage={"input": 100, "output": 50}, cost_usd=0.01,
    )
    with patch("agent_eval.adapters.claude_code.ClaudeCodeAdapter.run", return_value=mock_result):
        run_dir = runner.execute()

    results = json.loads((run_dir / "results.json").read_text())
    assert "mock-claude" in results
    assert "simple-test" in results["mock-claude"]
    task_result = results["mock-claude"]["simple-test"]
    assert "metrics" in task_result
    assert "assertions" in task_result
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_runner.py -v`
Expected: FAIL

**Step 3: Implement runner**

`src/agent_eval/runner.py`:
```python
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from agent_eval.adapters.base import AdapterResult, BaseAdapter, get_adapter
from agent_eval.assertions.deterministic import evaluate_assertion
from agent_eval.assertions.base import AssertionResult
from agent_eval.config import EvalConfig, AssistantConfig, TaskConfig
from agent_eval.metrics import collect_metrics
from agent_eval.workspace import WorkspaceManager


class Runner:
    """Orchestrates evaluation runs."""

    def __init__(
        self,
        config: EvalConfig,
        output_dir: Path,
        task_filter: str | None = None,
        assistant_filter: str | None = None,
    ):
        self.config = config
        self.output_dir = output_dir
        self.task_filter = task_filter
        self.assistant_filter = assistant_filter

    def execute(self) -> Path:
        """Run all tasks against all assistants. Returns the run directory."""
        run_id = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
        run_dir = self.output_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        workspace_mgr = WorkspaceManager(base_dir=run_dir)
        all_results: dict[str, dict[str, Any]] = {}

        tasks = self.config.tasks
        if self.task_filter:
            tasks = [t for t in tasks if t.name == self.task_filter]

        assistants = self.config.assistants
        if self.assistant_filter:
            assistants = {
                k: v for k, v in assistants.items()
                if k == self.assistant_filter
            }

        for assistant_name, assistant_config in assistants.items():
            all_results[assistant_name] = {}
            adapter = get_adapter(assistant_config.adapter)

            for task in tasks:
                result = self._run_task(
                    workspace_mgr=workspace_mgr,
                    adapter=adapter,
                    assistant_name=assistant_name,
                    assistant_config=assistant_config,
                    task=task,
                    run_id=run_id,
                )
                all_results[assistant_name][task.name] = result

        # Write results
        (run_dir / "results.json").write_text(
            json.dumps(all_results, indent=2, default=str)
        )

        # Write metadata
        meta = {
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "assistants": list(assistants.keys()),
            "tasks": [t.name for t in tasks],
        }
        (run_dir / "meta.yaml").write_text(yaml.dump(meta, default_flow_style=False))

        return run_dir

    def _run_task(
        self,
        workspace_mgr: WorkspaceManager,
        adapter: BaseAdapter,
        assistant_name: str,
        assistant_config: AssistantConfig,
        task: TaskConfig,
        run_id: str,
    ) -> dict[str, Any]:
        """Run a single task for a single assistant."""
        source_dir = Path(task.workdir)
        workspace = workspace_mgr.create_workspace(
            source_dir=source_dir,
            run_id=".",  # already inside run_dir
            assistant_name=assistant_name,
            task_name=task.name,
        )

        # Snapshot files before
        files_before = {
            str(f.relative_to(workspace))
            for f in workspace.rglob("*")
            if f.is_file()
        }

        # Install skills
        for skill in assistant_config.skills:
            if skill.startswith("./") or skill.startswith("/"):
                workspace_mgr.install_local_skill(
                    workspace=workspace,
                    skill_path=Path(skill),
                    skills_dir_name=adapter.skills_dir_name(),
                )
            else:
                workspace_mgr.install_github_skill(
                    workspace=workspace,
                    skill_ref=skill,
                    agent_type=adapter.agent_type(),
                )

        # Run adapter
        config = {**assistant_config.args, "timeout": task.timeout}
        adapter_result = adapter.run(
            prompt=task.prompt,
            workdir=workspace,
            config=config,
        )

        # Evaluate assertions
        assertion_results = []
        for assertion_def in task.assertions:
            ar = evaluate_assertion(workspace, assertion_def)
            assertion_results.append(ar)

        # Collect metrics
        metrics = collect_metrics(
            adapter_result=adapter_result,
            assertion_results=assertion_results,
            workspace=workspace,
            files_before=files_before,
        )

        # Save conversation log
        conv_dir = workspace.parent
        conv_file = conv_dir / "conversation.json"
        conv_file.write_text(
            json.dumps(adapter_result.conversation, indent=2, default=str)
        )

        return {
            "metrics": metrics,
            "assertions": [
                {"name": ar.name, "passed": ar.passed, "message": ar.message}
                for ar in assertion_results
            ],
            "all_passed": all(ar.passed for ar in assertion_results),
        }
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_runner.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add src/agent_eval/runner.py tests/test_runner.py
git commit -m "feat: runner orchestrator (workspace setup, skill install, run, evaluate)"
```

---

### Task 11: HTML Report Generator

**Files:**
- Create: `src/agent_eval/reporting/__init__.py`
- Create: `src/agent_eval/reporting/html.py`
- Create: `src/agent_eval/reporting/templates/report.html.j2`
- Create: `tests/test_reporting.py`

**Step 1: Write the failing tests**

`tests/test_reporting.py`:
```python
import json
import pytest
from pathlib import Path
from agent_eval.reporting.html import generate_report


@pytest.fixture
def sample_run_dir(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    results = {
        "claude-baseline": {
            "task-1": {
                "metrics": {
                    "wall_clock_seconds": 10.5,
                    "exit_code": 0,
                    "files_created": 2,
                    "files_modified": 0,
                    "total_lines_generated": 50,
                    "token_usage_input": 500,
                    "token_usage_output": 200,
                    "cost_usd": 0.03,
                    "tool_calls_count": 5,
                    "assertion_pass_count": 3,
                    "assertion_fail_count": 0,
                    "assertion_pass_rate": 100.0,
                },
                "assertions": [
                    {"name": "file_exists: main.tf", "passed": True, "message": ""},
                    {"name": "file_exists: variables.tf", "passed": True, "message": ""},
                    {"name": "command_succeeds: terraform validate", "passed": True, "message": ""},
                ],
                "all_passed": True,
            }
        },
        "codex-baseline": {
            "task-1": {
                "metrics": {
                    "wall_clock_seconds": 15.2,
                    "exit_code": 0,
                    "files_created": 1,
                    "files_modified": 0,
                    "total_lines_generated": 30,
                    "token_usage_input": 800,
                    "token_usage_output": 300,
                    "cost_usd": None,
                    "tool_calls_count": 8,
                    "assertion_pass_count": 2,
                    "assertion_fail_count": 1,
                    "assertion_pass_rate": 66.67,
                },
                "assertions": [
                    {"name": "file_exists: main.tf", "passed": True, "message": ""},
                    {"name": "file_exists: variables.tf", "passed": False, "message": "File not found"},
                    {"name": "command_succeeds: terraform validate", "passed": True, "message": ""},
                ],
                "all_passed": False,
            }
        },
    }
    (run_dir / "results.json").write_text(json.dumps(results, indent=2))
    return run_dir


def test_generate_report_creates_html(sample_run_dir):
    report_path = generate_report(sample_run_dir)
    assert report_path.exists()
    assert report_path.suffix == ".html"


def test_report_contains_assistant_names(sample_run_dir):
    report_path = generate_report(sample_run_dir)
    html = report_path.read_text()
    assert "claude-baseline" in html
    assert "codex-baseline" in html


def test_report_contains_task_names(sample_run_dir):
    report_path = generate_report(sample_run_dir)
    html = report_path.read_text()
    assert "task-1" in html


def test_report_is_self_contained(sample_run_dir):
    report_path = generate_report(sample_run_dir)
    html = report_path.read_text()
    # Should not reference external CSS/JS
    assert "<link rel=" not in html or "stylesheet" not in html
    assert "<style>" in html
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_reporting.py -v`
Expected: FAIL

**Step 3: Create the Jinja2 template**

`src/agent_eval/reporting/__init__.py`:
```python
"""HTML report generation."""
```

`src/agent_eval/reporting/templates/report.html.j2`:

This file will be large. Create it with a clean, functional HTML template:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>agent-eval Report</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f5f5; color: #333; padding: 24px; }
  h1 { font-size: 24px; margin-bottom: 8px; }
  .meta { color: #666; font-size: 14px; margin-bottom: 24px; }
  table { width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 24px; }
  th, td { padding: 12px 16px; text-align: left; border-bottom: 1px solid #eee; font-size: 14px; }
  th { background: #fafafa; font-weight: 600; }
  .pass { background: #e6f9e6; color: #1a7a1a; }
  .partial { background: #fff8e6; color: #8a6d00; }
  .fail { background: #fde6e6; color: #a00; }
  .metric { font-size: 12px; color: #666; }
  .details { display: none; background: #fafafa; padding: 16px; }
  .details.open { display: block; }
  .toggle { cursor: pointer; user-select: none; }
  .toggle:hover { background: #f0f0f0; }
  .assertion-list { list-style: none; padding: 0; }
  .assertion-list li { padding: 4px 0; font-size: 13px; }
  .assertion-list li::before { content: "✓ "; color: #1a7a1a; }
  .assertion-list li.failed::before { content: "✗ "; color: #a00; }
  .bar { display: inline-block; height: 16px; border-radius: 3px; min-width: 4px; }
  .bar-container { display: flex; gap: 4px; align-items: center; }
  .chart-section { margin-bottom: 24px; }
  .chart-row { display: flex; align-items: center; gap: 8px; margin: 4px 0; font-size: 13px; }
  .chart-label { width: 140px; text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .chart-bar { height: 20px; border-radius: 3px; transition: width 0.3s; }
  .colors { --c0: #4285f4; --c1: #ea4335; --c2: #fbbc04; --c3: #34a853; --c4: #ff6d01; --c5: #46bdc6; }
</style>
</head>
<body class="colors">
<h1>agent-eval Report</h1>
<p class="meta">Generated from run data</p>

<h2>Summary</h2>
<table>
  <thead>
    <tr>
      <th>Task</th>
      {% for assistant in assistants %}
      <th>{{ assistant }}</th>
      {% endfor %}
    </tr>
  </thead>
  <tbody>
    {% for task in tasks %}
    <tr class="toggle" onclick="toggleDetails('{{ task }}')">
      <td><strong>{{ task }}</strong></td>
      {% for assistant in assistants %}
      {% set r = results[assistant][task] %}
      {% if r %}
      {% if r.all_passed %}
      <td class="pass">
      {% elif r.metrics.assertion_pass_rate > 0 %}
      <td class="partial">
      {% else %}
      <td class="fail">
      {% endif %}
        {{ r.metrics.assertion_pass_rate }}% pass<br>
        <span class="metric">{{ "%.1f"|format(r.metrics.wall_clock_seconds) }}s | {{ r.metrics.tool_calls_count }} tools{% if r.metrics.cost_usd %} | ${{ "%.4f"|format(r.metrics.cost_usd) }}{% endif %}</span>
      </td>
      {% else %}
      <td>—</td>
      {% endif %}
      {% endfor %}
    </tr>
    <tr>
      <td colspan="{{ assistants|length + 1 }}">
        <div class="details" id="details-{{ task }}">
          <table>
            <thead>
              <tr>
                <th>Metric</th>
                {% for assistant in assistants %}
                <th>{{ assistant }}</th>
                {% endfor %}
              </tr>
            </thead>
            <tbody>
              {% for metric_key in metric_keys %}
              <tr>
                <td>{{ metric_key }}</td>
                {% for assistant in assistants %}
                {% set r = results[assistant][task] %}
                <td>{% if r %}{{ r.metrics[metric_key] if r.metrics[metric_key] is not none else "—" }}{% else %}—{% endif %}</td>
                {% endfor %}
              </tr>
              {% endfor %}
            </tbody>
          </table>
          <h4 style="margin: 12px 0 8px;">Assertions</h4>
          {% for assistant in assistants %}
          <p><strong>{{ assistant }}</strong></p>
          {% set r = results[assistant][task] %}
          {% if r %}
          <ul class="assertion-list">
            {% for a in r.assertions %}
            <li{% if not a.passed %} class="failed"{% endif %}>{{ a.name }}{% if a.message %} — {{ a.message }}{% endif %}</li>
            {% endfor %}
          </ul>
          {% endif %}
          {% endfor %}
        </div>
      </td>
    </tr>
    {% endfor %}
  </tbody>
</table>

<h2>Metrics Comparison</h2>
{% for metric_key in ["wall_clock_seconds", "cost_usd", "token_usage_input", "tool_calls_count", "assertion_pass_rate"] %}
<div class="chart-section">
  <h3>{{ metric_key }}</h3>
  {% for task in tasks %}
  <p style="font-size:12px; color:#666; margin: 4px 0;">{{ task }}</p>
  {% set max_val = [] %}
  {% for assistant in assistants %}
    {% set r = results[assistant][task] %}
    {% if r and r.metrics[metric_key] is not none %}
      {% if max_val.append(r.metrics[metric_key]) %}{% endif %}
    {% endif %}
  {% endfor %}
  {% set max_value = max_val|max if max_val else 1 %}
  {% for assistant in assistants %}
  {% set r = results[assistant][task] %}
  {% set val = r.metrics[metric_key] if r and r.metrics[metric_key] is not none else 0 %}
  {% set pct = (val / max_value * 100) if max_value > 0 else 0 %}
  <div class="chart-row">
    <span class="chart-label">{{ assistant }}</span>
    <div class="chart-bar" style="width: {{ pct }}%; max-width: 400px; background: var(--c{{ loop.index0 % 6 }});">&nbsp;</div>
    <span>{{ val if val else "—" }}</span>
  </div>
  {% endfor %}
  {% endfor %}
</div>
{% endfor %}

<script>
function toggleDetails(task) {
  var el = document.getElementById('details-' + task);
  if (el) el.classList.toggle('open');
}
</script>
</body>
</html>
```

**Step 4: Implement report generator**

`src/agent_eval/reporting/html.py`:
```python
from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


def generate_report(run_dir: Path) -> Path:
    """Generate a self-contained HTML report from run results."""
    results_file = run_dir / "results.json"
    results = json.loads(results_file.read_text())

    assistants = list(results.keys())
    tasks = []
    for assistant_results in results.values():
        for task_name in assistant_results:
            if task_name not in tasks:
                tasks.append(task_name)

    metric_keys = [
        "wall_clock_seconds", "exit_code", "files_created", "files_modified",
        "total_lines_generated", "token_usage_input", "token_usage_output",
        "cost_usd", "tool_calls_count", "assertion_pass_count",
        "assertion_fail_count", "assertion_pass_rate",
    ]

    template_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(template_dir), autoescape=False)
    template = env.get_template("report.html.j2")

    html = template.render(
        assistants=assistants,
        tasks=tasks,
        results=results,
        metric_keys=metric_keys,
    )

    report_path = run_dir / "report.html"
    report_path.write_text(html)
    return report_path
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_reporting.py -v`
Expected: all PASS

**Step 6: Commit**

```bash
git add src/agent_eval/reporting/ tests/test_reporting.py
git commit -m "feat: HTML report generator with summary table, detail view, metric charts"
```

---

### Task 12: Wire CLI to Runner + Report

**Files:**
- Modify: `src/agent_eval/cli.py`
- Create: `tests/test_cli.py`

**Step 1: Write the failing tests**

`tests/test_cli.py`:
```python
import pytest
from pathlib import Path
from typer.testing import CliRunner
from agent_eval.cli import app

runner = CliRunner()


def test_init_creates_example_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert (tmp_path / "eval.yaml").exists()


def test_run_missing_config():
    result = runner.invoke(app, ["run", "nonexistent.yaml"])
    assert result.exit_code != 0


def test_report_missing_dir():
    result = runner.invoke(app, ["report", "/tmp/nonexistent-run-dir"])
    assert result.exit_code != 0
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL (or partial FAIL)

**Step 3: Wire up the CLI**

`src/agent_eval/cli.py`:
```python
from __future__ import annotations

import sys
from pathlib import Path

import typer

app = typer.Typer(name="agent-eval", help="Evaluate AI coding assistants")


@app.command()
def run(
    config: str = typer.Argument(help="Path to eval YAML config"),
    task: str | None = typer.Option(None, help="Run only this task"),
    assistant: str | None = typer.Option(None, help="Run only this assistant"),
    parallel: bool = typer.Option(False, help="Run assistants concurrently per task"),
    output_dir: str = typer.Option("runs", help="Output directory for run results"),
):
    """Run evaluation tasks against configured assistants."""
    from agent_eval.config import load_config
    from agent_eval.runner import Runner
    from agent_eval.reporting.html import generate_report

    config_path = Path(config)
    if not config_path.exists():
        typer.echo(f"Error: config file not found: {config}", err=True)
        raise typer.Exit(1)

    eval_config = load_config(config_path)
    runner = Runner(
        config=eval_config,
        output_dir=Path(output_dir),
        task_filter=task,
        assistant_filter=assistant,
    )

    typer.echo("Starting evaluation run...")
    run_dir = runner.execute()

    typer.echo("Generating report...")
    report_path = generate_report(run_dir)

    typer.echo(f"Run complete: {run_dir}")
    typer.echo(f"Report: {report_path}")

    # Exit with non-zero if any assertion failed
    import json
    results = json.loads((run_dir / "results.json").read_text())
    all_passed = all(
        task_result.get("all_passed", False)
        for assistant_results in results.values()
        for task_result in assistant_results.values()
    )
    if not all_passed:
        raise typer.Exit(1)


@app.command()
def report(
    run_dir: str = typer.Argument(help="Path to run output directory"),
):
    """Regenerate HTML report from a previous run."""
    from agent_eval.reporting.html import generate_report

    run_path = Path(run_dir)
    if not run_path.exists() or not (run_path / "results.json").exists():
        typer.echo(f"Error: not a valid run directory: {run_dir}", err=True)
        raise typer.Exit(1)

    report_path = generate_report(run_path)
    typer.echo(f"Report generated: {report_path}")


@app.command()
def init():
    """Initialize a new eval project with example config."""
    example = Path("eval.yaml")
    if example.exists():
        typer.echo("eval.yaml already exists, skipping.")
        return

    example.write_text("""\
assistants:
  claude-baseline:
    adapter: claude-code
    args:
      model: sonnet

tasks:
  - name: hello-world
    prompt: "Create a Python script that prints 'Hello, World!'"
    workdir: ./fixtures/empty
    timeout: 120
    assertions:
      - file_exists: "hello.py"
      - command_succeeds: "python hello.py"
""")

    fixtures = Path("fixtures/empty")
    fixtures.mkdir(parents=True, exist_ok=True)
    (fixtures / ".gitkeep").write_text("")

    typer.echo("Initialized eval project:")
    typer.echo("  eval.yaml        - example eval config")
    typer.echo("  fixtures/empty/  - empty fixture directory")
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: all PASS

**Step 5: Run full test suite**

Run: `uv run pytest -v`
Expected: all tests PASS

**Step 6: Commit**

```bash
git add src/agent_eval/cli.py tests/test_cli.py
git commit -m "feat: wire CLI commands to runner and report generator"
```

---

### Task 13: Integration Smoke Test

**Files:**
- Create: `tests/test_integration.py`

This test uses a mock adapter to verify the full pipeline end-to-end without calling real CLIs.

**Step 1: Write the integration test**

`tests/test_integration.py`:
```python
import json
import pytest
from pathlib import Path
from unittest.mock import patch
from agent_eval.adapters.base import AdapterResult
from agent_eval.config import load_config
from agent_eval.runner import Runner
from agent_eval.reporting.html import generate_report


@pytest.fixture
def full_eval_setup(tmp_path):
    """Set up a complete eval scenario with fixtures."""
    # Create fixture directory
    fixture = tmp_path / "fixtures" / "test-repo"
    fixture.mkdir(parents=True)
    (fixture / "README.md").write_text("# Test Repo")

    # Create eval config
    config_file = tmp_path / "eval.yaml"
    config_file.write_text(f"""\
assistants:
  claude-baseline:
    adapter: claude-code
    args:
      model: sonnet
  codex-baseline:
    adapter: codex
    args:
      model: o3

tasks:
  - name: create-script
    prompt: "Create a Python hello world script"
    workdir: {fixture}
    timeout: 10
    assertions:
      - file_exists: "hello.py"
      - command_succeeds: "echo ok"
""")
    return config_file, tmp_path


def _make_mock_result(workdir: Path) -> AdapterResult:
    """Create a mock result that also creates the expected file."""
    (workdir / "hello.py").write_text('print("Hello, World!")')
    return AdapterResult(
        stdout='{"type":"result","result":"Done"}',
        stderr="",
        exit_code=0,
        duration_seconds=5.0,
        conversation=[{"role": "assistant", "content": "Created hello.py"}],
        token_usage={"input": 300, "output": 100},
        cost_usd=0.02,
    )


def test_full_pipeline(full_eval_setup):
    config_file, tmp_path = full_eval_setup
    config = load_config(config_file)

    def mock_run(self, prompt, workdir, config):
        return _make_mock_result(workdir)

    with patch("agent_eval.adapters.claude_code.ClaudeCodeAdapter.run", mock_run), \
         patch("agent_eval.adapters.codex.CodexAdapter.run", mock_run):

        runner = Runner(config=config, output_dir=tmp_path / "runs")
        run_dir = runner.execute()

        # Verify run directory structure
        assert (run_dir / "results.json").exists()
        assert (run_dir / "meta.yaml").exists()

        # Verify results content
        results = json.loads((run_dir / "results.json").read_text())
        assert "claude-baseline" in results
        assert "codex-baseline" in results

        for assistant in ["claude-baseline", "codex-baseline"]:
            task_result = results[assistant]["create-script"]
            assert task_result["all_passed"] is True
            assert task_result["metrics"]["wall_clock_seconds"] == 5.0
            assert task_result["metrics"]["cost_usd"] == 0.02

        # Generate and verify report
        report_path = generate_report(run_dir)
        assert report_path.exists()
        html = report_path.read_text()
        assert "claude-baseline" in html
        assert "codex-baseline" in html
        assert "create-script" in html
        assert "100.0% pass" in html
```

**Step 2: Run the integration test**

Run: `uv run pytest tests/test_integration.py -v`
Expected: PASS

**Step 3: Run full suite**

Run: `uv run pytest -v`
Expected: all PASS

**Step 4: Lint**

Run: `uv run ruff check src/ tests/`
Expected: no errors (fix any that appear)

**Step 5: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: integration smoke test for full pipeline"
```

---

### Task 14: Example Configs + Final Polish

**Files:**
- Create: `examples/simple-codegen-eval.yaml`
- Create: `examples/terraform-module-eval.yaml`

**Step 1: Create example configs**

`examples/simple-codegen-eval.yaml`:
```yaml
assistants:
  claude-baseline:
    adapter: claude-code
    args:
      model: sonnet

  codex-baseline:
    adapter: codex
    args:
      model: o3

tasks:
  - name: hello-world-python
    prompt: "Create a Python script called hello.py that prints 'Hello, World!'"
    workdir: ./fixtures/empty
    timeout: 120
    assertions:
      - file_exists: "hello.py"
      - command_succeeds: "python hello.py"
```

`examples/terraform-module-eval.yaml`:
```yaml
assistants:
  claude-baseline:
    adapter: claude-code
    args:
      model: sonnet

  claude-with-skills:
    adapter: claude-code
    args:
      model: sonnet
    skills:
      - terraform-ibm-modules/terraform-ibm-modules-skills

  codex-baseline:
    adapter: codex
    args:
      model: o3

tasks:
  - name: scaffold-terraform-vpc
    prompt: "Create a Terraform module for an IBM Cloud VPC with 3 subnets across different zones"
    workdir: ./fixtures/empty-repo
    timeout: 300
    assertions:
      - file_exists: "main.tf"
      - file_exists: "variables.tf"
      - file_exists: "outputs.tf"
      - file_contains: { path: "main.tf", pattern: "resource.*ibm_is_vpc" }
      - command_succeeds: "terraform fmt -check"
```

**Step 2: Create fixture directories**

```bash
mkdir -p examples/fixtures/empty
touch examples/fixtures/empty/.gitkeep
mkdir -p examples/fixtures/empty-repo
cd examples/fixtures/empty-repo && git init && touch .gitkeep && git add . && git commit -m "init" && cd -
```

**Step 3: Run all tests one final time**

Run: `uv run pytest -v`
Expected: all PASS

**Step 4: Lint and fix**

Run: `uv run ruff check src/ tests/ --fix`
Expected: clean

**Step 5: Commit**

```bash
git add examples/
git commit -m "docs: add example eval configs for simple codegen and Terraform"
```

---

## Dependency Graph

```
Task 1: Scaffolding
  └─ Task 2: Config Models
      └─ Task 3: Base Adapter
          ├─ Task 6: Claude Code Adapter
          ├─ Task 7: Codex Adapter
          └─ Task 8: Mistral Vibe Adapter
      └─ Task 4: Assertions
      └─ Task 5: Workspace Manager
      └─ Task 9: Metrics Collector
          └─ Task 10: Runner
              └─ Task 11: HTML Report
                  └─ Task 12: Wire CLI
                      └─ Task 13: Integration Test
                          └─ Task 14: Examples + Polish
```

Tasks 4, 5, 6, 7, 8, 9 can be parallelized after Task 3 is complete.
