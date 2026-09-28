"""Tests for file writers."""

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from pipeforge.exceptions import WriterError
from pipeforge.readers import read_file
from pipeforge.writers import (
    AtomicPath,
    write_csv,
    write_file,
    write_json,
    write_parquet,
)

DATA: list[dict[str, Any]] = [
    {"id": 1, "when": date(2026, 1, 15), "name": "Díaz", "note": None},
    {"id": 2, "when": date(2026, 1, 16), "name": "Chen", "extra": "only here"},
]


def test_atomic_write_creates_parent_directory(tmp_path: Path) -> None:
    """A missing output directory is created."""
    target = tmp_path / "nested" / "deep" / "out.txt"
    with AtomicPath(target) as tmp:
        tmp.write_text("data")
    assert target.read_text() == "data"


def test_atomic_write_leaves_target_untouched_on_failure(tmp_path: Path) -> None:
    """A failure inside the block does not modify an existing target."""
    target = tmp_path / "out.txt"
    target.write_text("original")

    with pytest.raises(RuntimeError):
        with AtomicPath(target) as tmp:
            tmp.write_text("partial")
            raise RuntimeError("boom")

    assert target.read_text() == "original"


def test_atomic_write_removes_temp_file_on_failure(tmp_path: Path) -> None:
    """No temporary file survives a failed write."""
    target = tmp_path / "out.txt"
    with pytest.raises(RuntimeError):
        with AtomicPath(target) as tmp:
            tmp.write_text("partial")
            raise RuntimeError("boom")
    assert list(tmp_path.iterdir()) == []


def test_atomic_write_overwrites_existing(tmp_path: Path) -> None:
    """A successful write replaces an existing file."""
    target = tmp_path / "out.txt"
    target.write_text("old")
    with AtomicPath(target) as tmp:
        tmp.write_text("new")
    assert target.read_text() == "new"


def test_atomic_write_does_not_suppress_exceptions(tmp_path: Path) -> None:
    """Exceptions inside the block propagate to the caller."""
    with pytest.raises(ValueError):
        with AtomicPath(tmp_path / "out.txt"):
            raise ValueError("propagate me")


@pytest.mark.parametrize("extension", ["csv", "json", "parquet"])
def test_round_trip_preserves_row_count(tmp_path: Path, extension: str) -> None:
    """Data written and read back has the same number of rows."""
    path = tmp_path / f"out.{extension}"
    write_file(DATA, path)
    assert len(list(read_file(path))) == len(DATA)


@pytest.mark.parametrize("extension", ["csv", "json", "parquet"])
def test_all_formats_write_the_same_columns(tmp_path: Path, extension: str) -> None:
    """A column present in only one row is written by every format."""
    path = tmp_path / f"out.{extension}"
    write_file(DATA, path)
    first = next(iter(read_file(path)))
    assert set(first) == {"id", "when", "name", "note", "extra"}


def test_csv_writes_dates_as_iso(tmp_path: Path) -> None:
    """Date objects are written in ISO format, not repr."""
    path = tmp_path / "out.csv"
    write_csv(DATA, path)
    assert "2026-01-15" in path.read_text()


def test_json_writes_unicode_unescaped(tmp_path: Path) -> None:
    """Non-ASCII characters are written as UTF-8, not escape sequences."""
    path = tmp_path / "out.json"
    write_json(DATA, path)
    assert "Díaz" in path.read_text(encoding="utf-8")


def test_parquet_preserves_date_type(tmp_path: Path) -> None:
    """Parquet round-trips a date as a date, not a string."""
    path = tmp_path / "out.parquet"
    write_parquet(DATA, path)
    assert next(iter(read_file(path)))["when"] == date(2026, 1, 15)


def test_json_rejects_unserializable_value(tmp_path: Path) -> None:
    """A value JSON cannot represent raises WriterError."""
    with pytest.raises(WriterError):
        write_json([{"a": object()}], tmp_path / "out.json")


def test_write_file_unknown_extension_raises(tmp_path: Path) -> None:
    """An unsupported extension is reported with the suffix."""
    with pytest.raises(WriterError) as excinfo:
        write_file(DATA, tmp_path / "out.xlsx")
    assert excinfo.value.context["suffix"] == ".xlsx"


def test_write_file_explicit_format_wins(tmp_path: Path) -> None:
    """An explicit format overrides extension inference."""
    path = tmp_path / "out.txt"
    write_file(DATA, path, file_format="json")
    assert path.read_text(encoding="utf-8").lstrip().startswith("[")


def test_empty_data_writes_header_only(tmp_path: Path) -> None:
    """An empty dataset produces a file with no rows."""
    path = tmp_path / "out.csv"
    write_csv([], path)
    assert path.exists()
    assert list(read_file(path)) == []
