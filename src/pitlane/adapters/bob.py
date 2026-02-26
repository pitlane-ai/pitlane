"""Bob (Bob-Shell) adapter."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, TYPE_CHECKING

from expandvars import expandvars

from pitlane.adapters.base import (
    AdapterFeature,
    AdapterResult,
    BaseAdapter,
    run_command_with_live_logging,
)

if TYPE_CHECKING:
    import logging


class BobAdapter(BaseAdapter):
    def cli_name(self) -> str:
        return "bob"

    def agent_type(self) -> str:
        return "bob"

    def get_cli_version(self) -> str | None:
        import subprocess

        try:
            result = subprocess.run(
                ["bob", "--version"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def supported_features(self) -> frozenset[AdapterFeature]:
        return frozenset({AdapterFeature.MCPS})

    def install_mcp(self, workspace: Path, mcp: Any) -> None:
        # Resolve ${VAR} references from the user's YAML config
        env = {k: expandvars(v, nounset=True) for k, v in mcp.env.items()}
        bob_dir = workspace / ".bob"
        bob_dir.mkdir(exist_ok=True)
        target = bob_dir / "mcp.json"
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
        if env:
            entry["env"] = env
        servers[mcp.name] = entry
        target.write_text(json.dumps(data, indent=2))

    def _build_command(self, prompt: str, config: dict[str, Any]) -> list[str]:
        cmd = [
            "bob",
            "--output-format",
            "stream-json",
            "--yolo",
        ]
        if chat_mode := config.get("chat_mode"):
            cmd.extend(["--chat-mode", chat_mode])
        if max_coins := config.get("max_coins"):
            cmd.extend(["--max-coins", str(max_coins)])
        cmd.append(prompt)
        return cmd

    def _parse_output(
        self, stdout: str
    ) -> tuple[list[dict], dict | None, float | None, int]:
        """Parse stream-json (NDJSON) output from bob CLI.

        Each line is either a JSON event object or non-JSON console output.
        Non-JSON lines are silently skipped.
        """
        conversation: list[dict] = []
        token_usage = None
        cost = None
        tool_calls_count = 0

        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type")

            if event_type == "tool_use":
                tool_name = event.get("tool_name")
                if tool_name == "attempt_completion":
                    result_text = event.get("parameters", {}).get("result", "").strip()
                    if result_text:
                        conversation.append(
                            {"role": "assistant", "content": result_text}
                        )
                else:
                    tool_calls_count += 1
                    conversation.append(
                        {
                            "role": "assistant",
                            "content": "",
                            "tool_use": {
                                "name": tool_name,
                                "input": event.get("parameters", {}),
                            },
                        }
                    )

            elif event_type == "message":
                content = event.get("content", "")
                if "Cost:" in content:
                    m = re.search(r"Cost:\s*([\d.]+)", content)
                    if m:
                        cost = float(m.group(1))

            elif event_type == "result":
                stats = event.get("stats", {})
                input_tokens = stats.get("input_tokens", 0)
                output_tokens = stats.get("output_tokens", 0)
                if input_tokens > 0 or output_tokens > 0:
                    token_usage = {"input": input_tokens, "output": output_tokens}

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
        logger.debug(f"Config: {json.dumps(config, indent=2)}")

        start = time.monotonic()

        try:
            stdout, stderr, exit_code, timed_out = run_command_with_live_logging(
                cmd, workdir, timeout, logger
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
                conversation=[],
                token_usage=None,
                cost_usd=None,
            )

        duration = time.monotonic() - start

        if logger:
            logger.debug(
                f"Command completed in {duration:.2f}s with exit code {exit_code}"
            )

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
