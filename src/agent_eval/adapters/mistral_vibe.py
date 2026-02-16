from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, TYPE_CHECKING

from agent_eval.adapters.base import AdapterResult, BaseAdapter
from agent_eval.adapters.streaming import run_command_with_streaming

if TYPE_CHECKING:
    import logging


class MistralVibeAdapter(BaseAdapter):
    def cli_name(self) -> str:
        return "vibe"

    def agent_type(self) -> str:
        return "mistral-vibe"

    def get_cli_version(self) -> str | None:
        try:
            import subprocess

            result = subprocess.run(
                ["vibe", "--version"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def _build_command(self, prompt: str, config: dict[str, Any]) -> list[str]:
        cmd = ["vibe", "-p", prompt, "--output", "json"]
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

    def _parse_output(self, stdout: str) -> list[dict]:
        """Parse JSON output from vibe --output json into conversation entries."""
        conversation: list[dict] = []

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return conversation

        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue

            role = item.get("role")
            if role == "assistant":
                entry: dict[str, Any] = {
                    "role": "assistant",
                    "content": item.get("content", ""),
                }
                if item.get("tool_calls"):
                    entry["tool_calls"] = item["tool_calls"]
                conversation.append(entry)

        return conversation

    def _read_session_stats(
        self,
        vibe_home: str,
        logger: logging.Logger,
    ) -> tuple[dict[str, int] | None, float | None, int]:
        """Read token usage, cost, and tool call count from vibe session meta.json.

        Vibe writes session metadata (including stats) to
        VIBE_HOME/logs/session/session_*/meta.json after each run.
        """
        token_usage = None
        cost = None
        tool_calls = 0

        session_dir = Path(vibe_home) / "logs" / "session"
        if not session_dir.exists():
            logger.debug("No vibe session log directory found")
            return token_usage, cost, tool_calls

        # Find the most recent session meta.json
        meta_files = sorted(session_dir.glob("session_*/meta.json"))
        if not meta_files:
            logger.debug("No vibe session meta.json found")
            return token_usage, cost, tool_calls

        meta_file = meta_files[-1]  # most recent
        try:
            meta = json.loads(meta_file.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(f"Failed to read vibe session meta: {e}")
            return token_usage, cost, tool_calls

        stats = meta.get("stats", {})
        if stats:
            prompt_tokens = stats.get("session_prompt_tokens", 0)
            completion_tokens = stats.get("session_completion_tokens", 0)
            if prompt_tokens or completion_tokens:
                token_usage = {
                    "input": prompt_tokens,
                    "output": completion_tokens,
                }
            cost = stats.get("session_cost")
            tool_calls = stats.get("tool_calls_agreed", 0)
            logger.debug(
                f"Vibe session stats: {prompt_tokens} input tokens, "
                f"{completion_tokens} output tokens, cost=${cost}, "
                f"{tool_calls} tool calls"
            )

        return token_usage, cost, tool_calls

    def run(
        self,
        prompt: str,
        workdir: Path,
        config: dict[str, Any],
        logger: logging.Logger,
    ) -> AdapterResult:
        self._generate_config(workdir, config)
        cmd = self._build_command(prompt, config)
        timeout = config.get("timeout", 300)

        logger.debug(f"Command: {' '.join(cmd)}")
        logger.debug(f"Working directory: {workdir}")
        logger.debug(f"Timeout: {timeout}s")

        vibe_home = tempfile.mkdtemp(prefix="vibe-home-")
        # Copy .env (API key) from the real ~/.vibe if it exists
        real_env = Path.home() / ".vibe" / ".env"
        if real_env.is_file():
            shutil.copy2(real_env, Path(vibe_home) / ".env")
        else:
            raise RuntimeError(
                "No ~/.vibe/.env found. Run 'vibe --setup' to configure your API key."
            )
        env = {**os.environ, "VIBE_HOME": vibe_home}

        start = time.monotonic()
        try:
            stdout, stderr, exit_code = asyncio.run(
                run_command_with_streaming(cmd, workdir, timeout, logger, env)
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
            )

        duration = time.monotonic() - start

        if logger:
            logger.debug(
                f"Command completed in {duration:.2f}s with exit code {exit_code}"
            )

        conversation = self._parse_output(stdout)
        token_usage, cost, tool_calls_count = self._read_session_stats(
            vibe_home, logger
        )
        return AdapterResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_seconds=duration,
            conversation=conversation,
            token_usage=token_usage,
            cost_usd=cost,
            tool_calls_count=tool_calls_count,
        )
