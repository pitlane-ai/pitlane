"""Deterministic assertion checks (file existence, content, commands)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from agent_eval.assertions.base import AssertionResult

_SIMILARITY_TYPES = frozenset({"bleu", "rouge", "bertscore", "cosine_similarity"})


def check_file_exists(workdir: str | Path, filename: str) -> AssertionResult:
    """Check that a file exists in the working directory."""
    path = Path(workdir) / filename
    if path.exists():
        return AssertionResult(
            name=f"file_exists:{filename}",
            passed=True,
            message=f"{filename} exists",
        )
    return AssertionResult(
        name=f"file_exists:{filename}",
        passed=False,
        message=f"{filename} does not exist",
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
        )
    content = path.read_text()
    if re.search(pattern, content):
        return AssertionResult(
            name=f"file_contains:{filename}",
            passed=True,
            message=f"{filename} matches pattern '{pattern}'",
        )
    return AssertionResult(
        name=f"file_contains:{filename}",
        passed=False,
        message=f"{filename} does not match pattern '{pattern}'",
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
        )
    except subprocess.TimeoutExpired:
        return AssertionResult(
            name=f"command_succeeds:{command}",
            passed=False,
            message="command timed out after 60s",
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
        )
    except subprocess.TimeoutExpired:
        return AssertionResult(
            name=f"command_fails:{command}",
            passed=True,
            message="command timed out after 60s (counts as failure)",
        )


def evaluate_assertion(
    workdir: str | Path, assertion_dict: dict[str, Any]
) -> AssertionResult:
    """Dispatch an assertion dict to the appropriate checker.

    Supported formats:
        {"file_exists": "main.tf"}
        {"file_contains": {"path": "x", "pattern": "y"}}
        {"command_succeeds": "echo ok"}
        {"command_fails": "false"}

    Raises ValueError for unknown assertion types.
    """
    if not assertion_dict:
        raise ValueError("Empty assertion dict")

    atype = next(iter(assertion_dict))
    value = assertion_dict[atype]

    if atype in _SIMILARITY_TYPES:
        from agent_eval.assertions.similarity import evaluate_similarity_assertion

        return evaluate_similarity_assertion(workdir, atype, value)

    if atype == "file_exists":
        return check_file_exists(workdir, value)
    if atype == "file_contains":
        return check_file_contains(workdir, value["path"], value["pattern"])
    if atype == "command_succeeds":
        return check_command_succeeds(workdir, value)
    if atype == "command_fails":
        return check_command_fails(workdir, value)

    raise ValueError(f"Unknown assertion type: '{atype}'")
