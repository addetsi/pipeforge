"""Tests for the pipeforge package."""

import pipeforge


def test_version_is_set() -> None:
    """The package exposes a version string."""
    assert pipeforge.__version__ == "1.0.0"
