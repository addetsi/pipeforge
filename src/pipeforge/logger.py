"""Logging configuration for Pipeforge."""

import logging
import sys
from pathlib import Path

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-24s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(
    level: int = logging.INFO,
    log_file: Path | None = None,
) -> None:
    """Configure logging for the pipeforge package.

    Sets up a console handler on the package root loggger, and optionally
    a file handler. Call this once, at application startup.

    Args:
        level: Minimum severity to emit. Defaults to logging.INFO.
        log_file: if given, also writes logs to this path.
    """
    package_logger = logging.getLogger("pipeforge")
    package_logger.setLevel(level)
    package_logger.handlers.clear()

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    package_logger.addHandler(console_handler)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        package_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """Return a logger for a module.

    Args:
        name: The module name, normally passed as __name__.

    Returns:
        A logger that inherits the package's handler and level
    """
    return logging.getLogger(name)
