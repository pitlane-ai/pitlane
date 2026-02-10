"""Cline CLI adapter."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, TYPE_CHECKING

from agent_eval.adapters.base import AdapterResult, BaseAdapter
from agent_eval.adapters.streaming import run_command_with_streaming

if TYPE_CHECKING:
    import logging


class ClineAdapter(BaseAdapter):

    def cli_name(self) -> str:
        return "cline"

    def agent_type(self) -> str:
        return "cline"

    def _build_command(self, prompt: str, config: dict[str, Any]) -> list[str]:
        cmd = ["cline", "-y", "--json"]
        if timeout := config.get("timeout"):
            cmd.extend(["--timeout", str(timeout)])
        cmd.append(prompt)
        return cmd

    def _parse_output(self, stdout: str) -> tuple[list[dict], dict | None, float | None, int]:
        """Parse JSON output from cline --json."""
        conversation: list[dict] = []
        token_usage = None
        cost = None
        tool_calls_count = 0

        # Cline --json emits newline-delimited JSON events
        for line in stdout.strip().splitlines():
            if not line.strip():
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")

            if msg_type in ("assistant", "assistant_message"):
                content = msg.get("content", msg.get("text", ""))
                if content:
                    conversation.append({
                        "role": "assistant",
                        "content": content,
                    })

            if msg_type == "tool_use":
                tool_calls_count += 1
                conversation.append({
                    "role": "assistant",
                    "content": "",
                    "tool_use": {
                        "name": msg.get("name", ""),
                        "input": msg.get("input", {}),
                    },
                })

            if msg_type == "result":
                usage = msg.get("usage", {})
                if usage:
                    token_usage = {
                        "input": usage.get("input_tokens", 0),
                        "output": usage.get("output_tokens", 0),
                    }
                cost = msg.get("total_cost_usd") or msg.get("cost")

        return conversation, token_usage, cost, tool_calls_count

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
            stdout, stderr, exit_code = asyncio.run(
                run_command_with_streaming(cmd, workdir, timeout, logger)
            )
        except Exception as e:
            duration = time.monotonic() - start
            if logger:
                logger.debug(f"Command failed after {duration:.2f}s: {e}")
            return AdapterResult(
                stdout="", stderr=str(e),
                exit_code=-1, duration_seconds=duration,
            )

        duration = time.monotonic() - start

        if logger:
            logger.debug(f"Command completed in {duration:.2f}s with exit code {exit_code}")

        conversation, token_usage, cost, tool_calls_count = self._parse_output(stdout)
        return AdapterResult(
            stdout=stdout, stderr=stderr,
            exit_code=exit_code, duration_seconds=duration,
            conversation=conversation, token_usage=token_usage, cost_usd=cost,
            tool_calls_count=tool_calls_count,
        )