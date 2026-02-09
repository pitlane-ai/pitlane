"""Claude Code adapter."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from agent_eval.adapters.base import AdapterResult, BaseAdapter


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

    def run(self, prompt: str, workdir: Path, config: dict[str, Any]) -> AdapterResult:
        cmd = self._build_command(prompt, config)
        start = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=config.get("timeout", 300),
            )
        except subprocess.TimeoutExpired as e:
            duration = time.monotonic() - start
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
        conversation, token_usage, cost = self._parse_output(proc.stdout)
        return AdapterResult(
            stdout=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
            duration_seconds=duration,
            conversation=conversation,
            token_usage=token_usage,
            cost_usd=cost,
        )
