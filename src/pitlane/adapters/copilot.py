"""GitHub Copilot CLI adapter."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, TYPE_CHECKING

from pitlane.adapters.base import AdapterResult, BaseAdapter
from pitlane.adapters.streaming import run_streaming_sync

if TYPE_CHECKING:
    import logging


class CopilotAdapter(BaseAdapter):
    MCP_FILENAME = ".pitlane_copilot_mcp.json"

    def cli_name(self) -> str:
        return "copilot"

    def agent_type(self) -> str:
        return "github-copilot"

    def get_cli_version(self) -> str | None:
        try:
            import subprocess

            result = subprocess.run(
                ["copilot", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def _build_command(
        self,
        prompt: str,
        config: dict[str, Any],
        workdir: Path | None = None,
    ) -> list[str]:
        cmd = ["copilot", "-p", prompt, "--yolo"]
        if workdir is not None:
            cmd.extend(["--add-dir", str(workdir.resolve())])
            mcp_file = workdir / self.MCP_FILENAME
            if mcp_file.exists():
                cmd.extend(["--additional-mcp-config", f"@{mcp_file.resolve()}"])
        if model := config.get("model"):
            cmd.extend(["--model", model])
        return cmd

    def _parse_output(
        self, stdout: str
    ) -> tuple[list[dict], dict | None, float | None, int]:
        """Parse plain-text output from gh copilot.

        Copilot has no JSON output flag; the entire stdout is treated as a
        single assistant message. Token/cost data is not available.
        """
        conversation: list[dict] = []
        if stdout.strip():
            conversation.append({"role": "assistant", "content": stdout.strip()})
        return conversation, None, None, 0

    def install_mcp(self, workspace: Path, mcp: Any) -> None:
        """Write MCP server config into workspace/.pitlane_copilot_mcp.json.

        The file path is passed to ``gh copilot --additional-mcp-config @<path>``
        by ``_build_command`` when the file is present at run time.
        """
        from pitlane.workspace import _expand_env

        expanded_env = {k: _expand_env(v) for k, v in mcp.env.items()}
        target = workspace / self.MCP_FILENAME

        data: dict = {}
        if target.exists():
            data = json.loads(target.read_text())

        servers = data.setdefault("mcpServers", {})
        entry: dict = {"type": mcp.type}
        if mcp.command is not None:
            entry["command"] = mcp.command
        if mcp.args:
            entry["args"] = mcp.args
        if mcp.url is not None:
            entry["url"] = mcp.url
        if expanded_env:
            entry["env"] = expanded_env
        servers[mcp.name] = entry
        target.write_text(json.dumps(data, indent=2))

    def run(
        self,
        prompt: str,
        workdir: Path,
        config: dict[str, Any],
        logger: logging.Logger,
    ) -> AdapterResult:
        cmd = self._build_command(prompt, config, workdir)
        timeout = config.get("timeout", 300)

        logger.debug(f"Command: {' '.join(cmd)}")
        logger.debug(f"Working directory: {workdir}")
        logger.debug(f"Timeout: {timeout}s")

        start = time.monotonic()
        try:
            stdout, stderr, exit_code, timed_out = run_streaming_sync(
                cmd, workdir, timeout, logger
            )
        except Exception as e:
            duration = time.monotonic() - start
            logger.debug(f"Command failed after {duration:.2f}s: {e}")
            return AdapterResult(
                stdout="",
                stderr=str(e),
                exit_code=-1,
                duration_seconds=duration,
            )

        duration = time.monotonic() - start
        logger.debug(f"Command completed in {duration:.2f}s with exit code {exit_code}")

        conversation, token_usage, cost, tool_calls_count = self._parse_output(stdout)
        return AdapterResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_seconds=duration,
            conversation=conversation,
            token_usage=token_usage,
            cost_usd=cost,
            tool_calls_count=tool_calls_count,
            timed_out=timed_out,
        )
