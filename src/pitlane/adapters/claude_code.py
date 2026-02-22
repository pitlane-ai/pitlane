"""Claude Code adapter."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, TYPE_CHECKING

from expandvars import expandvars

from pitlane.adapters.base import AdapterResult, BaseAdapter
from pitlane.adapters.streaming import run_streaming_sync

if TYPE_CHECKING:
    import logging


class ClaudeCodeAdapter(BaseAdapter):
    def cli_name(self) -> str:
        return "claude"

    def agent_type(self) -> str:
        return "claude-code"

    def get_cli_version(self) -> str | None:
        try:
            import subprocess

            result = subprocess.run(
                ["claude", "--version"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def _build_command(self, prompt: str, config: dict[str, Any]) -> list[str]:
        cmd = [
            "claude",
            "-p",
            "--output-format",
            "stream-json",
            "--verbose",
            "--dangerously-skip-permissions",
            "--disable-slash-commands",
            "--setting-sources",
            "project,local",
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

    def _parse_output(
        self, stdout: str
    ) -> tuple[list[dict], dict | None, float | None, int]:
        """Parse stream-json NDJSON output into conversation, token_usage, cost, tool_calls_count."""
        conversation: list[dict] = []
        token_usage = None
        cost = None
        tool_calls_count = 0

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
                        conversation.append(
                            {
                                "role": "assistant",
                                "content": block["text"],
                            }
                        )
                    elif block.get("type") == "tool_use":
                        tool_calls_count += 1
                        conversation.append(
                            {
                                "role": "assistant",
                                "content": "",
                                "tool_use": {
                                    "name": block.get("name", ""),
                                    "input": block.get("input", {}),
                                },
                            }
                        )
            elif msg_type == "result":
                usage = msg.get("usage", {})
                if usage:
                    token_usage = {
                        "input": usage.get("input_tokens", 0),
                        "output": usage.get("output_tokens", 0),
                    }
                cost = msg.get("total_cost_usd")

        return conversation, token_usage, cost, tool_calls_count

    def install_mcp(self, workspace: Path, mcp: Any) -> None:
        # Resolve ${VAR} references from the user's YAML config
        env = {k: expandvars(v, nounset=True) for k, v in mcp.env.items()}
        target = workspace / ".mcp.json"
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
        if env:
            entry["env"] = env
        servers[mcp.name] = entry
        target.write_text(json.dumps(data, indent=2))

    def run(
        self,
        prompt: str,
        workdir: Path,
        config: dict[str, Any],
        logger: logging.Logger,
    ) -> AdapterResult:
        cmd = self._build_command(prompt, config)
        timeout = config.get("timeout", 300)

        # Log command context
        logger.debug(f"Command: {' '.join(cmd)}")
        logger.debug(f"Working directory: {workdir}")
        logger.debug(f"Timeout: {timeout}s")
        logger.debug(f"Config: {json.dumps(config, indent=2)}")

        start = time.monotonic()

        try:
            stdout, stderr, exit_code, timed_out = run_streaming_sync(
                cmd, workdir, timeout, logger
            )
        except Exception as e:
            duration = time.monotonic() - start
            if logger:
                logger.debug(f"Command failed after {duration:.2f}s: {e}")
            return AdapterResult(
                stdout="",
                stderr=str(e),
                exit_code=-1,
                duration_seconds=duration,
                conversation=[],
                token_usage=None,
                cost_usd=None,
            )

        duration = time.monotonic() - start

        if logger:
            logger.debug(
                f"Command completed in {duration:.2f}s with exit code {exit_code}"
            )

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
