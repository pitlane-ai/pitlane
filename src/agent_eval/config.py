"""Eval config loading and validation using Pydantic."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

VALID_ADAPTERS = {"claude-code", "cline", "codex", "mistral-vibe", "opencode"}


class SkillRef(BaseModel):
    source: str
    skill: str | None = None


class AssistantConfig(BaseModel):
    adapter: str
    args: dict[str, Any] = {}
    skills: list[SkillRef] = []

    @field_validator("skills", mode="before")
    @classmethod
    def normalize_skills(cls, v: list) -> list:
        result = []
        for item in v:
            if isinstance(item, str):
                result.append(SkillRef(source=item))
            elif isinstance(item, dict):
                result.append(SkillRef(**item))
            else:
                result.append(item)
        return result

    @field_validator("adapter")
    @classmethod
    def adapter_must_be_valid(cls, v: str) -> str:
        if v not in VALID_ADAPTERS:
            raise ValueError(f"adapter must be one of {VALID_ADAPTERS}, got {v!r}")
        return v


class FileExistsAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_exists: str


class FileContainsSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    pattern: str


class FileContainsAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_contains: FileContainsSpec


class CommandSucceedsAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_succeeds: str


class CommandFailsAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_fails: str


class SimilaritySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actual: str
    expected: str
    metric: str | None = None
    min_score: float | None = None


class BleuAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bleu: SimilaritySpec


class RougeAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rouge: SimilaritySpec


class BERTScoreAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bertscore: SimilaritySpec


class CosineSimilarityAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cosine_similarity: SimilaritySpec


Assertion = (
    FileExistsAssertion
    | FileContainsAssertion
    | CommandSucceedsAssertion
    | CommandFailsAssertion
    | BleuAssertion
    | RougeAssertion
    | BERTScoreAssertion
    | CosineSimilarityAssertion
)


class TaskConfig(BaseModel):
    name: str
    prompt: str
    workdir: str
    timeout: int = 300
    assertions: list[Assertion]

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
