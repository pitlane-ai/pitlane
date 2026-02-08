"""Eval config loading and validation using Pydantic."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, field_validator, model_validator

VALID_ADAPTERS = {"claude-code", "codex", "mistral-vibe"}


class AssistantConfig(BaseModel):
    adapter: str
    args: dict[str, Any] = {}
    skills: list[str] = []

    @field_validator("adapter")
    @classmethod
    def adapter_must_be_valid(cls, v: str) -> str:
        if v not in VALID_ADAPTERS:
            raise ValueError(f"adapter must be one of {VALID_ADAPTERS}, got {v!r}")
        return v


class TaskConfig(BaseModel):
    name: str
    prompt: str
    workdir: str
    timeout: int = 300
    assertions: list[dict[str, Any]]

    @field_validator("assertions")
    @classmethod
    def assertions_must_not_be_empty(cls, v: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not v:
            raise ValueError("assertions must not be empty")
        return v


class EvalConfig(BaseModel):
    assistants: dict[str, AssistantConfig]
    tasks: list[TaskConfig]

    @model_validator(mode="after")
    def collections_must_not_be_empty(self) -> EvalConfig:
        if not self.assistants:
            raise ValueError("assistants must not be empty")
        if not self.tasks:
            raise ValueError("tasks must not be empty")
        return self


def load_config(path: Path) -> EvalConfig:
    """Load and validate an eval config from a YAML file."""
    with open(path) as f:
        raw = yaml.safe_load(f)
    return EvalConfig(**raw)
