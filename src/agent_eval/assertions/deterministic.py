"""Deterministic assertion checks (file existence, content, commands)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from agent_eval.assertions.base import AssertionResult

_SIMILARITY_TYPES = frozenset({"bleu", "rouge", "bertscore", "cosine_similarity"})


def check_file_exists(workdir: str | Path, filename: str) -> AssertionResult:
    """Check that a file exists in the working directory."""
    path = Path(workdir) / filename
    passed = path.exists()
    return AssertionResult(
        name=f"file_exists:{filename}",
        passed=passed,
        message=f"{filename} exists" if passed else f"{filename} does not exist",
        score=1.0 if passed else 0.0,
    )


def check_file_contains(
    workdir: str | Path, filename: str, pattern: str
) -> AssertionResult:
    """Check that a file contains text matching a regex pattern."""
    path = Path(workdir) / filename
    if not path.exists():
        return AssertionResult(
            name=f"file_contains:{filename}",
            passed=False,
            message=f"{filename} not found",
            score=0.0,
        )
    content = path.read_text()
    if re.search(pattern, content):
        return AssertionResult(
            name=f"file_contains:{filename}",
            passed=True,
            message=f"{filename} matches pattern '{pattern}'",
            score=1.0,
        )
    return AssertionResult(
        name=f"file_contains:{filename}",
        passed=False,
        message=f"{filename} does not match pattern '{pattern}'",
        score=0.0,
    )


def check_command_succeeds(workdir: str | Path, command: str) -> AssertionResult:
    """Check that a shell command exits with code 0."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=workdir,
            timeout=60,
            capture_output=True,
            check=False,
        )
        passed = result.returncode == 0
        return AssertionResult(
            name=f"command_succeeds:{command}",
            passed=passed,
            message=f"exit code {result.returncode}",
            score=1.0 if passed else 0.0,
        )
    except subprocess.TimeoutExpired:
        return AssertionResult(
            name=f"command_succeeds:{command}",
            passed=False,
            message="command timed out after 60s",
            score=0.0,
        )


def check_command_fails(workdir: str | Path, command: str) -> AssertionResult:
    """Check that a shell command exits with a non-zero code."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=workdir,
            timeout=60,
            capture_output=True,
            check=False,
        )
        passed = result.returncode != 0
        return AssertionResult(
            name=f"command_fails:{command}",
            passed=passed,
            message=f"exit code {result.returncode}",
            score=1.0 if passed else 0.0,
        )
    except subprocess.TimeoutExpired:
        return AssertionResult(
            name=f"command_fails:{command}",
            passed=True,
            message="command timed out after 60s (counts as failure)",
            score=1.0,
        )


def evaluate_assertion(
    workdir: str | Path, assertion_dict: dict[str, Any] | BaseModel, *, source_dir: str | Path | None = None,
) -> AssertionResult:
    """Dispatch an assertion dict to the appropriate checker.

    Supported formats:
        {"file_exists": "main.tf"}
        {"file_contains": {"path": "x", "pattern": "y"}}
        {"command_succeeds": "echo ok"}
        {"command_fails": "false"}

    All assertion types support an optional ``weight`` field (default 1.0)
    that controls relative importance in weighted grade computation.

    Raises ValueError for unknown assertion types.
    """
    if not assertion_dict:
        raise ValueError("Empty assertion dict")

    if isinstance(assertion_dict, BaseModel):
        assertion_dict = assertion_dict.model_dump()

    # Extract weight before dispatching (not part of assertion logic)
    weight = assertion_dict.get("weight", 1.0)

    atype = next(k for k in assertion_dict if k != "weight")
    value = assertion_dict[atype]

    if atype in _SIMILARITY_TYPES:
        from agent_eval.assertions.similarity import evaluate_similarity_assertion

        result = evaluate_similarity_assertion(workdir, atype, value, source_dir=source_dir)
    elif atype == "file_exists":
        result = check_file_exists(workdir, value)
    elif atype == "file_contains":
        result = check_file_contains(workdir, value["path"], value["pattern"])
    elif atype == "command_succeeds":
        result = check_command_succeeds(workdir, value)
    elif atype == "command_fails":
        result = check_command_fails(workdir, value)
    else:
        raise ValueError(f"Unknown assertion type: '{atype}'")

    result.weight = weight
    return result
