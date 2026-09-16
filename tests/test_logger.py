"""Tests for the LOGGER functionality in PipeForge."""

import logging
from pathlib import Path

import pytest
from pipeforge.logger import configure_logging, get_logger


def test_configure_adds_console_handler() -> None:
    """Configuring attaches exactly one handler to the package logger."""
    configure_logging()
    package_logger = logging.getLogger("pipeforge")
    assert len(package_logger.handlers) == 1


def test_configure_twice_does_not_duplicate_handlers() -> None:
    """Repeated configuration clear previous handlers."""
    configure_logging()
    configure_logging()
    package_logger = logging.getLogger("pipeforge")
    assert len(package_logger.handlers) == 1


def test_log_file_is_created(tmp_path: Path) -> None:
    """A log file is created at the specified path."""
    log_file = tmp_path / "logs" / "pipeforge.log"
    configure_logging(log_file=log_file)
    get_logger("pipeforge.test").info("hello")
    assert log_file.exists()
    assert "hello" in log_file.read_text()


def test_child_logger_propagates_to_package_handlers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A module logger's output reaches the package logger's handler."""
    configure_logging(level=logging.DEBUG)
    with caplog.at_level(logging.DEBUG, logger="pipeforge"):
        get_logger("pipeforge.readers").debug("reading")

    assert "reading" in caplog.text
