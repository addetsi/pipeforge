"""File readers for PipeForge.

Readers yield rows lazily as dictionaries. Callers that need random
access or multiple passes should materialize with list().
"""

import csv
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from pipeforge.config import FileFormat
from pipeforge.exceptions import ReaderError
from pipeforge.logger import get_logger

logger = get_logger(__name__)


def read_csv(path: Path, encoding: str = "utf-8") -> Iterator[dict[str, Any]]:
    """Yield rows from a CSV file as dictionaries.

    The first line is treated as the header and supplies the keys. All
    values are strings, since CSV carries no type information.

    Args:
        path: Path to the CSV file.
        encoding: Text encoding of the file.

    Yields:
        One dictionary per data row, keyed by column name.

    Raises:
        ReaderError: If the file is missing, unreadable, wrongly encoded,
            or has no header row.
    """
    try:
        handle = path.open(newline="", encoding=encoding)
    except FileNotFoundError as e:
        raise ReaderError("File not found", {"path": str(path)}) from e
    except OSError as e:
        raise ReaderError("Could not open file", {"path": str(path)}) from e

    with handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ReaderError("File has no header row", {"path": str(path)})

        try:
            for row in reader:
                yield dict(row)
        except UnicodeDecodeError as e:
            raise ReaderError(
                "Could not decode file",
                {"path": str(path), "encoding": encoding, "line": reader.line_num},
            ) from e
        except csv.Error as e:
            raise ReaderError(
                "Malformed CSV", {"path": str(path), "line": reader.line_num}
            ) from e


def read_json(path: Path, encoding: str = "utf-8") -> Iterator[dict[str, Any]]:
    """Yield rows from a JSON or JSON Lines file.

    A ``.jsonl`` file is parsed one line at a time and streams lazily.
    A ``.json`` file must contain a top-level array of objects, and is
    parsed in full before the first row is yielded.

    Args:
        path: Path to the JSON or JSON Lines file.
        encoding: Text encoding of the file.

    Yields:
        One dictionary per record.

    Raises:
        ReaderError: If the file is missing, unreadable, not valid JSON,
            or does not contain objects at the top level.
    """
    if path.suffix == ".jsonl":
        yield from _read_jsonl(path, encoding)
        return

    try:
        text = path.read_text(encoding=encoding)
    except FileNotFoundError as e:
        raise ReaderError("File not found", {"path": str(path)}) from e
    except OSError as e:
        raise ReaderError("Could not read file", {"path": str(path)}) from e
    except UnicodeDecodeError as e:
        raise ReaderError(
            "Could not decode file", {"path": str(path), "encoding": encoding}
        ) from e

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ReaderError(
            "Invalid JSON", {"path": str(path), "line": e.lineno, "column": e.colno}
        ) from e

    if not isinstance(data, list):
        raise ReaderError("Top level must be an array", {"path": str(path)})

    for index, record in enumerate(data):
        if not isinstance(record, dict):
            raise ReaderError(
                "Array element is not an object",
                {"path": str(path), "index": index, "type": type(record).__name__},
            )
        yield record


def _read_jsonl(path: Path, encoding: str) -> Iterator[dict[str, Any]]:
    """Yield rows from a JSON Lines file, one object per line."""
    try:
        handle = path.open(encoding=encoding)
    except FileNotFoundError as e:
        raise ReaderError("File not found", {"path": str(path)}) from e
    except OSError as e:
        raise ReaderError("Could not open file", {"path": str(path)}) from e

    with handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as e:
                raise ReaderError(
                    "Invalid JSON on line",
                    {"path": str(path), "line": line_number},
                ) from e
            if not isinstance(record, dict):
                raise ReaderError(
                    "Line is not an object",
                    {"path": str(path), "line": line_number},
                )
            yield record


def read_parquet(path: Path, batch_size: int = 10_000) -> Iterator[dict[str, Any]]:
    """Yield rows from a Parquet file as dictionaries.

    The file is read in batches so that memory use stays flat regardless
    of file size. Parquet stores type information, so values arrive as
    their declared types rather than as strings.

    Args:
        path: Path to the Parquet file.
        batch_size: Number of rows to read into memory at a time.

    Yields:
        One dictionary per row, keyed by column name.

    Raises:
        ReaderError: If the file is missing, unreadable, or not valid Parquet.
    """
    try:
        parquet_file = pq.ParquetFile(path)
    except FileNotFoundError as e:
        raise ReaderError("File not found", {"path": str(path)}) from e
    except OSError as e:
        raise ReaderError("Could not read file", {"path": str(path)}) from e
    except pa.ArrowInvalid as e:
        raise ReaderError("Not a valid Parquet file", {"path": str(path)}) from e

    for batch in parquet_file.iter_batches(batch_size=batch_size):
        yield from batch.to_pylist()


_READERS: dict[FileFormat, Callable[[Path], Iterator[dict[str, Any]]]] = {
    "csv": read_csv,
    "json": read_json,
    "parquet": read_parquet,
}

_EXTENSIONS: dict[str, FileFormat] = {
    ".csv": "csv",
    ".json": "json",
    ".jsonl": "json",
    ".parquet": "parquet",
}


def read_file(
    path: Path, file_format: FileFormat | None = None
) -> Iterator[dict[str, Any]]:
    """Read a data file, dispatching on its format.

    Args:
        path: Path to the data file.
        file_format: Format to read as. If omitted, inferred from the
            file extension.

    Yields:
        One dictionary per row.

    Raises:
        ReaderError: If the format is unsupported or cannot be inferred,
            or if the underlying reader fails.
    """
    resolved = file_format or infer_format(path)
    reader = _READERS[resolved]
    logger.debug("Reading %s as %s", path, resolved)
    yield from reader(path)


def infer_format(path: Path) -> FileFormat:
    """Determine the file format from a path's extension."""
    try:
        return _EXTENSIONS[path.suffix.lower()]
    except KeyError:
        raise ReaderError(
            "Cannot infer format from extension",
            {"path": str(path), "suffix": path.suffix},
        ) from None
