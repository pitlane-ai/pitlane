"""Base adapter interface and AdapterResult dataclass."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    import logging


@dataclass
class AdapterResult:
    """Captures the result of running an agent adapter."""

    stdout: str
    stderr: str
    exit_code: int
    duration_seconds: float
    conversation: list[dict[str, Any]] = field(default_factory=list)
    token_usage: dict[str, int] | None = None
    cost_usd: float | None = None
    tool_calls_count: int | None = None


class BaseAdapter(ABC):
    """Abstract base class that all agent adapters must implement."""

    @abstractmethod
    def run(
        self,
        prompt: str,
        workdir: Path,
        config: dict[str, Any],
        logger: logging.Logger,
    ) -> AdapterResult:
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
        """Get the version of the CLI tool this adapter uses."""
        ...