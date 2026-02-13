"""Deterministic assertion checks (file existence, content, commands)."""

from __future__ import annotations

import logging
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from agent_eval.assertions.base import AssertionResult

_SIMILARITY_TYPES = frozenset({"bleu", "rouge", "bertscore", "cosine_similarity"})


def check_file_exists(workdir: str | Path, filename: str, logger: logging.Logger) -> AssertionResult:
    """Check that a file exists in the working directory."""
    path = Path(workdir) / filename
    logger.info(f"Checking file_exists: {filename}")

    passed = path.exists()
    logger.info(f"File {filename} exists={passed}")

    return AssertionResult(
        name=f"file_exists:{filename}",
        passed=passed,
        message=f"{filename} exists" if passed else f"{filename} does not exist",
        score=1.0 if passed else 0.0,
    )


def check_file_contains(
    workdir: str | Path, filename: str, pattern: str, logger: logging.Logger
) -> AssertionResult:
    """Check that a file contains text matching a regex pattern."""
    path = Path(workdir) / filename
    logger.info(f"Checking file_contains: {filename} for pattern '{pattern}'")

    if not path.exists():
        logger.warning(f"File {filename} not found")
        return AssertionResult(
            name=f"file_contains:{filename}",
            passed=False,
            message=f"{filename} not found",
            score=0.0,
        )

    content = path.read_text()
    matched = re.search(pattern, content) is not None
    logger.info(f"Pattern '{pattern}' matched={matched} in {filename}")

    if matched:
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


def check_command_succeeds(workdir: str | Path, command: str, logger: logging.Logger) -> AssertionResult:
    """Check that a shell command exits with code 0."""
    logger.info(f"Running command_succeeds: {command}")

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

        logger.info(f"Command exited with code {result.returncode}, passed={passed}")
        if result.stdout:
            logger.debug(f"stdout: {result.stdout.decode('utf-8', errors='replace')}")
        if result.stderr:
            logger.debug(f"stderr: {result.stderr.decode('utf-8', errors='replace')}")

        return AssertionResult(
            name=f"command_succeeds:{command}",
            passed=passed,
            message=f"exit code {result.returncode}",
            score=1.0 if passed else 0.0,
        )
    except subprocess.TimeoutExpired:
        logger.warning("Command timed out after 60s")
        return AssertionResult(
            name=f"command_succeeds:{command}",
            passed=False,
            message="command timed out after 60s",
            score=0.0,
        )


def check_command_fails(workdir: str | Path, command: str, logger: logging.Logger) -> AssertionResult:
    """Check that a shell command exits with a non-zero code."""
    logger.info(f"Running command_fails: {command}")

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

        logger.info(f"Command exited with code {result.returncode}, passed={passed}")
        if result.stdout:
            logger.debug(f"stdout: {result.stdout.decode('utf-8', errors='replace')}")
        if result.stderr:
            logger.debug(f"stderr: {result.stderr.decode('utf-8', errors='replace')}")

        return AssertionResult(
            name=f"command_fails:{command}",
            passed=passed,
            message=f"exit code {result.returncode}",
            score=1.0 if passed else 0.0,
        )
    except subprocess.TimeoutExpired:
        logger.info("Command timed out after 60s (counts as failure)")
        return AssertionResult(
            name=f"command_fails:{command}",
            passed=True,
            message="command timed out after 60s (counts as failure)",
            score=1.0,
        )


