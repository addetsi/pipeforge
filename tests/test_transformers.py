"""Tests for data transformations."""

from datetime import date
from typing import Any

import pytest

from pipeforge.config import TransformRule
from pipeforge.exceptions import TransformError
from pipeforge.transformers import (
    add_column,
    apply_pipeline,
    cast_column,
    deduplicate,
    drop_columns,
    fill_nulls,
    filter_rows,
    register_transform,
    rename_columns,
    sort_data,
)


def test_transforms_do_not_mutate_input() -> None:
    """Every transform leaves the caller's data untouched."""
    data = [{"a": "1", "b": "2"}]
    original = [dict(row) for row in data]
    rename_columns(data, {"a": "x"})
    drop_columns(data, ["b"])
    cast_column(data, "a", "integer")
    filter_rows(data, "a", ">", 0)
    assert data == original


def test_rename_passes_through_unmapped_columns() -> None:
    """Columns absent from the mapping keep their names."""
    result = rename_columns([{"a": 1, "b": 2}], {"a": "x"})
    assert result == [{"x": 1, "b": 2}]


def test_rename_ignores_missing_source_column() -> None:
    """A mapping entry for an absent column is a no-op."""
    assert rename_columns([{"a": 1}], {"z": "y"}) == [{"a": 1}]


def test_drop_ignores_missing_column() -> None:
    """Dropping a column that is not present succeeds."""
    assert drop_columns([{"a": 1}], ["b"]) == [{"a": 1}]


def test_fill_nulls_replaces_empty_and_none() -> None:
    """Both empty strings and None are filled."""
    result = fill_nulls([{"a": ""}, {"a": None}, {"a": "x"}], "a", "z")
    assert [row["a"] for row in result] == ["z", "z", "x"]


def test_fill_nulls_missing_column_raises() -> None:
    """Filling an absent column is a config error."""
    with pytest.raises(TransformError):
        fill_nulls([{"a": 1}], "b", "z")


@pytest.mark.parametrize(
    ("value", "target_type", "expected"),
    [
        ("1200.00", "float", 1200.0),
        ("1001", "integer", 1001),
        (1200.0, "integer", 1200),
        (1001, "string", "1001"),
        ("yes", "boolean", True),
        ("0", "boolean", False),
    ],
)
def test_cast_column(value: Any, target_type: str, expected: Any) -> None:
    """Values are converted to the target type."""
    result = cast_column([{"a": value}], "a", target_type)  # type: ignore[arg-type]
    assert result[0]["a"] == expected


def test_cast_date_uses_format() -> None:
    """Dates are parsed with the supplied format."""
    result = cast_column([{"d": "15/01/2026"}], "d", "date", date_format="%d/%m/%Y")
    assert result[0]["d"] == date(2026, 1, 15)


def test_cast_preserves_nulls() -> None:
    """Null values become None rather than being coerced."""
    assert cast_column([{"a": ""}], "a", "float")[0]["a"] is None


def test_cast_failure_reports_row() -> None:
    """An unconvertible value names its row and column."""
    with pytest.raises(TransformError) as excinfo:
        cast_column([{"a": "1"}, {"a": "nope"}], "a", "float")
    assert excinfo.value.context["row"] == 2
    assert excinfo.value.context["column"] == "a"


def test_filter_compares_strings_to_numbers() -> None:
    """String data is coerced to match a numeric threshold."""
    data = [{"a": "1200.00"}, {"a": "-50.00"}]
    assert filter_rows(data, "a", ">", 0) == [{"a": "1200.00"}]


def test_filter_drops_nulls() -> None:
    """A null satisfies no comparison, matching SQL semantics."""
    assert filter_rows([{"a": ""}, {"a": "5"}], "a", ">", 0) == [{"a": "5"}]


def test_filter_unknown_operator_raises() -> None:
    """An unsupported operator lists the supported ones."""
    with pytest.raises(TransformError) as excinfo:
        filter_rows([{"a": 1}], "a", "~=", 1)
    assert "supported" in excinfo.value.context


