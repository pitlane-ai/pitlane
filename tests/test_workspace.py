"""Tests for WorkspaceManager."""

from pathlib import Path

import pytest

from agent_eval.workspace import WorkspaceManager


@pytest.fixture
def base_dir(tmp_path: Path) -> Path:
    return tmp_path / "workspaces"


@pytest.fixture
def manager(base_dir: Path) -> WorkspaceManager:
    return WorkspaceManager(base_dir)


@pytest.fixture
def source_dir(tmp_path: Path) -> Path:
    """Create a source directory with nested files."""
    src = tmp_path / "source_project"
    src.mkdir()
    (src / "README.md").write_text("# Hello")
    nested = src / "sub" / "deep"
    nested.mkdir(parents=True)
    (nested / "file.txt").write_text("nested content")
    return src


def test_create_isolated_workspace(manager: WorkspaceManager, source_dir: Path):
    ws = manager.create_workspace(
        source_dir=source_dir,
        run_id="run-001",
        assistant_name="copilot",
        task_name="task-a",
    )

    assert ws.exists()
    assert ws == manager.base_dir / "run-001" / "copilot" / "task-a" / "workspace"
    assert (ws / "README.md").read_text() == "# Hello"
    assert (ws / "sub" / "deep" / "file.txt").read_text() == "nested content"

    # Ensure it is a copy, not the same directory
    assert ws != source_dir


def test_install_local_skill(manager: WorkspaceManager, tmp_path: Path):
    # Setup workspace
    ws = tmp_path / "ws"
    ws.mkdir()

    # Setup skill with SKILL.md
    skill_path = tmp_path / "my-skill"
    skill_path.mkdir()
    (skill_path / "SKILL.md").write_text("# Skill")
    (skill_path / "helper.py").write_text("pass")

    manager.install_local_skill(ws, skill_path, skills_dir_name=".agent")

    installed = ws / ".agent" / "skills" / "my-skill"
    assert installed.is_dir()
    assert (installed / "SKILL.md").read_text() == "# Skill"
    assert (installed / "helper.py").read_text() == "pass"


def test_install_local_skill_missing_skill_md(manager: WorkspaceManager, tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()

    skill_path = tmp_path / "bad-skill"
    skill_path.mkdir()
    # No SKILL.md present

    with pytest.raises(FileNotFoundError):
        manager.install_local_skill(ws, skill_path, skills_dir_name=".agent")


def test_workspace_cleanup(manager: WorkspaceManager, source_dir: Path):
    ws = manager.create_workspace(
        source_dir=source_dir,
        run_id="run-002",
        assistant_name="claude",
        task_name="task-b",
    )
    assert ws.exists()

    manager.cleanup_workspace(ws)
    assert not ws.exists()
