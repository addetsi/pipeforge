"""Tests for the exception hierarchy in PipeForge."""

import pytest
from pipeforge.exceptions import (
    ConfigError,
    PipeForgeError,
    ReaderError,
    ValidationError,
)


def test_error_carries_message() -> None:
    """The message is stored and returned by str()."""
    err = ConfigError("Missing field")
    assert str(err) == "Missing field"


def test_context_defaults_to_empty_dct() -> None:
    """Omitting context gives an empty dict, not None."""
    err = ConfigError("Missing field")
    assert err.context == {}


def test_context_is_not_shared_between_instances() -> None:
    """Each instance gets its own context and dictionary."""
    first = ConfigError("first")
    second = ConfigError("second")
    first.context["file"] = "pipeline.yml"
    assert second.context == {}


def test_subclasses_inherit_from_base() -> None:
    """Every specific error is catchable as PipeForgeException."""
    error_classes: tuple[type[PipeForgeError], ...] = (
        ConfigError,
        ReaderError,
        ValidationError,
    )

    for error_class in error_classes:
        with pytest.raises(PipeForgeError):
            raise error_class("BOOM")


def test_repr_shows_class_and_fields() -> None:
    """The repr is unabmbiguous for debugging."""
    err = ConfigError("Missing field", {"field": "schema_path"})
    assert repr(err) == (
        "ConfigError(message='Missing field',context={'field': 'schema_path'})"
    )


def test_error_appends_context() -> None:
    """Context is rendered alongside the message."""
    err = ConfigError("Missing field", {"field": "schema_path"})
    assert str(err) == "Missing field (field=schema_path)"
