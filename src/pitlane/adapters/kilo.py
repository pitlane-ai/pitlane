"""Kilo Code adapter (forked from OpenCode)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, TYPE_CHECKING

from pitlane.adapters.base import AdapterResult, BaseAdapter
from pitlane.adapters.streaming import run_streaming_sync

if TYPE_CHECKING:
    import logging


class KiloAdapter(BaseAdapter):
    def cli_name(self) -> str:
        return "kilo"

    def agent_type(self) -> str:
        return "kilo"

    def get_cli_version(self) -> str | None:
        try:
            import subprocess

            result = subprocess.run(
                ["kilo", "--version"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def _build_command(self, prompt: str, config: dict[str, Any]) -> list[str]:
        cmd = ["kilo", "run", "--auto", "--format", "json"]
        if model := config.get("model"):
            cmd.extend(["-m", model])
        if agent := config.get("agent"):
            cmd.extend(["--agent", agent])
        cmd.append(prompt)
        return cmd

    def _parse_output(
        self, stdout: str
    ) -> tuple[list[dict], dict | None, float | None, int]:
        """Parse JSON events from kilo run --format json.

        Kilo is forked from OpenCode and uses the same event schema,
        including step_finish events for token/cost tracking.
        """
        conversation: list[dict] = []
        total_input_tokens = 0
        total_output_tokens = 0
        total_cost = 0.0
        tool_calls_count = 0

        for line in stdout.strip().splitlines():
            if not line.strip():
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")

            if msg_type in ("assistant", "assistant_message", "message"):
                content = msg.get("content", msg.get("text", ""))
                if content:
                    conversation.append({"role": "assistant", "content": content})

            if msg_type == "tool_use":
                tool_calls_count += 1
                conversation.append(
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_use": {
                            "name": msg.get("name", ""),
                            "input": msg.get("input", {}),
                        },
                    }
                )

            if msg_type == "step_finish":
                part = msg.get("part", {})
                tokens = part.get("tokens", {})
                if tokens:
                    total_input_tokens += tokens.get("input", 0)
                    total_output_tokens += tokens.get("output", 0)
                    step_cost = part.get("cost", 0)
                    if step_cost:
                        total_cost += step_cost

        token_usage = None
        if total_input_tokens > 0 or total_output_tokens > 0:
            token_usage = {
                "input": total_input_tokens,
                "output": total_output_tokens,
            }

        cost = total_cost if total_cost > 0 else None

        return conversation, token_usage, cost, tool_calls_count

    def install_mcp(self, workspace: Path, mcp: Any) -> None:
        """Write MCP server config into workspace/kilo.json.

        Uses the same structure as opencode.json since Kilo is forked from OpenCode.
        """
        from pitlane.workspace import _expand_env

        expanded_env = {k: _expand_env(v) for k, v in mcp.env.items()}
        target = workspace / "kilo.json"

        data: dict = {}
        if target.exists():
            data = json.loads(target.read_text())

        mcp_section = data.setdefault("mcp", {})
        full_command: list[str] = []
        if mcp.command is not None:
            full_command.append(mcp.command)
        full_command.extend(mcp.args)
        entry: dict = {
            "type": "local",
            "command": full_command,
            "environment": expanded_env,
            "enabled": True,
        }
        if mcp.url is not None:
            entry["url"] = mcp.url
        mcp_section[mcp.name] = entry
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
