"""Data transformation functions.

Every transform is a pure function: it takes a dataset and returns a new
one, never mutating its input. Rows are copied one level deep, which is
sufficient because row values are scalars.
"""

import functools
import operator
import time
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from pipeforge.config import DataType, TransformRule
from pipeforge.exceptions import TransformError
from pipeforge.logger import get_logger
from pipeforge.utils import is_null

logger = get_logger(__name__)

Row = dict[str, Any]
Data = list[Row]


def log_transform(func: Callable[..., Data]) -> Callable[..., Data]:
    """Log a transform's name, row counts, and duration.

    Wraps a transform function so that every call reports how many rows
    went in, how many came out, and how long it took.

    Args:
        func: The transform to wrap. Its first argument must be the dataset.

    Returns:
        The wrapped transform.
    """

    @functools.wraps(func)
    def wrapper(data: Data, *args: Any, **kwargs: Any) -> Data:
        started = time.perf_counter()
        result = func(data, *args, **kwargs)
        elapsed = time.perf_counter() - started
        logger.debug(
            "%s: %d rows in, %d rows out, %.3fs",
            func.__name__,
            len(data),
            len(result),
            elapsed,
        )
        return result

    return wrapper


def rename_columns(data: Data, mapping: dict[str, str]) -> Data:
    """Rename columns according to a mapping.

    Columns not present in the mapping are passed through unchanged.
    A mapping entry naming a column that does not exist is ignored.

    Args:
        data: The rows to transform.
        mapping: Old column name to new column name.

    Returns:
        A new dataset with renamed keys.
    """
    return [
        {mapping.get(key, key): value for key, value in row.items()} for row in data
    ]


def drop_columns(data: Data, columns: list[str]) -> Data:
    """Remove columns from every row.

    Columns that are not present are ignored rather than raising.

    Args:
        data: The rows to transform.
        columns: Names of columns to remove.

    Returns:
        A new dataset without the named columns.
    """
    unwanted = set(columns)
    return [
        {key: value for key, value in row.items() if key not in unwanted}
        for row in data
    ]


def fill_nulls(data: Data, column: str, value: Any) -> Data:
    """Replace null values in a column with a given value.

    Both None and empty strings are treated as null, matching the
    validator's definition.

    Args:
        data: The rows to transform.
        column: The column to fill.
        value: The replacement value.

    Returns:
        A new dataset with nulls replaced.

    Raises:
        TransformError: If the column is not present in the data.
    """
    _require_column(data, column)
    return [
        {**row, column: value if is_null(row.get(column)) else row[column]}
        for row in data
    ]


def _require_column(data: Data, column: str) -> None:
    """Raise if a column is absent from the dataset.

    Args:
        data: The rows to check. An empty dataset passes.
        column: The column that must be present.

    Raises:
        TransformError: If the column is missing.
    """
    if not data:
        return
    if column not in data[0]:
        raise TransformError(
            "Column not found",
            {"column": column, "available": ", ".join(sorted(data[0]))},
        )


def cast_column(
    data: Data, column: str, target_type: DataType, date_format: str | None = None
) -> Data:
    """Convert every value in a column to a target type.

    Null values are left as None rather than being coerced.

    Args:
        data: The rows to transform.
        column: The column to cast.
        target_type: The type to convert to.
        date_format: strptime format for date casts. Defaults to ISO.

    Returns:
        A new dataset with the column converted.

    Raises:
        TransformError: If the column is missing or a value cannot be
            converted.
    """
    _require_column(data, column)
    result: Data = []
    for row_number, row in enumerate(data, start=1):
        raw = row.get(column)
        if is_null(raw):
            result.append({**row, column: None})
            continue
        try:
            result.append({**row, column: _cast(raw, target_type, date_format)})
        except (ValueError, TypeError) as e:
            raise TransformError(
                "Could not cast value",
                {
                    "column": column,
                    "row": row_number,
                    "value": repr(raw),
                    "target_type": target_type,
                },
            ) from e
    return result