def check_custom_script(
    workdir: str | Path,
    script: str,
    logger: logging.Logger,
    interpreter: str | None = None,
    interpreter_args: list[str] | None = None,
    script_args: list[str] | None = None,
    timeout: int = 60,
    expected_exit_code: int = 0,
) -> AssertionResult:
    """Run a custom script and check if it returns the expected exit code.

    Args:
        workdir: Working directory to run the script in
        script: Path to the script or command to execute
        interpreter: Optional interpreter program (e.g., 'python', 'node', 'ruby')
        interpreter_args: Optional list of flags for the interpreter (e.g., ['-u'] for Python)
        script_args: Optional list of arguments to pass to the script
        timeout: Maximum time in seconds to wait for script completion
        expected_exit_code: Expected exit code for the script (default: 0)
        logger: Logger for debugging

    Returns:
        AssertionResult indicating whether the script returned the expected exit code
    """
    # Build command parts
    command_parts = []
    
    # Add interpreter and its args
    if interpreter:
        command_parts.append(shlex.quote(interpreter))
        if interpreter_args:
            command_parts.extend(shlex.quote(arg) for arg in interpreter_args)
    
    # Add script
    command_parts.append(shlex.quote(script))
    
    # Add script args
    if script_args:
        command_parts.extend(shlex.quote(arg) for arg in script_args)
    
    command = " ".join(command_parts)

    logger.info(f"Running custom_script: {command} (timeout={timeout}s, expected_exit_code={expected_exit_code})")

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=workdir,
            timeout=timeout,
            capture_output=True,
            check=False,
        )
        passed = result.returncode == expected_exit_code

        logger.info(f"Script exited with code {result.returncode}, expected {expected_exit_code}, passed={passed}")
        if result.stdout:
            logger.debug(f"stdout: {result.stdout.decode('utf-8', errors='replace')}")
        if result.stderr:
            logger.debug(f"stderr: {result.stderr.decode('utf-8', errors='replace')}")

        # Include stdout/stderr in message if script failed
        message_parts = [f"exit code {result.returncode}"]
        if not passed:
            if result.stdout:
                stdout = result.stdout.decode('utf-8', errors='replace').strip()
                if stdout:
                    message_parts.append(f"stdout: {stdout[:200]}")
            if result.stderr:
                stderr = result.stderr.decode('utf-8', errors='replace').strip()
                if stderr:
                    message_parts.append(f"stderr: {stderr[:200]}")

        return AssertionResult(
            name=f"custom_script:{script}",
            passed=passed,
            message=" | ".join(message_parts),
            score=1.0 if passed else 0.0,
        )
    except subprocess.TimeoutExpired:
        logger.warning(f"Script timed out after {timeout}s")
        return AssertionResult(
            name=f"custom_script:{script}",
            passed=False,
            message=f"script timed out after {timeout}s",
            score=0.0,
        )
    except Exception as e:
        logger.error(f"Error running script: {str(e)}")
        return AssertionResult(
            name=f"custom_script:{script}",
            passed=False,
            message=f"error running script: {str(e)}",
            score=0.0,
        )


def evaluate_assertion(
    workdir: str | Path,
    assertion_dict: dict[str, Any] | BaseModel,
    *,
    source_dir: str | Path | None = None,
    logger: logging.Logger | None = None,
) -> AssertionResult:
    """Dispatch an assertion dict to the appropriate checker.

    Supported formats:
        {"file_exists": "main.tf"}
        {"file_contains": {"path": "x", "pattern": "y"}}
        {"command_succeeds": "echo ok"}
        {"command_fails": "false"}
        {"custom_script": "script.sh"}

    All assertion types support an optional ``weight`` field (default 1.0)
    that controls relative importance in weighted grade computation.

    Raises ValueError for unknown assertion types.
    """
    if not assertion_dict:
        raise ValueError("Empty assertion dict")

    if isinstance(assertion_dict, BaseModel):
        assertion_dict = assertion_dict.model_dump()

    if logger is None:
        logger = logging.getLogger(__name__)

    # Extract weight before dispatching (not part of assertion logic)
    weight = assertion_dict.get("weight", 1.0)

    atype = next(k for k in assertion_dict if k != "weight")
    value = assertion_dict[atype]

    if atype in _SIMILARITY_TYPES:
        from agent_eval.assertions.similarity import evaluate_similarity_assertion

        result = evaluate_similarity_assertion(workdir, atype, value, source_dir=source_dir, logger=logger)
    elif atype == "file_exists":
        result = check_file_exists(workdir, value, logger=logger)
    elif atype == "file_contains":
        result = check_file_contains(workdir, value["path"], value["pattern"], logger=logger)
    elif atype == "command_succeeds":
        result = check_command_succeeds(workdir, value, logger=logger)
    elif atype == "command_fails":
        result = check_command_fails(workdir, value, logger=logger)
    elif atype == "custom_script":
        # Handle both simple string and dict with options
        if isinstance(value, str):
            result = check_custom_script(workdir, value, logger)
        else:
            result = check_custom_script(
                workdir,
                value["script"],
                logger,
                interpreter=value.get("interpreter"),
                interpreter_args=value.get("interpreter_args"),
                script_args=value.get("script_args"),
                timeout=value.get("timeout", 60),
                expected_exit_code=value.get("expected_exit_code", 0),
            )
    else:
        raise ValueError(f"Unknown assertion type: '{atype}'")

    result.weight = weight
    return result
