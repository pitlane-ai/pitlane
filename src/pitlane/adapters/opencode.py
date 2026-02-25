"""OpenCode (opencode.ai) adapter."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, TYPE_CHECKING

from expandvars import expandvars

from pitlane.adapters.base import (
    AdapterResult,
    BaseAdapter,
    run_command_with_live_logging,
)

if TYPE_CHECKING:
    import logging


class OpenCodeAdapter(BaseAdapter):
    def cli_name(self) -> str:
        return "opencode"

    def agent_type(self) -> str:
        return "opencode"

    def get_cli_version(self) -> str | None:
        try:
            import subprocess

            result = subprocess.run(
                ["opencode", "--version"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def supported_features(self) -> frozenset[str]:
        return frozenset({"mcps", "skills"})

    def skills_dir(self) -> str | None:
        return ".agents/skills"

    def install_mcp(self, workspace: Path, mcp: Any) -> None:
        # Resolve ${VAR} references from the user's YAML config
        env = {k: expandvars(v, nounset=True) for k, v in mcp.env.items()}
        target = workspace / "opencode.json"
        data: dict = {}
        if target.exists():
            data = json.loads(target.read_text())
        mcp_section = data.setdefault("mcp", {})
        full_command: list[str] = []
        if mcp.command is not None:
            full_command.append(mcp.command)
        full_command.extend(mcp.args)
        entry: dict = {
            "type": "local",
            "command": full_command,
            "environment": env,
            "enabled": True,
        }
        if mcp.url is not None:
            entry["url"] = mcp.url
        mcp_section[mcp.name] = entry
        target.write_text(json.dumps(data, indent=2))

    def _build_command(self, prompt: str, config: dict[str, Any]) -> list[str]:
        cmd = ["opencode", "run", "--format", "json"]

        if model := config.get("model"):
            cmd.extend(["--model", model])
        if agent := config.get("agent"):
            cmd.extend(["--agent", agent])

        if files := config.get("files"):
            for f in files:
                cmd.extend(["--file", f])

        if session_id := config.get("session"):
            cmd.extend(["--session", session_id])
        if config.get("continue", False):
            cmd.append("--continue")
        if config.get("fork", False):
            cmd.append("--fork")

        if title := config.get("title"):
            cmd.extend(["--title", title])
        if config.get("share", False):
            cmd.append("--share")

        if attach_url := config.get("attach"):
            cmd.extend(["--attach", attach_url])
        if port := config.get("port"):
            cmd.extend(["--port", str(port)])

        cmd.append(prompt)
        return cmd

    def _parse_output(
        self, stdout: str
    ) -> tuple[list[dict], dict | None, float | None, int]:
        """Parse JSON events from opencode run --format json."""
        conversation: list[dict] = []
        total_input_tokens = 0
        total_output_tokens = 0
        total_cost = 0.0
        tool_calls_count = 0

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
                    conversation.append(
                        {
                            "role": "assistant",
                            "content": content,
                        }
                    )

            if msg_type == "tool_use":
                # Real opencode format: name in part.tool
                # Fallback: legacy format with top-level name
                part = msg.get("part", {})
                tool_name = msg.get("name") or part.get("tool", "")
                tool_input = msg.get("input") or part.get("state", {}).get("input", {})
                if tool_name:
                    tool_calls_count += 1
                    conversation.append(
                        {
                            "role": "assistant",
                            "content": "",
                            "tool_use": {
                                "name": tool_name,
                                "input": tool_input,
                            },
                        }
                    )

            if msg_type == "text":
                content = msg.get("part", {}).get("text", "")
                if content:
                    conversation.append({"role": "assistant", "content": content})

            # OpenCode provides tokens in step_finish events
            if msg_type == "step_finish":
                part = msg.get("part", {})
                tokens = part.get("tokens", {})
                if tokens:
                    total_input_tokens += tokens.get("input", 0)
                    total_output_tokens += tokens.get("output", 0)
                step_cost = part.get("cost", 0)
                if step_cost:
                    total_cost += step_cost

        token_usage = None
        if total_input_tokens > 0 or total_output_tokens > 0:
            token_usage = {
                "input": total_input_tokens,
                "output": total_output_tokens,
            }

        cost = total_cost if total_cost > 0 else None

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
            )

        duration = time.monotonic() - start

        if logger:
            logger.debug(
                f"Command completed in {duration:.2f}s with exit code {exit_code}"
            )

        conversation, token_usage, cost, tool_calls_count = self._parse_output(stdout)

        if logger:
            logger.debug(f"Parsed token_usage: {token_usage}")
            logger.debug(f"Parsed cost: {cost}")
            logger.debug(f"Parsed tool_calls_count: {tool_calls_count}")

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