def test_add_column_from_attribute() -> None:
    """A source.attribute expression reads an attribute of a value."""
    data = [{"d": date(2026, 1, 15)}]
    assert add_column(data, "y", "d.year")[0]["y"] == 2026


def test_add_column_literal() -> None:
    """An expression naming no column is treated as a constant."""
    assert add_column([{"a": 1}], "src", "manual")[0]["src"] == "manual"


def test_add_column_null_source_yields_none() -> None:
    """A null source value produces None rather than raising."""
    assert add_column([{"d": None}], "y", "d.year")[0]["y"] is None


def test_add_column_bad_attribute_raises() -> None:
    """An attribute the value does not have is an error."""
    with pytest.raises(TransformError):
        add_column([{"d": "2026-01-15"}], "y", "d.year")


def test_deduplicate_keeps_first_occurrence() -> None:
    """The earliest of a set of identical rows is kept."""
    data = [{"a": 1, "b": "x"}, {"a": 1, "b": "x"}, {"a": 2, "b": "y"}]
    assert deduplicate(data) == [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]


def test_deduplicate_subset() -> None:
    """A subset restricts which columns determine identity."""
    data = [{"a": 1, "b": "x"}, {"a": 1, "b": "y"}]
    assert deduplicate(data, subset=["a"]) == [{"a": 1, "b": "x"}]


def test_sort_nulls_last() -> None:
    """Nulls sort after real values in both directions."""
    data = [{"a": 2}, {"a": None}, {"a": 1}]
    assert [r["a"] for r in sort_data(data, ["a"])] == [1, 2, None]
    assert [r["a"] for r in sort_data(data, ["a"], ascending=False)] == [2, 1, None]


def test_sort_missing_column_raises() -> None:
    """Sorting by an absent column is an error."""
    with pytest.raises(TransformError):
        sort_data([{"a": 1}], ["b"])


@pytest.mark.parametrize(
    "transform",
    [rename_columns, drop_columns, deduplicate],
)
def test_transforms_handle_empty_data(transform: Any) -> None:
    """An empty dataset transforms to an empty dataset."""
    assert transform([], {} if transform is rename_columns else []) == []


def test_apply_pipeline_runs_in_order() -> None:
    """Each rule's output feeds the next rule."""
    rules = [
        TransformRule(operation="cast", params={"a": "float"}),
        TransformRule(
            operation="filter",
            params={"column": "a", "operator": ">", "value": 0},
        ),
    ]
    data = [{"a": "5"}, {"a": "-1"}]
    assert apply_pipeline(data, rules) == [{"a": 5.0}]


def test_apply_pipeline_unknown_operation() -> None:
    """An unregistered operation names the step and the alternatives."""
    with pytest.raises(TransformError) as excinfo:
        apply_pipeline([{"a": 1}], [TransformRule(operation="explode", params={})])
    assert excinfo.value.context["step"] == 1


def test_apply_pipeline_missing_parameter() -> None:
    """A rule missing a required param names the parameter."""
    with pytest.raises(TransformError) as excinfo:
        apply_pipeline([{"a": 1}], [TransformRule(operation="rename", params={})])
    assert "mapping" in excinfo.value.context["parameter"]


def test_apply_pipeline_does_not_mutate_input() -> None:
    """The original dataset survives a full pipeline."""
    data = [{"a": "5"}]
    apply_pipeline(data, [TransformRule(operation="cast", params={"a": "float"})])
    assert data == [{"a": "5"}]


def test_register_transform_adds_to_registry() -> None:
    """A new operation becomes usable by apply_pipeline."""
    register_transform("noop", lambda data, params: data)
    rules = [TransformRule(operation="noop", params={})]
    assert apply_pipeline([{"a": 1}], rules) == [{"a": 1}]


def test_register_duplicate_name_raises() -> None:
    """Registering over an existing name is rejected."""
    with pytest.raises(TransformError):
        register_transform("rename", lambda data, params: data)


def test_decorator_preserves_metadata() -> None:
    """functools.wraps keeps the wrapped function's identity."""
    assert rename_columns.__name__ == "rename_columns"
    assert rename_columns.__doc__ is not None
