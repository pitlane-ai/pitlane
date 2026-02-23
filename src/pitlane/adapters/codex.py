"""Codex CLI adapter."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, TYPE_CHECKING

from pitlane.adapters.base import AdapterResult, BaseAdapter
from pitlane.adapters.streaming import run_streaming_sync

if TYPE_CHECKING:
    import logging


class CodexAdapter(BaseAdapter):
    def cli_name(self) -> str:
        return "codex"

    def agent_type(self) -> str:
        return "codex"

    def get_cli_version(self) -> str | None:
        try:
            import subprocess

            result = subprocess.run(
                ["codex", "--version"], capture_output=True, text=True, timeout=5
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
        cmd = ["codex", "exec", "--json", "--full-auto"]
        if workdir is not None:
            cmd.extend(["-C", str(workdir.resolve())])
        if model := config.get("model"):
            cmd.extend(["-m", model])
        cmd.append(prompt)
        return cmd

    def _parse_output(
        self, stdout: str
    ) -> tuple[list[dict], dict | None, float | None, int]:
        """Parse JSONL events from codex --json output."""
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

            if msg_type == "message":
                role = msg.get("role")
                if role == "assistant":
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text = block.get("text", "")
                                if text:
                                    conversation.append(
                                        {"role": "assistant", "content": text}
                                    )
                    elif isinstance(content, str) and content:
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

            elif msg_type in ("usage", "cost"):
                usage = msg.get("usage", {})
                if usage:
                    token_usage = {
                        "input": usage.get(
                            "input_tokens", usage.get("prompt_tokens", 0)
                        ),
                        "output": usage.get(
                            "output_tokens", usage.get("completion_tokens", 0)
                        ),
                    }
                if "cost" in msg:
                    cost = msg.get("cost")

        return conversation, token_usage, cost, tool_calls_count

    def install_mcp(self, workspace: Path, mcp: Any) -> None:
        """Write MCP server config into workspace/.codex/config.toml."""
        from pitlane.workspace import _expand_env

        expanded_env = {k: _expand_env(v) for k, v in mcp.env.items()}
        config_dir = workspace / ".codex"
        config_dir.mkdir(parents=True, exist_ok=True)
        target = config_dir / "config.toml"

        lines: list[str] = []
        if target.exists():
            lines = target.read_text().splitlines()

        lines.append("")
        lines.append(f"[mcp_servers.{mcp.name}]")
        if mcp.command is not None:
            lines.append(f'command = "{mcp.command}"')
        if mcp.args:
            args_toml = "[" + ", ".join(f'"{a}"' for a in mcp.args) + "]"
            lines.append(f"args = {args_toml}")
        if mcp.url is not None:
            lines.append(f'url = "{mcp.url}"')
        if expanded_env:
            env_pairs = ", ".join(f'{k} = "{v}"' for k, v in expanded_env.items())
            lines.append(f"env = {{ {env_pairs} }}")

        target.write_text("\n".join(lines) + "\n")

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
