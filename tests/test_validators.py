"""Tests for data validation."""

from typing import Any

import pytest

from pipeforge.config import ColumnSchema, DataSchema
from pipeforge.exceptions import SchemaError
from pipeforge.validators import (
    IssueType,
    check_value,
    is_null,
    matches_type,
    validate_schema,
)


def _schema(**kwargs: Any) -> DataSchema:
    """Build a minimal schema around one or more columns."""
    return DataSchema(name="test", description="test schema", **kwargs)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, True), ("", True), ("   ", True), ("0", False), (0, False), (False, False)],
)
def test_is_null(value: Any, expected: bool) -> None:
    """Empty strings and None are null; zero and False are not."""
    assert is_null(value) is expected


@pytest.mark.parametrize(
    ("value", "data_type", "expected"),
    [
        ("1001", "integer", True),
        (1001, "integer", True),
        (1001.0, "integer", True),
        (1001.5, "integer", False),
        (True, "integer", False),
        ("1200.00", "float", True),
        ("not_a_number", "float", False),
        ("anything", "string", True),
        (42, "string", True),
        ("true", "boolean", True),
        ("maybe", "boolean", False),
    ],
)
def test_matches_type(value: Any, data_type: str, expected: bool) -> None:
    """Values are checked for interpretability, not exact Python type."""
    column = ColumnSchema(name="c", data_type=data_type)  # type: ignore[arg-type]
    assert matches_type(value, column) is expected


@pytest.mark.parametrize(
    ("value", "date_format", "expected"),
    [
        ("2026-01-15", "%Y-%m-%d", True),
        ("15/01/2026", "%Y-%m-%d", False),
        ("15/01/2026", "%d/%m/%Y", True),
        ("2026-01-15", None, True),
    ],
)
def test_date_format(value: str, date_format: str | None, expected: bool) -> None:
    """Dates are parsed against the declared format, defaulting to ISO."""
    column = ColumnSchema(name="d", data_type="date", date_format=date_format)
    assert matches_type(value, column) is expected


def test_nullable_column_accepts_null() -> None:
    """A nullable column reports no issue for an empty value."""
    column = ColumnSchema(name="note", data_type="string", nullable=True)
    assert check_value("", column, 1) == []


def test_null_in_required_column_reports_issue() -> None:
    """A non-nullable column reports NULL_VALUE for an empty value."""
    column = ColumnSchema(name="email", data_type="string")
    issues = check_value("", column, 3)
    assert [i.issue_type for i in issues] == [IssueType.NULL_VALUE]
    assert issues[0].row == 3


def test_type_failure_skips_range_check() -> None:
    """A value that fails its type check is not range-checked."""
    column = ColumnSchema(name="amount", data_type="float", min_value=0)
    issues = check_value("not_a_number", column, 1)
    assert [i.issue_type for i in issues] == [IssueType.WRONG_TYPE]


def test_date_failure_reports_date_issue_type() -> None:
    """An unparseable date is reported as BAD_DATE_FORMAT."""
    column = ColumnSchema(name="d", data_type="date", date_format="%Y-%m-%d")
    issues = check_value("invalid_date", column, 1)
    assert issues[0].issue_type is IssueType.BAD_DATE_FORMAT


def test_value_can_have_multiple_issues() -> None:
    """Independent checks all report on the same value."""
    column = ColumnSchema(
        name="code", data_type="string", allowed_values=["AA"], pattern="^[0-9]+$"
    )
    issues = check_value("BB", column, 1)
    assert {i.issue_type for i in issues} == {
        IssueType.NOT_ALLOWED,
        IssueType.PATTERN_MISMATCH,
    }


def test_invalid_regex_raises_schema_error() -> None:
    """A malformed pattern is a schema problem, not a data problem."""
    column = ColumnSchema(name="c", data_type="string", pattern="[unclosed")
    with pytest.raises(SchemaError):
        check_value("x", column, 1)


def test_missing_required_column_is_error() -> None:
    """A required column absent from the data is an error."""
    schema = _schema(columns=[ColumnSchema(name="order_id", data_type="integer")])
    result = validate_schema([{"other": "1"}], schema)
    assert result.is_valid is False
    assert result.errors[0].issue_type is IssueType.MISSING_COLUMN


def test_unexpected_column_is_warning() -> None:
    """A column not in the schema is reported but does not invalidate."""
    schema = _schema(columns=[ColumnSchema(name="a", data_type="string")])
    result = validate_schema([{"a": "x", "extra": "y"}], schema)
    assert result.is_valid is True
    assert result.warnings[0].issue_type is IssueType.UNEXPECTED_COLUMN


def test_duplicate_primary_key_is_error() -> None:
    """A repeated primary key is reported with the first occurrence."""
    schema = _schema(
        columns=[ColumnSchema(name="id", data_type="integer")], primary_key=["id"]
    )
    result = validate_schema([{"id": "1"}, {"id": "1"}], schema)
    assert result.errors[0].issue_type is IssueType.DUPLICATE_KEY
    assert result.errors[0].row == 2
    assert "row 1" in result.errors[0].message


def test_composite_primary_key() -> None:
    """Uniqueness is checked across all primary key columns together."""
    schema = _schema(
        columns=[
            ColumnSchema(name="a", data_type="string"),
            ColumnSchema(name="b", data_type="string"),
        ],
        primary_key=["a", "b"],
    )
    rows = [{"a": "1", "b": "x"}, {"a": "1", "b": "y"}, {"a": "1", "b": "x"}]
    result = validate_schema(rows, schema)
    assert len(result.errors) == 1
    assert result.errors[0].row == 3


def test_duplicate_row_is_warning() -> None:
    """An identical row is a warning, not an error."""
    schema = _schema(columns=[ColumnSchema(name="a", data_type="string")])
    result = validate_schema([{"a": "x"}, {"a": "x"}], schema)
    assert result.is_valid is True
    assert result.warnings[0].issue_type is IssueType.DUPLICATE_ROW


def test_invalid_rows_counts_rows_not_issues() -> None:
    """A row with several problems counts once."""
    schema = _schema(
        columns=[
            ColumnSchema(name="a", data_type="integer"),
            ColumnSchema(name="b", data_type="integer"),
        ]
    )
    result = validate_schema([{"a": "x", "b": "y"}], schema)
    assert len(result.errors) == 2
    assert result.invalid_rows == 1


def test_empty_dataset_is_valid() -> None:
    """No rows means nothing to invalidate."""
    schema = _schema(columns=[ColumnSchema(name="a", data_type="string")])
    result = validate_schema([], schema)
    assert result.is_valid is True
    assert result.row_count == 0


def test_all_rows_are_validated() -> None:
    """Validation does not stop at the first bad row."""
    schema = _schema(columns=[ColumnSchema(name="a", data_type="integer")])
    result = validate_schema([{"a": "x"}, {"a": "1"}, {"a": "z"}], schema)
    assert [issue.row for issue in result.errors] == [1, 3]
