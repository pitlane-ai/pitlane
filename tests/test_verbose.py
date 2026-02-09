"""Tests for verbose logging."""

from pathlib import Path
from agent_eval.verbose import setup_verbose_logger
import tempfile
import logging


def test_verbose_logger_disabled_by_default():
    """Logger should be disabled when no debug file provided."""
    logger = setup_verbose_logger()
    assert logger.disabled


def test_verbose_logger_enabled_with_file():
    """Logger should be enabled when debug file provided."""
    with tempfile.TemporaryDirectory() as tmpdir:
        debug_file = Path(tmpdir) / "debug.log"
        logger = setup_verbose_logger(debug_file=debug_file)
        assert not logger.disabled
        assert logger.level == logging.DEBUG


def test_verbose_logger_writes_to_file():
    """Logger should write messages to debug file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        debug_file = Path(tmpdir) / "debug.log"
        logger = setup_verbose_logger(debug_file=debug_file)
        
        logger.debug("test message")
        
        content = debug_file.read_text()
        assert "test message" in content
        assert "[" in content  # timestamp


def test_verbose_logger_no_op_when_disabled():
    """Logger should not crash when disabled."""
    logger = setup_verbose_logger()
    logger.debug("test message")  # Should not raise


def test_verbose_logger_has_stderr_and_file_handlers():
    """Logger should have both stderr and file handlers."""
    with tempfile.TemporaryDirectory() as tmpdir:
        debug_file = Path(tmpdir) / "debug.log"
        logger = setup_verbose_logger(debug_file=debug_file)
        
        assert len(logger.handlers) == 2
        handler_types = [type(h).__name__ for h in logger.handlers]
        assert "StreamHandler" in handler_types
        assert "FileHandler" in handler_types