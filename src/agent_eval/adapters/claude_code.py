"""Claude Code adapter."""

from __future__ import annotations

import asyncio
import json
import subprocess
import time
from pathlib import Path
from typing import Any, TYPE_CHECKING

from agent_eval.adapters.base import AdapterResult, BaseAdapter

if TYPE_CHECKING:
    import logging


class ClaudeCodeAdapter(BaseAdapter):

    def cli_name(self) -> str:
        return "claude"

    def agent_type(self) -> str:
        return "claude-code"

    def _build_command(self, prompt: str, config: dict[str, Any]) -> list[str]:
        cmd = [
            "claude", "-p",
            "--output-format", "stream-json",
            "--verbose",
            "--dangerously-skip-permissions",
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

    def _parse_output(self, stdout: str) -> tuple[list[dict], dict | None, float | None]:
        """Parse stream-json NDJSON output into conversation, token_usage, cost."""
        conversation: list[dict] = []
        token_usage = None
        cost = None

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
                        conversation.append({
                            "role": "assistant",
                            "content": block["text"],
                        })
                    elif block.get("type") == "tool_use":
                        conversation.append({
                            "role": "assistant",
                            "content": "",
                            "tool_use": {
                                "name": block.get("name", ""),
                                "input": block.get("input", {}),
                            },
                        })
            elif msg_type == "result":
                usage = msg.get("usage", {})
                if usage:
                    token_usage = {
                        "input": usage.get("input_tokens", 0),
                        "output": usage.get("output_tokens", 0),
                    }
                cost = msg.get("total_cost_usd")

        return conversation, token_usage, cost

    async def _run_with_streaming(
        self,
        cmd: list[str],
        workdir: Path,
        timeout: int,
        logger: logging.Logger | None,
    ) -> tuple[str, str, int]:
        """Run command with optional real-time output streaming using asyncio."""
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=workdir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout_lines = []
        stderr_lines = []

        async def read_stream(stream, lines, prefix):
            """Read stream line by line and optionally log."""
            while True:
                line = await stream.readline()
                if not line:
                    break
                line_str = line.decode('utf-8')
                lines.append(line_str)
                if logger:
                    logger.debug(f"[{prefix}] {line_str.rstrip()}")

        # Read both streams concurrently
        try:
            await asyncio.wait_for(
                asyncio.gather(
                    read_stream(proc.stdout, stdout_lines, "stdout"),
                    read_stream(proc.stderr, stderr_lines, "stderr"),
                    proc.wait(),
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise subprocess.TimeoutExpired(cmd, timeout)

        stdout = ''.join(stdout_lines)
        stderr = ''.join(stderr_lines)
        return stdout, stderr, proc.returncode

    def run(
        self,
        prompt: str,
        workdir: Path,
        config: dict[str, Any],
        logger: logging.Logger | None = None,
    ) -> AdapterResult:
        cmd = self._build_command(prompt, config)
        timeout = config.get("timeout", 300)

        # Log command context if verbose
        if logger:
            logger.debug(f"Command: {' '.join(cmd)}")
            logger.debug(f"Working directory: {workdir}")
            logger.debug(f"Timeout: {timeout}s")
            logger.debug(f"Config: {json.dumps(config, indent=2)}")

        start = time.monotonic()

        try:
            stdout, stderr, exit_code = asyncio.run(
                self._run_with_streaming(cmd, workdir, timeout, logger)
            )

        except subprocess.TimeoutExpired as e:
            duration = time.monotonic() - start
            if logger:
                logger.debug(f"Command timed out after {duration:.2f}s")
            return AdapterResult(
                stdout=e.stdout or "",
                stderr=e.stderr or "",
                exit_code=-1,
                duration_seconds=duration,
                conversation=[],
                token_usage=None,
                cost_usd=None,
            )

        duration = time.monotonic() - start

        if logger:
            logger.debug(f"Command completed in {duration:.2f}s with exit code {exit_code}")

        conversation, token_usage, cost = self._parse_output(stdout)
        return AdapterResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_seconds=duration,
            conversation=conversation,
            token_usage=token_usage,
            cost_usd=cost,
        )