"""Shared streaming utilities for adapters."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import logging


def run_streaming_sync(
    cmd: list[str],
    workdir: Path,
    timeout: int,
    logger: logging.Logger | None = None,
    env: dict[str, str] | None = None,
) -> tuple[str, str, int, bool]:
    proc = subprocess.Popen(
        cmd,
        cwd=workdir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    def _read(stream, lines: list[str], prefix: str) -> None:
        for line in stream:
            lines.append(line)
            if logger:
                logger.debug("[%s] %s", prefix, line.rstrip())

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    t_out = threading.Thread(target=_read, args=(proc.stdout, stdout_lines, "stdout"))
    t_err = threading.Thread(target=_read, args=(proc.stderr, stderr_lines, "stderr"))
    t_out.start()
    t_err.start()

    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.kill()
        proc.wait()

    t_out.join()
    t_err.join()

    return "".join(stdout_lines), "".join(stderr_lines), proc.returncode, timed_out
