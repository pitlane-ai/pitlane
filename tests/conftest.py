"""Pytest configuration and fixtures."""

import logging
import subprocess
import pytest


@pytest.fixture(autouse=True)
def cleanup_loggers():
    """Clean up pitlane loggers after each test to prevent name collisions."""
    yield

    # Remove all pitlane loggers from registry
    loggers_to_remove = [
        name
        for name in logging.Logger.manager.loggerDict.keys()
        if name.startswith("pitlane")
    ]

    for name in loggers_to_remove:
        logger = logging.getLogger(name)
        logger.handlers.clear()
        del logging.Logger.manager.loggerDict[name]


# ---------------------------------------------------------------------------
# E2E helpers and fixtures
# ---------------------------------------------------------------------------


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


@pytest.fixture
def live_workspace(tmp_path):
    """Empty temporary workspace directory for E2E tests."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace


@pytest.fixture
def live_logger():
    """DEBUG-level logger for E2E test output."""
    logger = logging.getLogger("pitlane_e2e")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        logger.addHandler(handler)
    return logger
