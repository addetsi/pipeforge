"""Tests for shared utility predicates."""

from datetime import date, datetime
from typing import Any

import pytest

from pipeforge.utils import is_boolean, is_date, is_float, is_integer, is_null


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, True),
        ("", True),
        ("   ", True),
        ("\t\n", True),
        ("0", False),
        (0, False),
        (False, False),
        ([], False),
    ],
)
def test_is_null(value: Any, expected: bool) -> None:
    """None and blank strings are null; falsy values are not."""
    assert is_null(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1001, True),
        ("1001", True),
        ("  1001  ", True),
        (1001.0, True),
        (1001.5, False),
        ("1001.5", False),
        (True, False),
        ("abc", False),
        (None, False),
        ([], False),
        (date(2026, 1, 15), False),
    ],
)
def test_is_integer(value: Any, expected: bool) -> None:
    """Whole numbers in any form are integers; booleans are not."""
    assert is_integer(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1200.0, True),
        (1200, True),
        ("1200.00", True),
        ("  1200.00  ", True),
        ("1e5", True),
        ("-50.5", True),
        (True, False),
        ("abc", False),
        (None, False),
        ([], False),
    ],
)
def test_is_float(value: Any, expected: bool) -> None:
    """Anything float() accepts is a float; booleans are not."""
    assert is_float(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, True),
        (False, True),
        ("true", True),
        ("FALSE", True),
        ("yes", True),
        ("no", True),
        ("1", True),
        ("0", True),
        ("maybe", False),
        (1, False),
        (None, False),
    ],
)
def test_is_boolean(value: Any, expected: bool) -> None:
    """Real booleans and common string spellings are accepted."""
    assert is_boolean(value) is expected


@pytest.mark.parametrize(
    ("value", "date_format", "expected"),
    [
        (date(2026, 1, 15), None, True),
        (datetime(2026, 1, 15, 10, 30), None, True),
        ("2026-01-15", None, True),
        ("  2026-01-15  ", None, True),
        ("15/01/2026", None, False),
        ("15/01/2026", "%d/%m/%Y", True),
        ("2026-13-45", None, False),
        ("not_a_date", None, False),
        (1001, None, False),
        (None, None, False),
    ],
)
def test_is_date(value: Any, date_format: str | None, expected: bool) -> None:
    """Dates and parseable strings are dates; other types are not."""
    assert is_date(value, date_format) is expected
