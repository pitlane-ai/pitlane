"""Pytest configuration and fixtures."""

import logging
import pytest


@pytest.fixture(autouse=True)
def cleanup_loggers():
    """Clean up agent_eval loggers after each test to prevent name collisions."""
    yield

    # Remove all agent_eval loggers from registry
    loggers_to_remove = [
        name
        for name in logging.Logger.manager.loggerDict.keys()
        if name.startswith("agent_eval")
    ]

    for name in loggers_to_remove:
        logger = logging.getLogger(name)
        logger.handlers.clear()
        del logging.Logger.manager.loggerDict[name]
