"""Mistral Vibe adapter stub."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_eval.adapters.base import AdapterResult, BaseAdapter


class MistralVibeAdapter(BaseAdapter):
    def run(self, prompt: str, workdir: Path, config: dict[str, Any]) -> AdapterResult:
        raise NotImplementedError("MistralVibeAdapter.run is not yet implemented")

    def cli_name(self) -> str:
        return "vibe"

    def agent_type(self) -> str:
        return "mistral-vibe"

    def skills_dir_name(self) -> str:
        return ".vibe"
