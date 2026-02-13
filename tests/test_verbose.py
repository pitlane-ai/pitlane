"""Tests for verbose logging."""

from pathlib import Path
from agent_eval.verbose import setup_logger
import tempfile
import logging


def test_verbose_logger_creates_debug_log():
    """Logger should always create debug.log file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        debug_file = Path(tmpdir) / "debug.log"
        logger = setup_logger(debug_file=debug_file, verbose=False)
        
        assert not logger.disabled
        assert logger.level == logging.DEBUG
        assert debug_file.exists()


def test_verbose_logger_writes_to_file():
    """Logger should write messages to debug file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        debug_file = Path(tmpdir) / "debug.log"
        logger = setup_logger(debug_file=debug_file, verbose=False)
        
        logger.debug("test message")
        
        content = debug_file.read_text()
        assert "test message" in content
        assert "[" in content  # timestamp


def test_verbose_mode_adds_stderr_handler():
    """Logger should have stderr handler when verbose=True."""
    with tempfile.TemporaryDirectory() as tmpdir:
        debug_file = Path(tmpdir) / "debug.log"
        logger = setup_logger(debug_file=debug_file, verbose=True)
        
        assert len(logger.handlers) == 2
        handler_types = [type(h).__name__ for h in logger.handlers]
        assert "StreamHandler" in handler_types
        assert "FileHandler" in handler_types


def test_non_verbose_mode_only_file_handler():
    """Logger should only have file handler when verbose=False."""
    with tempfile.TemporaryDirectory() as tmpdir:
        debug_file = Path(tmpdir) / "debug.log"
        logger = setup_logger(debug_file=debug_file, verbose=False)
        
        assert len(logger.handlers) == 1
        handler_types = [type(h).__name__ for h in logger.handlers]
        assert "FileHandler" in handler_types
        assert "StreamHandler" not in handler_types


def test_logger_creates_parent_directories():
    """Logger should create parent directories for debug file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        debug_file = Path(tmpdir) / "nested" / "dir" / "debug.log"
        setup_logger(debug_file=debug_file, verbose=False)
        
        assert debug_file.exists()
        assert debug_file.parent.exists()
