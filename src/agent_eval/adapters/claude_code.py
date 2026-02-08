"""Claude Code adapter stub."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_eval.adapters.base import AdapterResult, BaseAdapter


class ClaudeCodeAdapter(BaseAdapter):
    def run(self, prompt: str, workdir: Path, config: dict[str, Any]) -> AdapterResult:
        raise NotImplementedError("ClaudeCodeAdapter.run is not yet implemented")

    def cli_name(self) -> str:
        return "claude"

    def agent_type(self) -> str:
        return "claude-code"

    def skills_dir_name(self) -> str:
        return ".claude"
