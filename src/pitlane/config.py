from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Literal

import yaml
from expandvars import expandvars
from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class AdapterType(str, Enum):
    BOB = "bob"
    CLAUDE_CODE = "claude-code"
    MISTRAL_VIBE = "mistral-vibe"
    OPENCODE = "opencode"


class ModelType(str, Enum):
    HAIKU = "haiku"
    SONNET = "sonnet"
    OPUS = "opus"
    DEVSTRAL_2 = "devstral-2"
    DEVSTRAL_SMALL = "devstral-small"


class SkillRef(BaseModel):
    source: str
    skill: str | None = None


class McpServerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    type: Literal["stdio", "sse", "http"] = "stdio"
    command: str | None = None
    args: list[str] = []
    url: str | None = None
    env: dict[str, str] = {}

    @model_validator(mode="after")
    def validate_env_variables(self) -> "McpServerConfig":
        """Validate that all ${VAR} references without defaults are set.

        Raises ValueError listing every missing variable so the user can fix them
        all at once rather than hitting them one-by-one mid-run.
        """
        missing: list[str] = []
        for key, value in self.env.items():
            try:
                expandvars(value, nounset=True)
            except Exception:
                # Variable is missing and has no default
                missing.append(f"  {key}={value}")

        if missing:
            details = "\n".join(missing)
            raise ValueError(
                f"MCP server '{self.name}' has missing environment variables:\n{details}"
            )

        return self


class AssistantConfig(BaseModel):
    adapter: AdapterType
    args: dict[str, Any] = {}
    skills: list[SkillRef] = []
    mcps: list[McpServerConfig] = []

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
    weight: float = 1.0


class FileContainsSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    pattern: str


class FileContainsAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_contains: FileContainsSpec
    weight: float = 1.0


class CommandSucceedsAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_succeeds: str
    weight: float = 1.0


class CommandFailsAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_fails: str
    weight: float = 1.0


class SimilaritySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actual: str
    expected: str
    metric: str | None = None
    min_score: float | None = None


class BleuAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bleu: SimilaritySpec
    weight: float = 1.0


class RougeAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rouge: SimilaritySpec
    weight: float = 1.0


class BERTScoreAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bertscore: SimilaritySpec
    weight: float = 1.0


class CosineSimilarityAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cosine_similarity: SimilaritySpec
    weight: float = 1.0


class CustomScriptSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    interpreter: str | None = None
    interpreter_args: list[str] = []
    script: str
    script_args: list[str] = []
    timeout: int = 60
    expected_exit_code: int = 0


class CustomScriptAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    custom_script: str | CustomScriptSpec


Assertion = (
    FileExistsAssertion
    | FileContainsAssertion
    | CommandSucceedsAssertion
    | CommandFailsAssertion
    | BleuAssertion
    | RougeAssertion
    | BERTScoreAssertion
    | CosineSimilarityAssertion
    | CustomScriptAssertion
)


class TaskConfig(BaseModel):
    name: str
    prompt: str
    workdir: str
    timeout: int = 300
    assertions: list[Assertion]

    @field_validator("assertions")
    @classmethod
    def assertions_must_not_be_empty(
        cls, v: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not v:
            raise ValueError("assertions must not be empty")
        return v


class EvalConfig(BaseModel):
    assistants: dict[str, AssistantConfig]
    tasks: list[TaskConfig]

    @field_validator("assistants")
    @classmethod
    def no_commas_in_assistant_names(cls, v: dict) -> dict:
        for name in v:
            if "," in name:
                raise ValueError(f"Assistant name '{name}' must not contain a comma")
        return v

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
