"""Fixtures for E2E tests that invoke real AI assistants."""

import subprocess

import pytest


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
