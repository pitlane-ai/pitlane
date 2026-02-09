from __future__ import annotations

import json
import subprocess
import tempfile
import time
import os
from pathlib import Path
from typing import Any

from agent_eval.adapters.base import AdapterResult, BaseAdapter


class MistralVibeAdapter(BaseAdapter):

    def cli_name(self) -> str:
        return "vibe"

    def agent_type(self) -> str:
        return "mistral-vibe"

    def skills_dir_name(self) -> str:
        return ".vibe"

    def _build_command(self, prompt: str, config: dict[str, Any]) -> list[str]:
        cmd = ["vibe", "--prompt", prompt, "--output", "json"]
        if max_turns := config.get("max_turns"):
            cmd.extend(["--max-turns", str(max_turns)])
        if max_price := config.get("max_price"):
            cmd.extend(["--max-price", str(max_price)])
        return cmd

    def _generate_config(self, workdir: Path, config: dict[str, Any]) -> None:
        """Generate .vibe/config.toml in the workspace."""
        lines = []

        if model := config.get("model"):
            lines.append(f'active_model = "{model}"')

        if mcp_servers := config.get("mcp_servers"):
            for server in mcp_servers:
                lines.append("")
                lines.append("[[mcp_servers]]")
                for key, value in server.items():
                    if isinstance(value, str):
                        lines.append(f'{key} = "{value}"')
                    else:
                        lines.append(f"{key} = {value}")

        if lines:
            config_dir = workdir / ".vibe"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "config.toml").write_text("\n".join(lines) + "\n")

    def _parse_output(self, stdout: str) -> tuple[list[dict], dict | None, float | None]:
        """Parse JSON output from vibe --output json."""
        conversation: list[dict] = []
        token_usage = None
        cost = None

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return conversation, token_usage, cost

        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue

            if item.get("role") == "assistant":
                conversation.append({
                    "role": "assistant",
                    "content": item.get("content", ""),
                })

            if item.get("type") == "result":
                usage = item.get("usage", {})
                if usage:
                    token_usage = {
                        "input": usage.get("prompt_tokens", 0),
                        "output": usage.get("completion_tokens", 0),
                    }
                cost = item.get("total_cost_usd")

        return conversation, token_usage, cost

    def run(self, prompt: str, workdir: Path, config: dict[str, Any]) -> AdapterResult:
        self._generate_config(workdir, config)
        cmd = self._build_command(prompt, config)

        vibe_home = tempfile.mkdtemp(prefix="vibe-home-")

        start = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=config.get("timeout", 300),
                env={**os.environ, "VIBE_HOME": vibe_home},
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
