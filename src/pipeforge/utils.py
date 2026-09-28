"""Shared utility functions."""

from datetime import date, datetime
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


def is_integer(value: Any) -> bool:
    """Return True if a value can be interpreted as an integer.

    Booleans are rejected, since a schema declaring an integer column
    does not mean True or False.

    Args:
        value: The value to test.

    Returns:
        True if the value is, or parses as, a whole number.
    """
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return value.is_integer()
    if isinstance(value, str):
        try:
            int(value.strip())
        except ValueError:
            return False
        return True
    return False


def is_float(value: Any) -> bool:
    """Return True if a value can be interpreted as a float.

    Args:
        value: The value to test.

    Returns:
        True if the value is, or parses as, a number.
    """
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value.strip())
        except ValueError:
            return False
        return True
    return False


def is_boolean(value: Any) -> bool:
    """Return True if a value can be interpreted as a boolean.

    Args:
        value: The value to test.

    Returns:
        True for real booleans and for common string spellings.
    """
    if isinstance(value, bool):
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"true", "false", "yes", "no", "1", "0"}
    return False


def is_date(value: Any, date_format: str | None = None) -> bool:
    """Return True if a value can be interpreted as a date.

    Args:
        value: The value to test.
        date_format: A strptime format string. Defaults to ISO format.

    Returns:
        True if the value is a date or parses against the format.
    """
    if isinstance(value, (date, datetime)):
        return True
    if not isinstance(value, str):
        return False
    try:
        datetime.strptime(value.strip(), date_format or "%Y-%m-%d")
    except ValueError:
        return False
    return True
