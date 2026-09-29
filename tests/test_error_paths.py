"""Tests for failure paths that require simulated errors."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pipeforge.exceptions import ReaderError, WriterError
from pipeforge.readers import read_csv
from pipeforge.writers import AtomicPath, write_csv, write_parquet


def test_atomic_path_mkstemp_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure creating the temporary file becomes WriterError."""

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise OSError("no space left on device")

    monkeypatch.setattr("pipeforge.writers.tempfile.mkstemp", fail)

    with pytest.raises(WriterError) as excinfo:
        with AtomicPath(tmp_path / "out.txt"):
            pass
    assert excinfo.value.context["path"].endswith("out.txt")


def test_atomic_path_replace_failure_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed rename raises and leaves no temporary file behind."""

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise OSError("cross-device link")

    monkeypatch.setattr("pipeforge.writers.os.replace", fail)

    with pytest.raises(WriterError):
        with AtomicPath(tmp_path / "out.txt") as tmp:
            tmp.write_text("data")

    assert list(tmp_path.iterdir()) == []


def test_atomic_path_calls_replace_with_temp_and_target(tmp_path: Path) -> None:
    """The rename moves the temporary file onto the target path."""
    target = tmp_path / "out.txt"

    with patch("pipeforge.writers.os.replace") as replace:
        with AtomicPath(target) as tmp:
            tmp.write_text("data")

    replace.assert_called_once()
    source_arg, target_arg = replace.call_args.args
    assert Path(target_arg) == target
    assert Path(source_arg).name.startswith(".out.txt.")


def test_read_csv_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unreadable file becomes ReaderError, not PermissionError."""
    path = tmp_path / "orders.csv"
    path.write_text("a,b\n1,2\n")

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "open", fail)

    with pytest.raises(ReaderError) as excinfo:
        list(read_csv(path))
    assert "Could not open" in excinfo.value.message


def test_write_csv_os_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A write failure becomes WriterError and writes no target file."""
    target = tmp_path / "out.csv"
    original_open = Path.open
    calls: list[int] = []

    def fail_on_write(self: Path, *args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        raise OSError("disk full")

    monkeypatch.setattr(Path, "open", fail_on_write)

    with pytest.raises(WriterError):
        write_csv([{"a": 1}], target)

    monkeypatch.setattr(Path, "open", original_open)
    assert not target.exists()


def test_write_parquet_rejects_unconvertible_data(tmp_path: Path) -> None:
    """Data pyarrow cannot type becomes WriterError before any file exists."""
    target = tmp_path / "out.parquet"

    with pytest.raises(WriterError):
        write_parquet([{"a": object()}], target)

    assert list(tmp_path.iterdir()) == []


def test_error_boundary_lets_bugs_propagate() -> None:
    """A non-PipeForge exception is not caught by the CLI boundary."""
    from pipeforge.cli import error_boundary

    with pytest.raises(NameError):
        with error_boundary():
            raise NameError("this is a bug, not a user error")


def test_inspect_command_reports_reader_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ReaderError inside a command exits 1 rather than crashing."""
    from typer.testing import CliRunner

    from pipeforge.cli import app

    path = tmp_path / "orders.csv"
    path.write_text("a,b\n1,2\n")

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise ReaderError("simulated failure", {"path": str(path)})

    monkeypatch.setattr("pipeforge.inspectors.read_file", fail)

    result = CliRunner().invoke(app, ["inspect", "--input", str(path)])
    assert result.exit_code == 1


def test_mock_records_arguments() -> None:
    """A MagicMock records how it was called."""
    mock = MagicMock(return_value=42)
    assert mock(1, key="value") == 42
    mock.assert_called_once_with(1, key="value")
