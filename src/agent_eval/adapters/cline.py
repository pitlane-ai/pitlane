"""Cline CLI adapter."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from agent_eval.adapters.base import AdapterResult, BaseAdapter


class ClineAdapter(BaseAdapter):

    def cli_name(self) -> str:
        return "cline"

    def agent_type(self) -> str:
        return "cline"

    def skills_dir_name(self) -> str:
        return ".cline"

    def _build_command(self, prompt: str, config: dict[str, Any]) -> list[str]:
        cmd = ["cline", "-y", "--json"]
        if timeout := config.get("timeout"):
            cmd.extend(["--timeout", str(timeout)])
        cmd.append(prompt)
        return cmd

    def _parse_output(self, stdout: str) -> tuple[list[dict], dict | None, float | None]:
        """Parse JSON output from cline --json."""
        conversation: list[dict] = []
        token_usage = None
        cost = None

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
