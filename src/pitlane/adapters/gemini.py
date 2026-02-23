"""Gemini CLI adapter."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, TYPE_CHECKING

from pitlane.adapters.base import AdapterResult, BaseAdapter
from pitlane.adapters.streaming import run_streaming_sync

if TYPE_CHECKING:
    import logging


class GeminiAdapter(BaseAdapter):
    def cli_name(self) -> str:
        return "gemini"

    def agent_type(self) -> str:
        return "gemini-cli"

    def get_cli_version(self) -> str | None:
        try:
            import subprocess

            result = subprocess.run(
                ["gemini", "--version"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def _build_command(self, prompt: str, config: dict[str, Any]) -> list[str]:
        cmd = ["gemini", "--output-format", "stream-json", "--approval-mode", "yolo"]
        if model := config.get("model"):
            cmd.extend(["-m", model])
        cmd.append(prompt)
        return cmd

    def _parse_output(
        self, stdout: str
    ) -> tuple[list[dict], dict | None, float | None, int]:
        """Parse NDJSON stream-json events from gemini --output-format stream-json."""
        conversation: list[dict] = []
        total_input = 0
        total_output = 0
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

            if msg_type in ("assistant", "message", "content"):
                content = msg.get("content", msg.get("text", ""))
                if content:
                    conversation.append({"role": "assistant", "content": content})

            elif msg_type == "tool_call":
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

            elif msg_type in ("usage", "stats", "result"):
                usage = msg.get("usage", msg.get("tokenCount", {}))
                if isinstance(usage, dict):
                    inp = usage.get(
                        "input_tokens",
                        usage.get("inputTokens", usage.get("promptTokenCount", 0)),
                    )
                    out = usage.get(
                        "output_tokens",
                        usage.get("outputTokens", usage.get("candidatesTokenCount", 0)),
                    )
                    if inp or out:
                        total_input += int(inp or 0)
                        total_output += int(out or 0)
                if "cost" in msg:
                    cost = msg.get("cost")

        token_usage = None
        if total_input > 0 or total_output > 0:
            token_usage = {"input": total_input, "output": total_output}

        return conversation, token_usage, cost, tool_calls_count

    def install_mcp(self, workspace: Path, mcp: Any) -> None:
        """Write MCP server config into workspace/.gemini/settings.json."""
        from pitlane.workspace import _expand_env

        expanded_env = {k: _expand_env(v) for k, v in mcp.env.items()}
        config_dir = workspace / ".gemini"
        config_dir.mkdir(parents=True, exist_ok=True)
        target = config_dir / "settings.json"

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
