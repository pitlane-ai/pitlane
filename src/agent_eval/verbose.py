"""Verbose logging configuration for debug output."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup_verbose_logger(debug_file: Path | None = None) -> logging.Logger:
    """
    Configure and return a logger for verbose debug output.
    
    Args:
        debug_file: Optional path to debug log file. If provided, logs to both
                   stderr and the file. If None, returns a disabled logger.
    
    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger("agent_eval")
    
    # Clear any existing handlers
    logger.handlers.clear()
    
    if debug_file is None:
        logger.disabled = True
        return logger
    
    logger.disabled = False
    logger.setLevel(logging.DEBUG)
    
    # Create formatter with timestamp
    formatter = logging.Formatter(
        fmt="[%(asctime)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S"
    )
    
    # Add stderr handler
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.DEBUG)
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stderr_handler)
    
    # Add file handler
    file_handler = logging.FileHandler(debug_file, mode='a')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger
