"""Data validation against schemas."""

import re
from collections.abc import Iterable
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from pipeforge.config import ColumnSchema, DataSchema
from pipeforge.exceptions import SchemaError
from pipeforge.logger import get_logger
from pipeforge.utils import is_null

logger = get_logger(__name__)


class IssueType(StrEnum):
    """Categories of validation problem."""

    MISSING_COLUMN = "missing_column"
    UNEXPECTED_COLUMN = "unexpected_column"
    NULL_VALUE = "null_value"
    WRONG_TYPE = "wrong_type"
    OUT_OF_RANGE = "out_of_range"
    NOT_ALLOWED = "not_allowed"
    BAD_DATE_FORMAT = "bad_date_format"
    PATTERN_MISMATCH = "pattern_mismatch"
    DUPLICATE_KEY = "duplicate_key"
    NOT_UNIQUE = "not_unique"
    DUPLICATE_ROW = "duplicate_row"


class ValidationIssue(BaseModel):
    """A single problem found in the data.

    Attributes:
        issue_type: The category of problem.
        message: Human-readable description.
        row: 1-based row number in the data, or None for file-level issues.
        column: The column involved, or None for row- or file-level issues.
        expected: What the schema required.
        actual: What the data contained.
    """

    issue_type: IssueType
    message: str
    row: int | None = None
    column: str | None = None
    expected: str | None = None
    actual: str | None = None


class ValidationResult(BaseModel):
    """The outcome of validating a dataset against a schema.

    Attributes:
        is_valid: True when no errors were found. Warnings do not affect this.
        errors: Problems that make the data unusable.
        warnings: Problems worth reporting that do not block processing.
        row_count: Total rows examined.
        invalid_rows: Number of distinct rows with at least one error.
    """

    is_valid: bool
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    row_count: int = 0
    invalid_rows: int = 0


def _is_integer(value: Any) -> bool:
    """Return True if a value can be interpreted as an integer."""
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


def _is_float(value: Any) -> bool:
    """Return True if a value can be interpreted as a float."""
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


def _is_boolean(value: Any) -> bool:
    """Return True if a value can be interpreted as a boolean."""
    if isinstance(value, bool):
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"true", "false", "yes", "no", "1", "0"}
    return False


def _is_date(value: Any, date_format: str | None) -> bool:
    """Return True if a value can be interpreted as a date.

    Args:
        value: The raw value.
        date_format: A strptime format string. Defaults to ISO format.
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


def matches_type(value: Any, column: ColumnSchema) -> bool:
    """Return True if a value is compatible with a column's declared type.

    Args:
        value: The raw value from a data row.
        column: The column definition carrying the expected type.

    Returns:
        True if the value can be interpreted as the declared type.
    """
    if column.data_type == "string":
        return True
    if column.data_type == "integer":
        return _is_integer(value)
    if column.data_type == "float":
        return _is_float(value)
    if column.data_type == "boolean":
        return _is_boolean(value)
    return _is_date(value, column.date_format)


def check_value(
    value: Any, column: ColumnSchema, row_number: int
) -> list[ValidationIssue]:
    """Validate a single cell against its column definition.

    Checks stop early where continuing would be meaningless: a null value
    is not range-checked, and a value that fails its type check is not
    compared against numeric bounds.

    Args:
        value: The raw value from the data row.
        column: The column definition to validate against.
        row_number: 1-based row number, used in issue reporting.

    Returns:
        Every issue found for this cell. Empty when the value is valid.

    Raises:
        SchemaError: If the column declares an invalid regex pattern.
    """
    if is_null(value):
        if column.nullable:
            return []
        return [
            ValidationIssue(
                issue_type=IssueType.NULL_VALUE,
                message=f"{column.name} must not be null",
                row=row_number,
                column=column.name,
                expected="non-null",
                actual=repr(value),
            )
        ]

    if not matches_type(value, column):
        issue_type = (
            IssueType.BAD_DATE_FORMAT
            if column.data_type == "date"
            else IssueType.WRONG_TYPE
        )
        return [
            ValidationIssue(
                issue_type=issue_type,
                message=f"{column.name} is not a valid {column.data_type}",
                row=row_number,
                column=column.name,
                expected=column.date_format or column.data_type,
                actual=repr(value),
            )
        ]

    issues: list[ValidationIssue] = []
    issues.extend(_check_range(value, column, row_number))
    issues.extend(_check_allowed(value, column, row_number))
    issues.extend(_check_pattern(value, column, row_number))
    return issues


def _check_range(
    value: Any, column: ColumnSchema, row_number: int
) -> list[ValidationIssue]:
    """Check a numeric value against min_value and max_value."""
    if column.min_value is None and column.max_value is None:
        return []
    if column.data_type not in ("integer", "float"):
        return []

    number = float(value)
    if column.min_value is not None and number < column.min_value:
        return [
            ValidationIssue(
                issue_type=IssueType.OUT_OF_RANGE,
                message=f"{column.name} is below the minimum",
                row=row_number,
                column=column.name,
                expected=f">= {column.min_value}",
                actual=str(value),
            )
        ]
    if column.max_value is not None and number > column.max_value:
        return [
            ValidationIssue(
                issue_type=IssueType.OUT_OF_RANGE,
                message=f"{column.name} is above the maximum",
                row=row_number,
                column=column.name,
                expected=f"<= {column.max_value}",
                actual=str(value),
            )
        ]
    return []


def _check_allowed(
    value: Any, column: ColumnSchema, row_number: int
) -> list[ValidationIssue]:
    """Check a value against the column's allowed_values list."""
    if column.allowed_values is None:
        return []
    if str(value) in column.allowed_values:
        return []
    return [
        ValidationIssue(
            issue_type=IssueType.NOT_ALLOWED,
            message=f"{column.name} is not an allowed value",
            row=row_number,
            column=column.name,
            expected=", ".join(column.allowed_values),
            actual=str(value),
        )
    ]


def _check_pattern(
    value: Any, column: ColumnSchema, row_number: int
) -> list[ValidationIssue]:
    """Check a value against the column's regex pattern."""
    if column.pattern is None:
        return []
    try:
        matched = re.search(column.pattern, str(value))
    except re.error as e:
        raise SchemaError(
            "Invalid regex pattern",
            {"column": column.name, "pattern": column.pattern},
        ) from e
    if matched:
        return []
    return [
        ValidationIssue(
            issue_type=IssueType.PATTERN_MISMATCH,
            message=f"{column.name} does not match the required pattern",
            row=row_number,
            column=column.name,
            expected=column.pattern,
            actual=str(value),
        )
    ]


def validate_schema(
    rows: Iterable[dict[str, Any]], schema: DataSchema
) -> ValidationResult:
    """Validate a dataset against a schema.

    Every row is checked; validation does not stop at the first problem.
    The dataset is materialized in full because uniqueness and duplicate
    detection require access to all rows.

    Args:
        rows: The data to validate, as one dictionary per row.
        schema: The schema to validate against.

    Returns:
        A result carrying every error and warning found.

    Raises:
        SchemaError: If the schema declares an invalid regex pattern.
    """
    data = list(rows)
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []

    if not data:
        logger.warning("No rows to validate")
        return ValidationResult(is_valid=True, row_count=0)

    column_errors, column_warnings = _check_columns(set(data[0]), schema)
    errors.extend(column_errors)
    warnings.extend(column_warnings)

    invalid_row_numbers: set[int] = set()
    for row_number, row in enumerate(data, start=1):
        for column in schema.columns:
            if column.name not in row:
                continue
            issues = check_value(row[column.name], column, row_number)
            if issues:
                errors.extend(issues)
                invalid_row_numbers.add(row_number)

    errors.extend(_check_unique(data, schema))
    warnings.extend(_check_duplicate_rows(data))

    result = ValidationResult(
        is_valid=not errors,
        errors=errors,
        warnings=warnings,
        row_count=len(data),
        invalid_rows=len(invalid_row_numbers),
    )
    logger.info(
        "Validated %d rows: %d errors, %d warnings",
        result.row_count,
        len(result.errors),
        len(result.warnings),
    )
    return result


def _check_columns(
    present: set[str], schema: DataSchema
) -> tuple[list[ValidationIssue], list[ValidationIssue]]:
    """Compare the columns in the data against those in the schema.

    Returns:
        A tuple of (errors, warnings). Missing required columns are
        errors; columns not in the schema are warnings.
    """
    errors = [
        ValidationIssue(
            issue_type=IssueType.MISSING_COLUMN,
            message=f"Required column {column.name} is missing",
            column=column.name,
            expected="present",
            actual="absent",
        )
        for column in schema.columns
        if column.required and column.name not in present
    ]

    expected = {column.name for column in schema.columns}
    warnings = [
        ValidationIssue(
            issue_type=IssueType.UNEXPECTED_COLUMN,
            message=f"Column {name} is not defined in the schema",
            column=name,
        )
        for name in sorted(present - expected)
    ]
    return errors, warnings


def _check_unique(
    data: list[dict[str, Any]], schema: DataSchema
) -> list[ValidationIssue]:
    """Check primary key and unique column constraints."""
    issues: list[ValidationIssue] = []

    if schema.primary_key:
        issues.extend(
            _find_duplicates(
                data, schema.primary_key, IssueType.DUPLICATE_KEY, "primary key"
            )
        )

    for name in schema.unique_columns or []:
        issues.extend(
            _find_duplicates(data, [name], IssueType.NOT_UNIQUE, f"{name} value")
        )

    return issues


def _find_duplicates(
    data: list[dict[str, Any]],
    columns: list[str],
    issue_type: IssueType,
    label: str,
) -> list[ValidationIssue]:
    """Report rows whose values across the given columns repeat."""
    seen: dict[tuple[Any, ...], int] = {}
    issues: list[ValidationIssue] = []

    for row_number, row in enumerate(data, start=1):
        key = tuple(row.get(name) for name in columns)
        first_seen = seen.get(key)
        if first_seen is None:
            seen[key] = row_number
            continue
        issues.append(
            ValidationIssue(
                issue_type=issue_type,
                message=f"Duplicate {label}, first seen on row {first_seen}",
                row=row_number,
                column=", ".join(columns),
                expected="unique",
                actual=", ".join(str(part) for part in key),
            )
        )
    return issues


def _check_duplicate_rows(data: list[dict[str, Any]]) -> list[ValidationIssue]:
    """Report rows that are identical to an earlier row."""
    seen: dict[tuple[tuple[str, Any], ...], int] = {}
    issues: list[ValidationIssue] = []

    for row_number, row in enumerate(data, start=1):
        key = tuple(sorted(row.items()))
        first_seen = seen.get(key)
        if first_seen is None:
            seen[key] = row_number
            continue
        issues.append(
            ValidationIssue(
                issue_type=IssueType.DUPLICATE_ROW,
                message=f"Row is identical to row {first_seen}",
                row=row_number,
            )
        )
    return issues
