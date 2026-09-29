"""File writers for PipeForge.

All writers write atomically: output goes to a temporary file in the
target directory and is renamed into place only on success.
"""

import csv
import json
import os
import tempfile
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from types import TracebackType
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from pipeforge.config import FileFormat
from pipeforge.exceptions import WriterError
from pipeforge.logger import get_logger
from pipeforge.utils import Data

logger = get_logger(__name__)


__all__ = [
    "AtomicPath",
    "write_csv",
    "write_file",
    "write_json",
    "write_parquet",
]


def _fieldnames(data: Data) -> list[str]:
    """Return every column name across all rows, in first-seen order."""
    names: dict[str, None] = {}
    for row in data:
        for key in row:
            names[key] = None
    return list(names)


def _serialize(value: Any) -> Any:
    """Convert a value to something a text format can represent."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def write_csv(data: Data, path: Path, options: dict[str, Any] | None = None) -> None:
    """Write rows to a CSV file.

    Columns are the union of keys across all rows, in first-seen order.
    Rows missing a column are written with an empty value. Dates are
    written in ISO format.

    Args:
        data: The rows to write.
        path: Destination file path.
        options: Optional settings. Supports ``encoding`` and ``delimiter``.

    Raises:
        WriterError: If the file cannot be written.
    """
    settings = options or {}
    fieldnames = _fieldnames(data)

    with AtomicPath(path) as tmp:
        try:
            with tmp.open(
                "w", newline="", encoding=settings.get("encoding", "utf-8")
            ) as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=fieldnames,
                    delimiter=settings.get("delimiter", ","),
                    restval="",
                )
                writer.writeheader()
                for row in data:
                    writer.writerow({k: _serialize(v) for k, v in row.items()})
        except OSError as e:
            raise WriterError("Could not write CSV", {"path": str(path)}) from e

    logger.info("Wrote %d rows to %s", len(data), path)


def write_json(data: Data, path: Path, options: dict[str, Any] | None = None) -> None:
    """Write rows to a JSON file as an array of objects.

    Rows are normalized to the union of all column names, so a column
    present in only some rows appears in every object. Dates and
    datetimes are serialized in ISO format.

    Args:
        data: The rows to write.
        path: Destination file path.
        options: Optional settings. Supports ``encoding`` and ``indent``.

    Raises:
        WriterError: If the file cannot be written or a value cannot be
            serialized.
    """
    settings = options or {}
    fieldnames = _fieldnames(data)
    normalized = [{name: row.get(name) for name in fieldnames} for row in data]

    with AtomicPath(path) as tmp:
        try:
            with tmp.open("w", encoding=settings.get("encoding", "utf-8")) as handle:
                json.dump(
                    normalized,
                    handle,
                    indent=settings.get("indent", 2),
                    default=_json_default,
                    ensure_ascii=False,
                )
        except OSError as e:
            raise WriterError("Could not write JSON", {"path": str(path)}) from e
        except TypeError as e:
            raise WriterError(
                "Value is not JSON serializable", {"path": str(path)}
            ) from e

    logger.info("Wrote %d rows to %s", len(data), path)


def _json_default(value: Any) -> Any:
    """Serialize values the json module does not handle natively."""
    serialized = _serialize(value)
    if serialized is value and not isinstance(value, (str, int, float, bool)):
        raise TypeError(f"not serializable: {type(value).__name__}")
    return serialized


def write_parquet(
    data: Data, path: Path, options: dict[str, Any] | None = None
) -> None:
    """Write rows to a Parquet file.

    Rows are normalized to the union of all column names before writing,
    so a column present in only some rows is not dropped. The schema is
    inferred from the normalized data, and types are preserved — dates
    stay dates rather than becoming strings.

    Args:
        data: The rows to write.
        path: Destination file path.
        options: Optional settings. Supports ``compression``.

    Raises:
        WriterError: If the data cannot be converted or written.
    """
    settings = options or {}

    try:
        fieldnames = _fieldnames(data)
        normalized = [{name: row.get(name) for name in fieldnames} for row in data]
        table = pa.Table.from_pylist(normalized)
    except (pa.ArrowInvalid, pa.ArrowTypeError) as e:
        raise WriterError("Could not build Parquet table", {"path": str(path)}) from e

    with AtomicPath(path) as tmp:
        try:
            pq.write_table(
                table, tmp, compression=settings.get("compression", "snappy")
            )
        except (OSError, pa.ArrowException) as e:
            raise WriterError("Could not write Parquet", {"path": str(path)}) from e

    logger.info("Wrote %d rows to %s", len(data), path)


_WRITERS: dict[FileFormat, Callable[[Data, Path, dict[str, Any] | None], None]] = {
    "csv": write_csv,
    "json": write_json,
    "parquet": write_parquet,
}


def write_file(
    data: Data,
    path: Path,
    file_format: FileFormat | None = None,
    options: dict[str, Any] | None = None,
) -> None:
    """Write rows to a file, dispatching on format.

    Args:
        data: The rows to write.
        path: Destination file path.
        file_format: Format to write. Inferred from the extension if omitted.
        options: Format-specific settings.

    Raises:
        WriterError: If the format is unsupported or the write fails.
    """
    resolved = file_format or _infer_format(path)
    _WRITERS[resolved](data, path, options)


_EXTENSIONS: dict[str, FileFormat] = {
    ".csv": "csv",
    ".json": "json",
    ".parquet": "parquet",
}


def _infer_format(path: Path) -> FileFormat:
    """Determine the output format from a path's extension."""
    try:
        return _EXTENSIONS[path.suffix.lower()]
    except KeyError:
        raise WriterError(
            "Cannot infer format from extension",
            {"path": str(path), "suffix": path.suffix},
        ) from None


class AtomicPath:
    r"""Provide a temporary path that is renamed onto the target on success.

    The target's parent directory is created if needed. If the ``with``
    block raises, the temporary file is removed and the target is left
    untouched.

    Example:
        >>> with AtomicPath(Path("out/data.csv")) as tmp:
        ...     tmp.write_text("a,b\\n1,2\\n")

    Attributes:
        target: The final path the file will occupy.
    """

    def __init__(self, target: Path) -> None:
        """Store the target path.

        Args:
            target: Where the finished file should end up.
        """
        self.target = target
        self._temp_path: Path | None = None

    def __enter__(self) -> Path:
        """Create the temporary file and return its path.

        Returns:
            A path to an empty temporary file in the target's directory.

        Raises:
            WriterError: If the directory cannot be created or the
                temporary file cannot be opened.
        """
        try:
            self.target.parent.mkdir(parents=True, exist_ok=True)
            handle, name = tempfile.mkstemp(
                dir=self.target.parent,
                prefix=f".{self.target.name}.",
                suffix=".tmp",
            )
        except OSError as e:
            raise WriterError(
                "Could not prepare output location", {"path": str(self.target)}
            ) from e
        os.close(handle)
        self._temp_path = Path(name)
        return self._temp_path

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Rename the temporary file into place, or discard it on failure.

        Args:
            exc_type: The exception class raised in the block, if any.
            exc: The exception instance, if any.
            traceback: The traceback, if any.

        Raises:
            WriterError: If the rename fails.
        """
        if self._temp_path is None:
            return

        if exc_type is not None:
            self._temp_path.unlink(missing_ok=True)
            logger.debug("Discarded temporary file for %s", self.target)
            return

        try:
            os.replace(self._temp_path, self.target)
        except OSError as e:
            self._temp_path.unlink(missing_ok=True)
            raise WriterError(
                "Could not move file into place", {"path": str(self.target)}
            ) from e
