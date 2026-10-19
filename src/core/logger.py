"""Structured logging configuration."""

import logging
import sys


def setup_logger(name: str = "agentic-code-rag", level: str = "INFO") -> logging.Logger:
    """Configures and returns a standardized console logger."""
    logger = logging.getLogger(name)

    if not logger.handlers:
        logger.setLevel(level.upper())
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level.upper())

        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
