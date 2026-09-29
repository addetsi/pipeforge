"""Tests for file readers."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from pipeforge.exceptions import ReaderError
from pipeforge.readers import read_csv, read_json, read_parquet

CSV_TEXT = """order_id,amount,status
1001,1200.00,completed
1002,800.00,pending
"""

JSON_TEXT = (
    '[{"order_id": 1001, "amount": 1200.0}, {"order_id": 1002, "amount": 800.0}]'
)

JSONL_TEXT = '{"order_id": 1001}\n\n{"order_id": 1002}\n'


def test_read_csv_yields_dicts(tmp_path: Path) -> None:
    """Each data row becomes a dictionary keyed by header name."""
    path = tmp_path / "orders.csv"
    path.write_text(CSV_TEXT)
    rows = list(read_csv(path))
    assert len(rows) == 2
    assert rows[0] == {"order_id": "1001", "amount": "1200.00", "status": "completed"}


def test_read_csv_values_are_strings(tmp_path: Path) -> None:
    """CSV carries no type information, so every value is a string."""
    path = tmp_path / "orders.csv"
    path.write_text(CSV_TEXT)
    row = next(read_csv(path))
    assert all(isinstance(value, str) for value in row.values())


def test_read_csv_is_lazy(tmp_path: Path) -> None:
    """Calling the reader does not open the file."""
    missing = tmp_path / "nope.csv"
    generator = read_csv(missing)
    assert isinstance(generator, Iterator)
    with pytest.raises(ReaderError):
        next(generator)


def test_read_csv_empty_file_raises(tmp_path: Path) -> None:
    """A file with no header row is rejected."""
    path = tmp_path / "empty.csv"
    path.write_text("")
    with pytest.raises(ReaderError) as excinfo:
        list(read_csv(path))
    assert "header" in excinfo.value.message.lower()


def test_read_json_array(tmp_path: Path) -> None:
    """A top-level array of objects yields one dict per element."""
    path = tmp_path / "orders.json"
    path.write_text(JSON_TEXT)
    rows = list(read_json(path))
    assert len(rows) == 2
    assert rows[0]["order_id"] == 1001


def test_read_json_preserves_numeric_types(tmp_path: Path) -> None:
    """JSON numbers arrive as ints and floats, not strings."""
    path = tmp_path / "orders.json"
    path.write_text(JSON_TEXT)
    row = next(read_json(path))
    assert isinstance(row["order_id"], int)
    assert isinstance(row["amount"], float)


def test_read_jsonl_skips_blank_lines(tmp_path: Path) -> None:
    """Blank lines in a JSON Lines file are ignored."""
    path = tmp_path / "orders.jsonl"
    path.write_text(JSONL_TEXT)
    rows = list(read_json(path))
    assert len(rows) == 2


def test_read_json_invalid_reports_line(tmp_path: Path) -> None:
    """A syntax error includes the line number in context."""
    path = tmp_path / "bad.json"
    path.write_text('[{"a": 1},]')
    with pytest.raises(ReaderError) as excinfo:
        list(read_json(path))
    assert "line" in excinfo.value.context


def test_read_json_rejects_non_array(tmp_path: Path) -> None:
    """A top-level object is not tabular data."""
    path = tmp_path / "obj.json"
    path.write_text('{"a": 1}')
    with pytest.raises(ReaderError):
        list(read_json(path))


def test_read_json_rejects_non_object_elements(tmp_path: Path) -> None:
    """An array of scalars is not tabular data."""
    path = tmp_path / "scalars.json"
    path.write_text("[1, 2, 3]")
    with pytest.raises(ReaderError) as excinfo:
        list(read_json(path))
        assert excinfo.value.context["index"] == 0


def test_read_jsonl_invalid_line_reports_number(tmp_path: Path) -> None:
    """A malformed line in a JSON Lines file names its line number."""
    path = tmp_path / "bad.jsonl"
    path.write_text('{"a": 1}\n{invalid}\n')
    with pytest.raises(ReaderError) as excinfo:
        list(read_json(path))
    assert excinfo.value.context["line"] == 2


def test_read_jsonl_non_object_line_raises(tmp_path: Path) -> None:
    """A line holding a scalar is not tabular data."""
    path = tmp_path / "scalar.jsonl"
    path.write_text('{"a": 1}\n42\n')
    with pytest.raises(ReaderError) as excinfo:
        list(read_json(path))
    assert excinfo.value.context["line"] == 2


def test_read_jsonl_missing_file_raises(tmp_path: Path) -> None:
    """A missing JSON Lines file raises ReaderError."""
    with pytest.raises(ReaderError):
        list(read_json(tmp_path / "nope.jsonl"))


def test_read_parquet_missing_file_raises(tmp_path: Path) -> None:
    """A missing Parquet file raises ReaderError."""
    with pytest.raises(ReaderError):
        list(read_parquet(tmp_path / "nope.parquet"))


def test_read_file_unreadable_json_raises(tmp_path: Path) -> None:
    """A JSON file with a bad encoding is reported, not crashed on."""
    path = tmp_path / "bad.json"
    path.write_bytes(b"\xff\xfe invalid utf-8")
    with pytest.raises(ReaderError):
        list(read_json(path))
