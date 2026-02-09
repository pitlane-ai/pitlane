from __future__ import annotations

import asyncio
import json
import tempfile
import time
from pathlib import Path
from typing import Any, TYPE_CHECKING

from agent_eval.adapters.base import AdapterResult, BaseAdapter
from agent_eval.adapters.streaming import run_command_with_streaming

if TYPE_CHECKING:
    import logging


class CodexAdapter(BaseAdapter):

    def cli_name(self) -> str:
        return "codex"

    def agent_type(self) -> str:
        return "codex"

    def _build_command(self, prompt: str, config: dict[str, Any]) -> list[str]:
        cmd = ["codex", "exec", "--json"]
        if model := config.get("model"):
            cmd.extend(["-m", model])
        sandbox = config.get("sandbox", "workspace-write")
        cmd.extend(["-s", sandbox])
        approval = config.get("approval", "never")
        cmd.extend(["-a", approval])
        cmd.append(prompt)
        return cmd

    def _generate_config(self, workdir: Path, config: dict[str, Any]) -> None:
        """Generate .codex/config.toml in the workspace if needed."""
        sections = []

        if mcp_servers := config.get("mcp_servers"):
            for name, server_config in mcp_servers.items():
                section = f'[mcp_servers."{name}"]\n'
                for key, value in server_config.items():
                    if isinstance(value, str):
                        section += f'{key} = "{value}"\n'
                    elif isinstance(value, list):
                        items = ", ".join(f'"{v}"' for v in value)
                        section += f"{key} = [{items}]\n"
                    else:
                        section += f"{key} = {value}\n"
                sections.append(section)

        if model_instructions := config.get("model_instructions_file"):
            sections.append(f'model_instructions_file = "{model_instructions}"\n')

        if sections:
            config_dir = workdir / ".codex"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "config.toml").write_text("\n".join(sections))

    def _parse_output(self, stdout: str) -> tuple[list[dict], dict | None, float | None]:
        """Parse JSONL output from codex exec --json."""
        conversation: list[dict] = []
        token_usage = None

        for line in stdout.strip().splitlines():
            if not line.strip():
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")

            if msg_type == "turn.completed":
                usage = msg.get("usage", {})
                if usage:
                    prev_input = token_usage["input"] if token_usage else 0
                    prev_output = token_usage["output"] if token_usage else 0
                    token_usage = {
                        "input": prev_input + usage.get("input_tokens", 0),
                        "output": prev_output + usage.get("output_tokens", 0),
                    }

            if msg_type in ("agent_message", "assistant_message"):
                conversation.append({
                    "role": "assistant",
                    "content": msg.get("content", ""),
                })

        return conversation, token_usage, None  # Codex doesn't report cost

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

        codex_home = tempfile.mkdtemp(prefix="codex-home-")

        import os
        env = {**os.environ, "CODEX_HOME": codex_home}

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
                stdout="", stderr=str(e),
                exit_code=-1, duration_seconds=duration,
            )
        
        duration = time.monotonic() - start
        
        if logger:
            logger.debug(f"Command completed in {duration:.2f}s with exit code {exit_code}")
        
        conversation, token_usage, cost = self._parse_output(stdout)
        return AdapterResult(
            stdout=stdout, stderr=stderr,
            exit_code=exit_code, duration_seconds=duration,
            conversation=conversation, token_usage=token_usage, cost_usd=cost,
        )