def _cast(value: Any, target_type: DataType, date_format: str | None) -> Any:
    """Convert a single non-null value to the target type."""
    if target_type == "string":
        return str(value)
    if target_type == "integer":
        return int(float(value)) if isinstance(value, float) else int(value)
    if target_type == "float":
        return float(value)
    if target_type == "boolean":
        return _to_bool(value)
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value).strip(), date_format or "%Y-%m-%d").date()


def _to_bool(value: Any) -> bool:
    """Convert a value to a boolean, accepting common string spellings."""
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "yes", "1"}:
        return True
    if text in {"false", "no", "0"}:
        return False
    raise ValueError(f"not a boolean: {value!r}")


_OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
}


def filter_rows(data: Data, column: str, op: str, value: Any) -> Data:
    """Keep only rows where a column satisfies a comparison.

    Rows whose value is null are dropped, since a null satisfies no
    comparison. Values are coerced to the type of the comparison value
    before comparing, so string data from CSV compares correctly against
    numeric thresholds from config.

    Args:
        data: The rows to filter.
        column: The column to compare.
        op: One of ==, !=, >, >=, <, <=.
        value: The value to compare against.

    Returns:
        A new dataset containing only matching rows.

    Raises:
        TransformError: If the column is missing or the operator is
            unknown.
    """
    _require_column(data, column)
    try:
        compare = _OPERATORS[op]
    except KeyError:
        raise TransformError(
            "Unknown operator",
            {"operator": op, "supported": ", ".join(sorted(_OPERATORS))},
        ) from None

    kept: Data = []
    for row in data:
        raw = row.get(column)
        if is_null(raw):
            continue
        try:
            if compare(_coerce_like(raw, value), value):
                kept.append(dict(row))
        except TypeError:
            continue
    return kept


def _coerce_like(raw: Any, reference: Any) -> Any:
    """Convert a raw value to the type of a reference value where possible."""
    if isinstance(reference, bool) or not isinstance(reference, (int, float)):
        return raw
    if isinstance(raw, str):
        return float(raw.strip())
    return raw


@log_transform
def add_column(data: Data, name: str, expression: str) -> Data:
    """Add a column derived from a simple expression.

    The expression is either a literal value, or ``source.attribute`` to
    read an attribute of another column's value — for example
    ``order_date.year`` on a column holding date objects. Arbitrary Python
    is deliberately not evaluated.

    Args:
        data: The rows to transform.
        name: The name of the new column.
        expression: A literal, or ``source.attribute``.

    Returns:
        A new dataset with the column added.

    Raises:
        TransformError: If the expression names a missing column or
            attribute.
    """
    source, _, attribute = expression.partition(".")
    if not attribute or (data and source not in data[0]):
        return [{**row, name: expression} for row in data]

    result: Data = []
    for row_number, row in enumerate(data, start=1):
        value = row.get(source)
        if is_null(value):
            result.append({**row, name: None})
            continue
        try:
            result.append({**row, name: getattr(value, attribute)})
        except AttributeError as e:
            raise TransformError(
                "Attribute not available on value",
                {
                    "column": source,
                    "attribute": attribute,
                    "row": row_number,
                    "value_type": type(value).__name__,
                },
            ) from e
    return result


@log_transform
def deduplicate(data: Data, subset: list[str] | None = None) -> Data:
    """Remove rows that repeat an earlier row.

    The first occurrence is kept and later ones dropped.

    Args:
        data: The rows to transform.
        subset: Columns that determine identity. When omitted, the whole
            row is compared.

    Returns:
        A new dataset without duplicates.
    """
    seen: set[tuple[Any, ...]] = set()
    kept: Data = []
    for row in data:
        key: tuple[Any, ...]
        if subset is None:
            key = tuple(sorted(row.items()))
        else:
            key = tuple(row.get(name) for name in subset)
        if key in seen:
            continue
        seen.add(key)
        kept.append(dict(row))
    return kept


