"""Data file inspection and profiling."""

from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from pipeforge.config import ColumnSchema, DataType, FileFormat
from pipeforge.logger import get_logger
from pipeforge.readers import _infer_format, read_file
from pipeforge.utils import is_boolean, is_date, is_float, is_integer, is_null

logger = get_logger(__name__)

DOMINANT_THRESHOLD = 0.5


class ColumnProfile(BaseModel):
    """Statistics describing a single column.

    Attributes:
        name: The column name.
        inferred_type: The narrowest type that fits every non-null value.
        dominant_type: When inferred_type is string, the narrowest type
            that fits most non-null values. None when they agree.
        dominant_ratio: The fraction of non-null values matching
            dominant_type.
        null_count: Number of null or empty values.
        null_percentage: Nulls as a percentage of all rows.
        unique_count: Number of distinct non-null values.
        duplicate_count: Non-null values that repeat an earlier value.
        min_value: Smallest value, for numeric columns.
        max_value: Largest value, for numeric columns.
        min_length: Shortest string length, for string columns.
        max_length: Longest string length, for string columns.
        sample_values: Up to five distinct values, in first-seen order.
    """

    name: str
    inferred_type: DataType
    dominant_type: DataType | None = None
    dominant_ratio: float | None = None
    null_count: int = 0
    null_percentage: float = 0.0
    unique_count: int = 0
    duplicate_count: int = 0
    min_value: float | None = None
    max_value: float | None = None
    min_length: int | None = None
    max_length: int | None = None
    sample_values: list[str] = Field(default_factory=list)


class InspectionReport(BaseModel):
    """A profile of a data file.

    Attributes:
        file_name: The file's name.
        file_size: Size in bytes.
        file_format: The format the file was read as.
        row_count: Number of rows.
        column_count: Number of columns.
        columns: A profile per column, in file order.
    """

    file_name: str
    file_size: int
    file_format: FileFormat
    row_count: int
    column_count: int
    columns: list[ColumnProfile] = Field(default_factory=list)


_CANDIDATES: list[DataType] = ["integer", "float", "date", "boolean"]


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
        return is_integer(value)
    if column.data_type == "float":
        return is_float(value)
    if column.data_type == "boolean":
        return is_boolean(value)
    return is_date(value, column.date_format)


def infer_type(values: list[Any]) -> tuple[DataType, DataType | None, float | None]:
    """Determine the type of a sequence of values.

    Candidate types are tried narrowest first. A column is typed as the
    first candidate every non-null value satisfies, falling back to
    string. When the result is string, the best-fitting candidate is also
    reported if it covers at least half the values.

    Args:
        values: Non-null values from one column.

    Returns:
        A tuple of (inferred_type, dominant_type, dominant_ratio). The
        second and third are None when no candidate applies or when the
        inferred type is not string.
    """
    if not values:
        return "string", None, None

    ratios = {
        candidate: sum(_matches(v, candidate) for v in values) / len(values)
        for candidate in _CANDIDATES
    }

    for candidate in _CANDIDATES:
        if ratios[candidate] == 1.0:
            return candidate, None, None

    best = max(_CANDIDATES, key=lambda c: ratios[c])
    if ratios[best] >= DOMINANT_THRESHOLD:
        return "string", best, round(ratios[best], 4)
    return "string", None, None


def _matches(value: Any, data_type: DataType) -> bool:
    """Return True if a value can be interpreted as the given type."""
    if data_type == "integer":
        return is_integer(value)
    if data_type == "float":
        return is_float(value)
    if data_type == "date":
        return is_date(value)
    if data_type == "boolean":
        return is_boolean(value)
    return True


def profile_column(name: str, values: list[Any], row_count: int) -> ColumnProfile:
    """Build a profile for one column.

    Args:
        name: The column name.
        values: Every value for this column, including nulls.
        row_count: Total rows, used for the null percentage.

    Returns:
        The column's profile.
    """
    non_null = [v for v in values if not is_null(v)]
    null_count = len(values) - len(non_null)
    inferred, dominant, ratio = infer_type(non_null)

    counts = Counter(str(v) for v in non_null)
    unique_count = len(counts)
    duplicate_count = len(non_null) - unique_count

    profile = ColumnProfile(
        name=name,
        inferred_type=inferred,
        dominant_type=dominant,
        dominant_ratio=ratio,
        null_count=null_count,
        null_percentage=round(100 * null_count / row_count, 2) if row_count else 0.0,
        unique_count=unique_count,
        duplicate_count=duplicate_count,
        sample_values=list(counts)[:5],
    )

    if inferred in ("integer", "float") and non_null:
        numbers = [float(v) for v in non_null]
        profile.min_value = min(numbers)
        profile.max_value = max(numbers)
    elif non_null:
        lengths = [len(str(v)) for v in non_null]
        profile.min_length = min(lengths)
        profile.max_length = max(lengths)

    return profile


def inspect_file(path: Path, file_format: FileFormat | None = None) -> InspectionReport:
    """Profile a data file.

    Args:
        path: Path to the file.
        file_format: Format to read as. Inferred from the extension if
            omitted.

    Returns:
        A report describing the file and each of its columns.

    Raises:
        ReaderError: If the file cannot be read.
    """
    rows = list(read_file(path, file_format))
    resolved = file_format or _infer_format(path)

    names: dict[str, None] = {}
    for row in rows:
        for key in row:
            names[key] = None

    columns = [
        profile_column(name, [row.get(name) for row in rows], len(rows))
        for name in names
    ]

    report = InspectionReport(
        file_name=path.name,
        file_size=path.stat().st_size,
        file_format=resolved,
        row_count=len(rows),
        column_count=len(names),
        columns=columns,
    )
    logger.info("Inspected %s: %d rows, %d columns", path.name, len(rows), len(names))
    return report


def format_report(report: InspectionReport) -> str:
    """Render a report as an aligned plain-text table.

    Args:
        report: The report to render.

    Returns:
        The formatted report, ready to print.
    """
    header = (
        f"{report.file_name}  "
        f"({report.file_size:,} bytes, {report.file_format})\n"
        f"{report.row_count:,} rows x {report.column_count} columns\n"
    )

    width = max((len(c.name) for c in report.columns), default=4)
    lines = [
        f"{'COLUMN':<{width}}  {'TYPE':<8}  {'NULLS':>10}  "
        f"{'UNIQUE':>7}  {'RANGE':<24}  SAMPLE",
        "-" * (width + 66),
    ]

    for column in report.columns:
        nulls = f"{column.null_count} ({column.null_percentage}%)"
        samples = ", ".join(column.sample_values[:3])
        lines.append(
            f"{column.name:<{width}}  {column.inferred_type:<8}  {nulls:>10}  "
            f"{column.unique_count:>7}  {_range(column):<24}  {samples[:40]}"
        )
        if column.dominant_type is not None and column.dominant_ratio is not None:
            share = round(100 * column.dominant_ratio, 1)
            lines.append(
                f"{'':<{width}}  -> {share}% of values parse as {column.dominant_type}"
            )

    return header + "\n".join(lines)


def _range(column: ColumnProfile) -> str:
    """Describe a column's value range for display."""
    if column.min_value is not None:
        return f"{column.min_value:g} .. {column.max_value:g}"
    if column.min_length is not None:
        return f"len {column.min_length} .. {column.max_length}"
    return ""
