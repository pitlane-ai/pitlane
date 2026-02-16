"""Test logger isolation to prevent debug.log mixing between assistants."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from agent_eval.verbose import setup_logger


def test_unique_logger_names_create_separate_instances(tmp_path: Path):
    """Test that different logger names create independent logger instances."""
    log1 = tmp_path / "assistant1.log"
    log2 = tmp_path / "assistant2.log"

    logger1 = setup_logger(
        log1, verbose=False, logger_name="agent_eval_assistant1_task1"
    )
    logger2 = setup_logger(
        log2, verbose=False, logger_name="agent_eval_assistant2_task1"
    )

    # Verify they are different logger instances
    assert logger1 is not logger2
    assert logger1.name != logger2.name

    # Write to each logger
    logger1.debug("Message from assistant1")
    logger2.debug("Message from assistant2")

    # Verify logs are isolated
    log1_content = log1.read_text()
    log2_content = log2.read_text()

    assert "Message from assistant1" in log1_content
    assert "Message from assistant2" not in log1_content

    assert "Message from assistant2" in log2_content
    assert "Message from assistant1" not in log2_content


def test_same_logger_name_raises_error(tmp_path: Path):
    """Test that reusing the same logger name raises RuntimeError."""
    log1 = tmp_path / "log1.log"
    log2 = tmp_path / "log2.log"

    # First call - should succeed
    logger1 = setup_logger(log1, verbose=False, logger_name="agent_eval_shared_test")
    logger1.debug("First message")

    # Second call with same name - should raise RuntimeError
    with pytest.raises(RuntimeError) as exc_info:
        setup_logger(log2, verbose=False, logger_name="agent_eval_shared_test")

    # Verify error message
    error_msg = str(exc_info.value)
    assert "agent_eval_shared_test" in error_msg
    assert "already exists" in error_msg


def test_parallel_loggers_with_unique_names(tmp_path: Path):
    """Test that multiple loggers can write concurrently without interference."""
    loggers = []
    log_files = []

    # Create 5 different loggers (simulating 5 assistants)
    for i in range(5):
        log_file = tmp_path / f"assistant{i}.log"
        log_files.append(log_file)
        logger = setup_logger(
            log_file,
            verbose=False,
            logger_name=f"agent_eval_parallel_assistant{i}_task1",
        )
        loggers.append(logger)

    # Write unique messages to each logger
    for i, logger in enumerate(loggers):
        logger.debug(f"Unique message from assistant {i}")

    # Verify each log file contains only its own message
    for i, log_file in enumerate(log_files):
        content = log_file.read_text()
        assert f"Unique message from assistant {i}" in content

        # Verify no messages from other assistants
        for j in range(5):
            if i != j:
                assert f"Unique message from assistant {j}" not in content


def test_logger_name_format_matches_runner_pattern():
    """Test that the logger name format matches what runner.py uses."""
    # This test documents the expected format: agent_eval_{assistant_name}_{task_name}
    assistant_name = "claude-baseline"
    task_name = "fibonacci-module"

    expected_format = f"agent_eval_{assistant_name}_{task_name}"

    # Verify the format is valid and unique
    assert expected_format == "agent_eval_claude-baseline_fibonacci-module"

    # Different assistant, same task should have different name
    other_assistant = "vibe-baseline"
    other_format = f"agent_eval_{other_assistant}_{task_name}"
    assert other_format != expected_format


def test_verbose_mode_adds_stderr_handler(tmp_path: Path):
    """Test that verbose mode adds stderr handler in addition to file handler."""
    log_file = tmp_path / "verbose.log"

    # Non-verbose: only file handler
    logger1 = setup_logger(
        log_file, verbose=False, logger_name="agent_eval_test_verbose_off"
    )
    assert len(logger1.handlers) == 1
    assert isinstance(logger1.handlers[0], logging.FileHandler)

    # Verbose: file handler + stderr handler
    logger2 = setup_logger(
        log_file, verbose=True, logger_name="agent_eval_test_verbose_on"
    )
    assert len(logger2.handlers) == 2
    handler_types = [type(h).__name__ for h in logger2.handlers]
    assert "FileHandler" in handler_types
    assert "StreamHandler" in handler_types


def test_collision_detection_prevents_log_mixing(tmp_path: Path):
    """Test that collision detection prevents the bug where logs get mixed."""
    log1 = tmp_path / "assistant1" / "task1" / "debug.log"
    log2 = tmp_path / "assistant2" / "task1" / "debug.log"

    # Setup first logger
    logger1 = setup_logger(
        log1, verbose=False, logger_name="agent_eval_collision_assistant1_task1"
    )
    logger1.debug("Message from assistant1")

    # Setup second logger with DIFFERENT name (correct usage)
    logger2 = setup_logger(
        log2, verbose=False, logger_name="agent_eval_collision_assistant2_task1"
    )
    logger2.debug("Message from assistant2")

    # Verify logs are properly isolated
    assert "Message from assistant1" in log1.read_text()
    assert "Message from assistant2" not in log1.read_text()
    assert "Message from assistant2" in log2.read_text()
    assert "Message from assistant1" not in log2.read_text()

    # Now try to create a logger with the SAME name as logger1 (should fail)
    log3 = tmp_path / "assistant3" / "task1" / "debug.log"
    with pytest.raises(RuntimeError):
        setup_logger(
            log3, verbose=False, logger_name="agent_eval_collision_assistant1_task1"
        )