@log_transform
def sort_data(data: Data, columns: list[str], ascending: bool = True) -> Data:
    """Sort rows by one or more columns.

    Null values sort last regardless of direction. Values of mixed types
    are compared by their string form to avoid TypeError.

    Args:
        data: The rows to sort.
        columns: Columns to sort by, in priority order.
        ascending: Sort direction.

    Returns:
        A new, sorted dataset.

    Raises:
        TransformError: If a named column is missing.
    """
    for column in columns:
        _require_column(data, column)

    # reverse=True flips the null flag too, so invert it for descending sorts
    null_rank = 1 if ascending else -1

    def key(row: Row) -> tuple[Any, ...]:
        parts: list[Any] = []
        for column in columns:
            value = row.get(column)
            parts.append((null_rank, "") if is_null(value) else (0, _sortable(value)))
        return tuple(parts)

    return [dict(row) for row in sorted(data, key=key, reverse=not ascending)]


def _sortable(value: Any) -> Any:
    """Return a value in a form that compares consistently."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return str(value)


TransformFunc = Callable[[Data, dict[str, Any]], Data]


def _apply_rename(data: Data, params: dict[str, Any]) -> Data:
    """Adapt config params to rename_columns."""
    return rename_columns(data, params["mapping"])


def _apply_cast(data: Data, params: dict[str, Any]) -> Data:
    """Adapt config params to cast_column, one column at a time."""
    result = data
    for column, target_type in params.items():
        result = cast_column(result, column, target_type)
    return result


def _apply_filter(data: Data, params: dict[str, Any]) -> Data:
    """Adapt config params to filter_rows."""
    return filter_rows(data, params["column"], params["operator"], params["value"])


def _apply_add_column(data: Data, params: dict[str, Any]) -> Data:
    """Adapt config params to add_column."""
    return add_column(data, params["name"], params["expression"])


def _apply_drop_column(data: Data, params: dict[str, Any]) -> Data:
    """Adapt config params to drop_columns."""
    return drop_columns(data, params["columns"])


def _apply_deduplicate(data: Data, params: dict[str, Any]) -> Data:
    """Adapt config params to deduplicate."""
    return deduplicate(data, params.get("subset"))


def _apply_sort(data: Data, params: dict[str, Any]) -> Data:
    """Adapt config params to sort_data."""
    return sort_data(data, params["columns"], params.get("ascending", True))


def _apply_fill_nulls(data: Data, params: dict[str, Any]) -> Data:
    """Adapt config params to fill_nulls."""
    return fill_nulls(data, params["column"], params["value"])


_TRANSFORMS: dict[str, TransformFunc] = {
    "rename": _apply_rename,
    "cast": _apply_cast,
    "filter": _apply_filter,
    "add_column": _apply_add_column,
    "drop_column": _apply_drop_column,
    "deduplicate": _apply_deduplicate,
    "sort": _apply_sort,
    "fill_nulls": _apply_fill_nulls,
}


def register_transform(name: str, func: TransformFunc) -> None:
    """Add a transform to the registry.

    Args:
        name: The operation name used in pipeline configs.
        func: A function taking a dataset and a params dict.

    Raises:
        TransformError: If the name is already registered.
    """
    if name in _TRANSFORMS:
        raise TransformError("Transform already registered", {"operation": name})
    _TRANSFORMS[name] = func


def apply_pipeline(data: Data, transforms: list[TransformRule]) -> Data:
    """Apply a sequence of transform rules in order.

    Each rule's output becomes the next rule's input. The input dataset
    is not modified.

    Args:
        data: The rows to transform.
        transforms: The rules to apply, in order.

    Returns:
        The transformed dataset.

    Raises:
        TransformError: If an operation is unknown, a required parameter
            is missing, or a transform fails.
    """
    result = data
    for step, rule in enumerate(transforms, start=1):
        try:
            func = _TRANSFORMS[rule.operation]
        except KeyError:
            raise TransformError(
                "Unknown transform operation",
                {
                    "step": step,
                    "operation": rule.operation,
                    "supported": ", ".join(sorted(_TRANSFORMS)),
                },
            ) from None

        try:
            result = func(result, rule.params)
        except KeyError as e:
            raise TransformError(
                "Missing required parameter",
                {"step": step, "operation": rule.operation, "parameter": str(e)},
            ) from e

    logger.info(
        "Applied %d transforms: %d rows in, %d rows out",
        len(transforms),
        len(data),
        len(result),
    )
    return result
