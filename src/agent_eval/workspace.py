"""Workspace isolation and skill installation."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


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
        shutil.copytree(source_dir, workspace)
        return workspace

    def install_local_skill(
        self,
        workspace: Path | str,
        skill_path: Path | str,
        skills_dir_name: str,
    ) -> None:
        """Copy a local skill directory into the workspace.

        Raises FileNotFoundError if skill_path has no SKILL.md.
        """
        workspace = Path(workspace)
        skill_path = Path(skill_path)

        if not (skill_path / "SKILL.md").exists():
            raise FileNotFoundError(
                f"SKILL.md not found in {skill_path}"
            )

        skill_name = skill_path.name
        dest = workspace / skills_dir_name / "skills" / skill_name
        shutil.copytree(skill_path, dest)

    def install_github_skill(
        self,
        workspace: Path | str,
        skill_ref: str,
        agent_type: str,
    ) -> None:
        """Run: npx skills install <ref> --agent <type> --yes.

        Raises RuntimeError on failure.
        """
        workspace = Path(workspace)
        result = subprocess.run(
            ["npx", "skills", "install", skill_ref, "--agent", agent_type, "--yes"],
            cwd=workspace,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to install skill {skill_ref}: {result.stderr}"
            )

    def cleanup_workspace(self, workspace: Path | str) -> None:
        """Remove the workspace directory."""
        workspace = Path(workspace)
        shutil.rmtree(workspace)
