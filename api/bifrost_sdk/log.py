"""
Bifrost SDK Log Module

Logging utilities that integrate with Bifrost execution logs.
"""

import logging
import sys
from typing import Any


# Module-level logger
_logger = logging.getLogger("bifrost_sdk")


def _configure_logger():
    """Configure the SDK logger with console output."""
    if not _logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s - [Bifrost] %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        _logger.addHandler(handler)
        _logger.setLevel(logging.INFO)


# Configure on import
_configure_logger()


def _format_metadata(metadata: dict[str, Any] | None) -> str:
    """Format metadata for log output."""
    if not metadata:
        return ""
    parts = [f"{k}={v}" for k, v in metadata.items()]
    return f" [{', '.join(parts)}]"


def info(message: str, **metadata: Any):
    """
    Log info message.

    Args:
        message: Log message
        **metadata: Additional metadata as keyword arguments
    """
    suffix = _format_metadata(metadata) if metadata else ""
    _logger.info(f"{message}{suffix}")


def warning(message: str, **metadata: Any):
    """
    Log warning message.

    Args:
        message: Log message
        **metadata: Additional metadata
    """
    suffix = _format_metadata(metadata) if metadata else ""
    _logger.warning(f"{message}{suffix}")


def error(message: str, **metadata: Any):
    """
    Log error message.

    Args:
        message: Log message
        **metadata: Additional metadata
    """
    suffix = _format_metadata(metadata) if metadata else ""
    _logger.error(f"{message}{suffix}")


def debug(message: str, **metadata: Any):
    """
    Log debug message.

    Args:
        message: Log message
        **metadata: Additional metadata
    """
    suffix = _format_metadata(metadata) if metadata else ""
    _logger.debug(f"{message}{suffix}")


def set_level(level: str | int):
    """
    Set log level.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR) or logging constant
    """
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)
    _logger.setLevel(level)


# Convenience aliases
warn = warning
