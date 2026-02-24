"""Fixtures for E2E tests that invoke real AI assistants."""

import os
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest


def run_with_tee(cmd, *, timeout):
    """Run a subprocess, streaming output while capturing it for assertions."""
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    stdout_lines, stderr_lines = [], []

    def _reader(stream, buf, dest):
        for line in stream:
            buf.append(line)
            dest.write(line)
            dest.flush()

    t_out = threading.Thread(
        target=_reader, args=(proc.stdout, stdout_lines, sys.stdout)
    )
    t_err = threading.Thread(
        target=_reader, args=(proc.stderr, stderr_lines, sys.stderr)
    )
    t_out.start()
    t_err.start()
    proc.wait(timeout=timeout)
    t_out.join()
    t_err.join()

    return SimpleNamespace(
        returncode=proc.returncode,
        stdout="".join(stdout_lines),
        stderr="".join(stderr_lines),
    )


def _assert_cli_installed(cli_name: str) -> None:
    """Assert that a CLI is installed; call pytest.fail() (not skip) if missing."""
    try:
        result = subprocess.run(
            [cli_name, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            pytest.fail(
                f"CLI '{cli_name}' returned exit code {result.returncode}. "
                "Ensure it is installed before running E2E tests.",
                pytrace=False,
            )
    except FileNotFoundError:
        pytest.fail(
            f"CLI '{cli_name}' not found. Install it before running E2E tests.",
            pytrace=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(
            f"CLI '{cli_name} --version' timed out. Check the installation.",
            pytrace=False,
        )
    except Exception as e:
        pytest.fail(
            f"CLI '{cli_name}' check failed: {e}",
            pytrace=False,
        )


@pytest.fixture(scope="session")
def require_claude_cli():
    _assert_cli_installed("claude")


@pytest.fixture(scope="session")
def require_bob_cli():
    _assert_cli_installed("bob")


@pytest.fixture(scope="session")
def require_opencode_cli():
    _assert_cli_installed("opencode")


@pytest.fixture(scope="session")
def require_vibe_cli():
    _assert_cli_installed("vibe")


@pytest.fixture(scope="session")
def require_pitlane_cli():
    _assert_cli_installed("pitlane")
