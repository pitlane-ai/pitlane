"""Verbose logging configuration for debug output."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup_logger(debug_file: Path, verbose: bool = False, logger_name: str = "agent_eval") -> logging.Logger:
    """
    Configure and return a logger for debug output.
    
    Always writes to debug_file. Optionally also writes to stderr if verbose=True.
    
    Args:
        debug_file: Path to debug log file (always created)
        verbose: If True, also log to stderr. If False, only log to file.
        logger_name: Name of the logger instance (allows multiple independent loggers)
    
    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(logger_name)
    
    # Clear any existing handlers for this specific logger
    logger.handlers.clear()
    
    logger.disabled = False
    logger.setLevel(logging.DEBUG)
    
    # Create formatter with timestamp
    formatter = logging.Formatter(
        fmt="[%(asctime)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S"
    )
    
    # Always add file handler
    debug_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(debug_file, mode='a')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Add stderr handler only if verbose mode enabled
    if verbose:
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(logging.DEBUG)
        stderr_handler.setFormatter(formatter)
        logger.addHandler(stderr_handler)
    
    return logger


