"""Custom exceptions for PipeForge."""

from typing import Any


class PipeForgeError(Exception):
    """Base class for all PipeForge errors.

    Args:
        message: Human-readable description of what went wrong.
        context: Optional structured detail about the failure.
    """

    def __init__(self, message: str, context: dict[str, Any] | None = None) -> None:
        """Constructure to initialize Args."""
        super().__init__(message)
        self.message = message
        self.context = context or {}

    def __str__(self) -> str:
        """Return the message, with context appended if present."""
        if not self.context:
            return self.message
        details = ", ".join(f"{k}={v}" for k, v in self.context.items())
        return f"{self.message} ({details})"

    def __repr__(self) -> str:
        """Returns an unabmbiguous representation for debugging."""
        return (
            f"{type(self).__name__}(message={self.message!r},context={self.context!r})"
        )


class ConfigError(PipeForgeError):
    """Raised When a config file is missing, malformed, or invalid."""


class SchemaError(PipeForgeError):
    """Raised when a schema definition is invalid."""


class ValidationError(PipeForgeError):
    """Raised when data fails validation against a schema."""


class ReaderError(PipeForgeError):
    """Raised when a file cannot be read."""


class WriteError(PipeForgeError):
    """Raised when output cannot be written."""


class TransformError(PipeForgeError):
    """Raised when a transformation fails."""
