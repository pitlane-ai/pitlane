"""Shared streaming utilities for adapters."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import logging


async def run_command_with_streaming(
    cmd: list[str],
    workdir: Path,
    timeout: int,
    logger: logging.Logger | None = None,
    env: dict[str, str] | None = None,
) -> tuple[str, str, int]:
    """
    Run command with optional real-time output streaming using asyncio.
    
    Args:
        cmd: Command and arguments to execute
        workdir: Working directory for command execution
        timeout: Timeout in seconds
        logger: Optional logger for streaming output
        env: Optional environment variables
    
    Returns:
        Tuple of (stdout, stderr, exit_code)
    
    Raises:
        subprocess.TimeoutExpired: If command exceeds timeout
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=workdir,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    stdout_lines = []
    stderr_lines = []

    async def read_stream(stream, lines, prefix):
        """Read stream line by line and optionally log."""
        while True:
            line = await stream.readline()
            if not line:
                break
            line_str = line.decode('utf-8')
            lines.append(line_str)
            if logger:
                logger.debug(f"[{prefix}] {line_str.rstrip()}")

    # Read both streams concurrently
    try:
        await asyncio.wait_for(
            asyncio.gather(
                read_stream(proc.stdout, stdout_lines, "stdout"),
                read_stream(proc.stderr, stderr_lines, "stderr"),
                proc.wait(),
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise subprocess.TimeoutExpired(cmd, timeout)

    stdout = ''.join(stdout_lines)
    stderr = ''.join(stderr_lines)
    return stdout, stderr, proc.returncode