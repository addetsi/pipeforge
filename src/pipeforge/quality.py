"""Data quality report generation."""

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from pipeforge.config import FileFormat, load_schema
from pipeforge.inspectors import ColumnProfile, profile_rows
from pipeforge.logger import get_logger
from pipeforge.readers import read_file
from pipeforge.validators import ValidationIssue, validate_schema

logger = get_logger(__name__)


class QualityReport(BaseModel):
    """A combined validation and profiling report for a data file.

    Attributes:
        file_name: The inspected file's name.
        schema_name: The schema validated against.
        generated_at: When the report was produced, in UTC.
        row_count: Total rows examined.
        column_count: Number of columns.
        is_valid: True when no errors were found.
        invalid_rows: Rows with at least one error.
        completeness: Percentage of cells holding a non-null value.
        issues_by_type: Count of issues per issue type.
        columns: A profile per column.
        errors: Every blocking issue found.
        warnings: Every non-blocking issue found.
    """

    file_name: str
    schema_name: str
    generated_at: datetime
    row_count: int
    column_count: int
    is_valid: bool
    invalid_rows: int
    completeness: float
    issues_by_type: dict[str, int] = Field(default_factory=dict)
    columns: list[ColumnProfile] = Field(default_factory=list)
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)


def generate_quality_report(
    input_path: Path, schema_path: Path, file_format: FileFormat | None = None
) -> QualityReport:
    """Validate and profile a data file in one pass.

    Args:
        input_path: The data file to examine.
        schema_path: The schema to validate against.
        file_format: Format to read as. Inferred from the extension if
            omitted.

    Returns:
        A report combining validation results and column profiles.

    Raises:
        ReaderError: If the data file cannot be read.
        SchemaError: If the schema cannot be loaded.
    """
    rows = list(read_file(input_path, file_format))
    schema = load_schema(schema_path)

    result = validate_schema(rows, schema)
    columns = profile_rows(rows)

    total_cells = sum(len(row) for row in rows)
    null_cells = sum(column.null_count for column in columns)
    completeness = (
        round(100 * (total_cells - null_cells) / total_cells, 2) if total_cells else 0.0
    )

    issues_by_type = Counter(
        issue.issue_type.value for issue in result.errors + result.warnings
    )

    report = QualityReport(
        file_name=input_path.name,
        schema_name=schema.name,
        generated_at=datetime.now(UTC),
        row_count=result.row_count,
        column_count=len(columns),
        is_valid=result.is_valid,
        invalid_rows=result.invalid_rows,
        completeness=completeness,
        issues_by_type=dict(issues_by_type),
        columns=columns,
        errors=result.errors,
        warnings=result.warnings,
    )
    logger.info(
        "Quality report for %s: valid=%s, completeness=%.1f%%",
        input_path.name,
        report.is_valid,
        completeness,
    )
    return report
