"""Shared streaming utilities for adapters."""

from __future__ import annotations

import asyncio
import gc
import logging as _logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import logging

# ---------------------------------------------------------------------------
# Suppress asyncio subprocess-transport cleanup noise (module-level, once).
#
# When asyncio.run() closes the event loop, subprocess transports held alive
# by a reference cycle (transport ↔ protocol) get collected by the cyclic GC
# *after* the loop is closed.  Their __del__ then tries to close pipe
# transports on a dead loop, producing:
#   1. WARNING:asyncio  – "Loop … that handles pid … is closed"
#   2. RuntimeError traceback via sys.unraisablehook
#
# The RuntimeError cannot be caught by try/except or warnings.filterwarnings
# because it fires inside __del__.  We install a targeted unraisable-hook
# once at import time so it is always active regardless of which thread GC
# runs in.
# ---------------------------------------------------------------------------
_original_unraisable_hook = sys.unraisablehook


def _quiet_unraisable_hook(unraisable):
    if isinstance(unraisable.exc_value, RuntimeError) and "Event loop is closed" in str(
        unraisable.exc_value
    ):
        return
    _original_unraisable_hook(unraisable)


sys.unraisablehook = _quiet_unraisable_hook


async def run_command_with_streaming(
    cmd: list[str],
    workdir: Path,
    timeout: int,
    logger: logging.Logger | None = None,
    env: dict[str, str] | None = None,
) -> tuple[str, str, int, bool]:
    """
    Run command with optional real-time output streaming using asyncio.

    Args:
        cmd: Command and arguments to execute
        workdir: Working directory for command execution
        timeout: Timeout in seconds
        logger: Optional logger for streaming output
        env: Optional environment variables

    Returns:
        Tuple of (stdout, stderr, exit_code, timed_out).
        On timeout the process is killed and partial output is returned.
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=workdir,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        limit=16 * 1024 * 1024,  # 16 MiB – MCP resource payloads can be large
    )

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    async def read_stream(stream, lines, prefix):
        while True:
            line = await stream.readline()
            if not line:
                break
            line_str = line.decode("utf-8")
            lines.append(line_str)
            if logger:
                logger.debug(f"[{prefix}] {line_str.rstrip()}")

    # Read both streams concurrently
    timed_out = False
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
        timed_out = True
        proc.kill()
        await proc.wait()
        # Fall through to return partial output collected before timeout

    stdout = "".join(stdout_lines)
    stderr = "".join(stderr_lines)
    returncode = proc.returncode
    assert returncode is not None

    # Close process transport while the event loop is still active.
    # This sets _closed=True so __del__ becomes a no-op in many cases.
    try:
        proc._transport.close()  # type: ignore[attr-defined]
    except Exception:
        pass

    return stdout, stderr, returncode, timed_out


def run_streaming_sync(
    cmd: list[str],
    workdir: Path,
    timeout: int,
    logger: logging.Logger | None = None,
    env: dict[str, str] | None = None,
) -> tuple[str, str, int, bool]:
    """Synchronous wrapper around run_command_with_streaming.

    Suppresses 'Event loop is closed' noise that occurs when subprocess
    transports are garbage-collected after the event loop shuts down.

    Three layers of defence:
      1. proc._transport.close() – marks transport closed while loop is live
      2. asyncio logger set to CRITICAL + gc.collect() – catches the WARNING
         from any transports the cyclic GC collects after asyncio.run()
      3. sys.unraisablehook (module-level) – catches the RuntimeError
         traceback from __del__ regardless of which thread triggers GC
    """
    asyncio_logger = _logging.getLogger("asyncio")
    original_level = asyncio_logger.level
    asyncio_logger.setLevel(_logging.CRITICAL)
    try:
        result = asyncio.run(
            run_command_with_streaming(cmd, workdir, timeout, logger, env)
        )
        # Force cyclic GC while the asyncio logger is suppressed so any
        # transport __del__ finalizers fire under our quiet context.
        gc.collect()
        return result
    finally:
        asyncio_logger.setLevel(original_level)
