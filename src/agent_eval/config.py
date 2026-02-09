"""Eval config loading and validation using Pydantic."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class AdapterType(str, Enum):
    CLAUDE_CODE = "claude-code"
    CLINE = "cline"
    CODEX = "codex"
    MISTRAL_VIBE = "mistral-vibe"
    OPENCODE = "opencode"


class SkillRef(BaseModel):
    source: str
    skill: str | None = None


class AssistantConfig(BaseModel):
    adapter: AdapterType
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
    config_dir = path.parent.resolve()
    
    with open(path) as f:
        raw = yaml.safe_load(f)
    
    config = EvalConfig(**raw)
    
    # Resolve relative workdir paths relative to config file location
    for task in config.tasks:
        workdir_path = Path(task.workdir)
        if not workdir_path.is_absolute():
            task.workdir = str((config_dir / workdir_path).resolve())
    
    return config
