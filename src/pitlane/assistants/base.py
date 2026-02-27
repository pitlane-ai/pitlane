from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, TYPE_CHECKING
import subprocess
import threading

if TYPE_CHECKING:
    import logging
    from pitlane.config import McpServerConfig


class AssistantFeature(str, Enum):
    MCPS = "mcps"
    SKILLS = "skills"


@dataclass
class AssistantResult:
    stdout: str
    stderr: str
    exit_code: int
    duration_seconds: float
    conversation: list[dict[str, Any]] = field(default_factory=list)
    token_usage: dict[str, int] | None = None
    cost_usd: float | None = None
    tool_calls_count: int | None = None
    timed_out: bool = False


class BaseAssistant(ABC):
    @abstractmethod
    def run(
        self,
        prompt: str,
        workdir: Path,
        config: dict[str, Any],
        logger: logging.Logger,
    ) -> AssistantResult:
        """Execute the agent with the given prompt in workdir."""
        ...

    @abstractmethod
    def cli_name(self) -> str:
        """The CLI command name for this agent."""
        ...

    @abstractmethod
    def agent_type(self) -> str:
        """Identifier for this agent type."""
        ...

    @abstractmethod
    def get_cli_version(self) -> str | None:
        """Get the version of the CLI tool this assistant uses."""
        ...

    @abstractmethod
    def install_mcp(self, workspace: Path, mcp: McpServerConfig) -> None:
        """Write MCP server config into the workspace for this agent."""
        ...

    @abstractmethod
    def supported_features(self) -> frozenset[AssistantFeature]:
        """Features this assistant supports."""
        ...

    def skills_dir(self) -> str | None:
        """Relative path where this agent discovers skills, or None if unsupported."""
        return None


def run_command_with_live_logging(
    cmd: list[str],
    workdir: Path,
    timeout: int,
    logger: logging.Logger,
    env: dict[str, str] | None = None,
) -> tuple[str, str, int, bool]:

    # Popen rather than run here as we want to call logger.debug while assistant is run (--verbose mode)
    proc = subprocess.Popen(
        cmd,
        cwd=workdir,
        stdin=subprocess.DEVNULL,  # may force detached mode (but note that we do not rely on this specifically - arguments should be passed to assistant CLIs)
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    def _read(stream, lines: list[str], prefix: str) -> None:
        for line in stream:
            lines.append(line)
            logger.debug("[%s] %s", prefix, line.rstrip())

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    t_out = threading.Thread(target=_read, args=(proc.stdout, stdout_lines, "stdout"))
    t_err = threading.Thread(target=_read, args=(proc.stderr, stderr_lines, "stderr"))
    t_out.start()
    t_err.start()

    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.kill()
        proc.wait()

    t_out.join()
    t_err.join()

    return "".join(stdout_lines), "".join(stderr_lines), proc.returncode, timed_out
