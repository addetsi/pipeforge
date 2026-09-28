"""Tests for data inspection and profiling."""

from pathlib import Path
from typing import Any

import pytest

from pipeforge.inspectors import (
    format_report,
    infer_type,
    inspect_file,
    profile_column,
)

CSV_TEXT = """order_id,amount,status,note
1001,1200.00,completed,
1002,800.00,pending,x
1003,not_a_number,completed,
"""


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (["1001", "1002"], "integer"),
        (["1200.00", "800.50"], "float"),
        (["2026-01-15"], "date"),
        (["true", "no"], "boolean"),
        (["Laptop", "Phone"], "string"),
        ([], "string"),
    ],
)
def test_infer_type(values: list[Any], expected: str) -> None:
    """The narrowest type fitting every value is chosen."""
    assert infer_type(values)[0] == expected


def test_infer_type_prefers_integer_over_float() -> None:
    """Whole numbers infer as integer, not float."""
    assert infer_type(["1", "2", "3"])[0] == "integer"


def test_infer_type_reports_dominant_type() -> None:
    """A mostly-numeric column reports the dominant type and ratio."""
    inferred, dominant, ratio = infer_type(["1.5", "2.5", "bad"])
    assert inferred == "string"
    assert dominant == "float"
    assert ratio is not None
    assert round(ratio, 2) == 0.67


def test_infer_type_no_dominant_below_threshold() -> None:
    """A mostly-textual column reports no dominant type."""
    assert infer_type(["a", "b", "c", "1"])[1] is None


def test_profile_counts_nulls() -> None:
    """Empty strings and None both count as null."""
    profile = profile_column("c", ["x", "", None, "y"], 4)
    assert profile.null_count == 2
    assert profile.null_percentage == 50.0


def test_profile_counts_unique_and_duplicates() -> None:
    """Distinct non-null values are counted, repeats reported."""
    profile = profile_column("c", ["a", "a", "b", ""], 4)
    assert profile.unique_count == 2
    assert profile.duplicate_count == 1


def test_profile_numeric_range() -> None:
    """Numeric columns report min and max values."""
    profile = profile_column("c", ["10", "5", "20"], 3)
    assert profile.min_value == 5.0
    assert profile.max_value == 20.0
    assert profile.min_length is None


def test_profile_string_lengths() -> None:
    """String columns report min and max lengths."""
    profile = profile_column("c", ["ab", "abcd"], 2)
    assert profile.min_length == 2
    assert profile.max_length == 4
    assert profile.min_value is None


def test_profile_samples_are_distinct_and_capped() -> None:
    """Up to five distinct values are sampled, in first-seen order."""
    profile = profile_column("c", ["a", "a", "b", "c", "d", "e", "f"], 7)
    assert profile.sample_values == ["a", "b", "c", "d", "e"]


def test_profile_all_null_column() -> None:
    """A column with no values infers as string without ranges."""
    profile = profile_column("c", ["", None], 2)
    assert profile.inferred_type == "string"
    assert profile.unique_count == 0
    assert profile.min_value is None


def test_inspect_file_counts_rows_and_columns(tmp_path: Path) -> None:
    """The report describes the file's shape."""
    path = tmp_path / "orders.csv"
    path.write_text(CSV_TEXT)
    report = inspect_file(path)
    assert report.row_count == 3
    assert report.column_count == 4
    assert report.file_name == "orders.csv"
    assert report.file_size > 0


def test_inspect_file_profiles_every_column(tmp_path: Path) -> None:
    """Each column gets a profile, in file order."""
    path = tmp_path / "orders.csv"
    path.write_text(CSV_TEXT)
    report = inspect_file(path)
    assert [c.name for c in report.columns] == [
        "order_id",
        "amount",
        "status",
        "note",
    ]


def test_inspect_file_flags_mixed_column(tmp_path: Path) -> None:
    """A column with one bad value is typed string with a float hint."""
    path = tmp_path / "orders.csv"
    path.write_text(CSV_TEXT)
    report = inspect_file(path)
    amount = next(c for c in report.columns if c.name == "amount")
    assert amount.inferred_type == "string"
    assert amount.dominant_type == "float"


def test_format_report_includes_column_names(tmp_path: Path) -> None:
    """The rendered table names every column."""
    path = tmp_path / "orders.csv"
    path.write_text(CSV_TEXT)
    output = format_report(inspect_file(path))
    assert "order_id" in output
    assert "parse as float" in output
