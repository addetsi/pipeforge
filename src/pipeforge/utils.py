"""Shared utility functions."""

from typing import Any


def is_null(value: Any) -> bool:
    """Return True if a value represents absence of data.

    CSV represents a missing value as an empty string, while JSON and
    Parquet use None. Both are treated as null.

    Args:
        value: The raw value from a data row.

    Returns:
        True when the value is None or an empty/whitespace-only string.
    """
    if value is None:
        return True
    return isinstance(value, str) and not value.strip()
