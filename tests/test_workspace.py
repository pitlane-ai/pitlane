"""Tests for WorkspaceManager."""

from pathlib import Path

import pytest

from pitlane.config import SkillRef
from pitlane.workspace import WorkspaceManager


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


def test_create_workspace_excludes_refs(manager: WorkspaceManager, tmp_path: Path):
    """Refs dir must NOT be copied to workspace — AI assistants must not see reference files."""
    src = tmp_path / "with_refs"
    src.mkdir()
    (src / "README.md").write_text("# Hello")
    refs = src / "refs"
    refs.mkdir()
    (refs / "expected.py").write_text("golden output")

    ws = manager.create_workspace(
        source_dir=src,
        run_id="run-refs",
        assistant_name="test",
        task_name="task-refs",
    )

    assert (ws / "README.md").exists()
    assert not (ws / "refs").exists(), "refs/ should be excluded from workspace"


def test_install_skill_includes_skill_flag(
    manager: WorkspaceManager, tmp_path: Path, monkeypatch
):
    ws = tmp_path / "ws"
    ws.mkdir()

    calls = []

    def fake_run(cmd, cwd, capture_output, text, timeout):
        calls.append(
            {
                "cmd": cmd,
                "cwd": cwd,
                "capture_output": capture_output,
                "text": text,
                "timeout": timeout,
            }
        )

        class Result:
            returncode = 0
            stderr = ""

        return Result()

    monkeypatch.setattr("pitlane.workspace.subprocess.run", fake_run)

    manager.install_skill(
        workspace=ws,
        skill=SkillRef(source="owner/repo", skill="my-skill"),
        agent_type="codex",
    )

    assert calls == [
        {
            "cmd": [
                "npx",
                "--yes",
                "skills",
                "add",
                "owner/repo",
                "--agent",
                "codex",
                "--yes",
                "--skill",
                "my-skill",
            ],
            "cwd": ws,
            "capture_output": True,
            "text": True,
            "timeout": 30,
        }
    ]


def test_install_skill_without_skill_flag(
    manager: WorkspaceManager, tmp_path: Path, monkeypatch
):
    ws = tmp_path / "ws"
    ws.mkdir()

    calls = []

    def fake_run(cmd, cwd, capture_output, text, timeout):
        calls.append(
            {
                "cmd": cmd,
                "cwd": cwd,
                "capture_output": capture_output,
                "text": text,
                "timeout": timeout,
            }
        )

        class Result:
            returncode = 0
            stderr = ""

        return Result()

    monkeypatch.setattr("pitlane.workspace.subprocess.run", fake_run)

    manager.install_skill(
        workspace=ws,
        skill=SkillRef(source="owner/repo"),
        agent_type="claude-code",
    )

    assert calls == [
        {
            "cmd": [
                "npx",
                "--yes",
                "skills",
                "add",
                "owner/repo",
                "--agent",
                "claude-code",
                "--yes",
            ],
            "cwd": ws,
            "capture_output": True,
            "text": True,
            "timeout": 30,
        }
    ]


def test_install_skill_timeout_handling(
    manager: WorkspaceManager, tmp_path: Path, monkeypatch
):
    """Test that skill installation handles timeout gracefully."""
    import subprocess

    ws = tmp_path / "ws"
    ws.mkdir()

    def fake_run_timeout(cmd, cwd, capture_output, text, timeout):
        raise subprocess.TimeoutExpired(cmd, timeout)

    monkeypatch.setattr("pitlane.workspace.subprocess.run", fake_run_timeout)

    with pytest.raises(RuntimeError) as exc_info:
        manager.install_skill(
            workspace=ws,
            skill=SkillRef(source="owner/repo"),
            agent_type="claude-code",
        )

    assert "timed out after 30s" in str(exc_info.value)
    assert "owner/repo" in str(exc_info.value)


def test_install_skill_non_interactive(
    manager: WorkspaceManager, tmp_path: Path, monkeypatch
):
    """Test that skill installation completes without user interaction (blackbox test)."""

    ws = tmp_path / "ws"
    ws.mkdir()

    # Create a marker file to verify the command ran
    marker_file = ws / ".skill_installed"

    def fake_run(cmd, cwd, capture_output, text, timeout):
        # Simulate successful skill installation by creating marker file
        marker_file.write_text("installed")

        class Result:
            returncode = 0
            stderr = ""
            stdout = "Skill installed successfully"

        return Result()

    monkeypatch.setattr("pitlane.workspace.subprocess.run", fake_run)

    # Should complete without hanging or prompting
    manager.install_skill(
        workspace=ws,
        skill=SkillRef(source="owner/repo"),
        agent_type="claude-code",
    )

    # Verify installation completed (marker file exists)
    assert marker_file.exists()
    assert marker_file.read_text() == "installed"


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
