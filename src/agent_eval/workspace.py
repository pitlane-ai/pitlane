"""Workspace isolation and skill installation."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from agent_eval.config import SkillRef


class WorkspaceManager:
    """Manages isolated workspaces for evaluation runs."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)

    def create_workspace(
        self,
        source_dir: Path | str,
        run_id: str,
        assistant_name: str,
        task_name: str,
    ) -> Path:
        """Copy source_dir to base_dir/run_id/assistant_name/task_name/workspace."""
        source_dir = Path(source_dir)
        workspace = self.base_dir / run_id / assistant_name / task_name / "workspace"
        shutil.copytree(
            source_dir,
            workspace,
            ignore=shutil.ignore_patterns("refs"),
        )
        return workspace

    def install_skill(
        self,
        workspace: Path | str,
        skill: SkillRef,
        agent_type: str,
    ) -> None:
        """Run: npx --yes skills add <ref> --agent <type> --yes [--skill <name>].

        Raises RuntimeError on failure.
        """
        workspace = Path(workspace)
        cmd = ["npx", "--yes", "skills", "add", skill.source, "--agent", agent_type, "--yes"]
        if skill.skill:
            cmd.extend(["--skill", skill.skill])
        try:
            result = subprocess.run(
                cmd,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(
                f"Skill installation timed out after 30s for {skill.source}. "
                f"Command: {' '.join(cmd)}"
            ) from e
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to install skill {skill.source}: {result.stderr}"
            )

    def cleanup_workspace(self, workspace: Path | str) -> None:
        """Remove the workspace directory."""
        workspace = Path(workspace)
        shutil.rmtree(workspace)
