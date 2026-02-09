"""OpenCode (opencode.ai) adapter."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from agent_eval.adapters.base import AdapterResult, BaseAdapter


class OpenCodeAdapter(BaseAdapter):

    def cli_name(self) -> str:
        return "opencode"

    def agent_type(self) -> str:
        return "opencode"

    def _build_command(self, prompt: str, config: dict[str, Any]) -> list[str]:
        cmd = ["opencode", "run", "--format", "json"]
        if model := config.get("model"):
            cmd.extend(["--model", model])
        if agent := config.get("agent"):
            cmd.extend(["--agent", agent])
        if files := config.get("files"):
            for f in files:
                cmd.extend(["--file", f])
        cmd.append(prompt)
        return cmd

    def _parse_output(self, stdout: str) -> tuple[list[dict], dict | None, float | None]:
        """Parse JSON events from opencode run --format json."""
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

            msg_type = msg.get("type", "")

            if msg_type in ("assistant", "assistant_message", "message"):
                content = msg.get("content", msg.get("text", ""))
                if content:
                    conversation.append({
                        "role": "assistant",
                        "content": content,
                    })

            if msg_type == "tool_use":
                conversation.append({
                    "role": "assistant",
                    "content": "",
                    "tool_use": {
                        "name": msg.get("name", ""),
                        "input": msg.get("input", {}),
                    },
                })

            if msg_type in ("result", "summary"):
                usage = msg.get("usage", msg.get("token_usage", {}))
                if usage:
                    token_usage = {
                        "input": usage.get("input_tokens", usage.get("input", 0)),
                        "output": usage.get("output_tokens", usage.get("output", 0)),
                    }
                cost = msg.get("total_cost_usd") or msg.get("cost")

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
                stdout=e.stdout or "", stderr=e.stderr or "",
                exit_code=-1, duration_seconds=duration,
            )
        duration = time.monotonic() - start
        conversation, token_usage, cost = self._parse_output(proc.stdout)
        return AdapterResult(
            stdout=proc.stdout, stderr=proc.stderr,
            exit_code=proc.returncode, duration_seconds=duration,
            conversation=conversation, token_usage=token_usage, cost_usd=cost,
        )
