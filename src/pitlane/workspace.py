"""Workspace isolation and skill installation."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from pitlane.config import SkillRef


_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z_0-9]*)(?::-(.*?))?\}")


def _expand_env(value: str) -> str:
    """Expand ${VAR} and ${VAR:-default} in a string using os.environ."""

    def _replace(m: re.Match) -> str:
        var = m.group(1)
        default = m.group(2)
        if var in os.environ:
            return os.environ[var]
        if default is not None:
            return str(default)
        raise ValueError(f"MCP env variable ${{{var}}} is not set in the environment")

    return _ENV_RE.sub(_replace, value)


def validate_mcp_env(assistants: dict[str, Any]) -> None:
    """Check that all MCP env ${VAR} references (without defaults) are set.

    Raises ValueError listing every missing variable so the user can fix them
    all at once rather than hitting them one-by-one mid-run.
    """
    missing: list[str] = []
    for name, asst in assistants.items():
        for mcp in asst.mcps:
            for key, value in mcp.env.items():
                for m in _ENV_RE.finditer(value):
                    var, default = m.group(1), m.group(2)
                    if default is None and var not in os.environ:
                        missing.append(f"  {name} -> mcp '{mcp.name}': ${{{var}}}")
    if missing:
        details = "\n".join(missing)
        raise ValueError(
            f"Missing environment variables required by MCP servers:\n{details}"
        )


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
        cmd = [
            "npx",
            "--yes",
            "skills",
            "add",
            skill.source,
            "--agent",
            agent_type,
            "--yes",
        ]
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
