"""Tests for configuration models and YAML loading."""

from pathlib import Path

import pydantic
import pytest

from pipeforge.config import (
    ColumnSchema,
    PipelineConfig,
    load_pipeline_config,
    load_schema,
    load_yaml,
)
from pipeforge.exceptions import ConfigError, SchemaError

SCHEMA_YAML = """
name: orders
description: Order data schema
columns:
  - name: order_id
    data_type: integer
  - name: amount
    data_type: float
    min_value: 0
primary_key:
  - order_id
"""
PIPELINE_YAML = """
name: orders_pipeline
description: Clean orders
input_format: csv
output_format: parquet
schema_path: config/orders_schema.yml
transforms:
  - operation: rename
    params:
      mapping:
        orderDate: order_date
  - operation: deduplicate
"""


def test_load_pipeline_config_parses_transforms(tmp_path: Path) -> None:
    """A valid pipeline file produces typed transform rules."""
    path = tmp_path / "pipeline.yml"
    path.write_text(PIPELINE_YAML)
    config = load_pipeline_config(path)
    assert config.name == "orders_pipeline"
    assert len(config.transforms) == 2
    assert config.transforms[1].params == {}


def test_load_pipeline_config_invalid_format(tmp_path: Path) -> None:
    """An unsupported format raises ConfigError with details."""
    path = tmp_path / "bad.yml"
    path.write_text(PIPELINE_YAML.replace("csv", "excel"))
    with pytest.raises(ConfigError) as excinfo:
        load_pipeline_config(path)
    assert "input_format" in excinfo.value.context["errors"]


def test_column_defaults_apply() -> None:
    """Optional fields fall back to their declared defaults."""
    col = ColumnSchema(name="amount", data_type="float")
    assert col.required is True
    assert col.nullable is False
    assert col.min_value is None


def test_column_coerces_int_to_float() -> None:
    """An integer min_value is converted to float."""
    col = ColumnSchema(name="amount", data_type="float", min_value=0)
    assert isinstance(col.min_value, float)


def test_column_rejects_unknown_data_type() -> None:
    """A data_type outside the Literal is rejected."""
    with pytest.raises(pydantic.ValidationError):
        ColumnSchema(name="amount", data_type="flaot")  # type: ignore[arg-type]


def test_load_yaml_missing_file(tmp_path: Path) -> None:
    """A missing file raises ConfigError with the path in context."""
    missing = tmp_path / "nope.yml"
    with pytest.raises(ConfigError) as excinfo:
        load_yaml(missing)
    assert excinfo.value.context["path"] == str(missing)


def test_load_yaml_rejects_non_mapping(tmp_path: Path) -> None:
    """A YAML file whose top level is not a mapping raises ConfigError."""
    path = tmp_path / "scalar.yml"
    path.write_text("just a string")
    with pytest.raises(ConfigError):
        load_yaml(path)


def test_load_schema_parses_columns(tmp_path: Path) -> None:
    """A valid schema file produces a DataSchema with typed columns."""
    path = tmp_path / "schema.yml"
    path.write_text(SCHEMA_YAML)
    schema = load_schema(path)
    assert schema.name == "orders"
    assert len(schema.columns) == 2
    assert schema.columns[1].min_value == 0.0


def test_load_schema_invalid_raises_schema_error(tmp_path: Path) -> None:
    """An invalid schema raises SchemaError, not ConfigError."""
    path = tmp_path / "bad.yml"
    path.write_text("name: orders\ndescription: x\ncolumns: []\nextra: [\n")
    with pytest.raises(SchemaError):
        load_schema(path)


def test_pipeline_config_coerces_schema_path() -> None:
    """schema_path becomes a Path object, not a string."""
    config = PipelineConfig(
        name="p",
        description="d",
        input_format="csv",
        output_format="csv",
        schema_path=Path("config/x.yml"),
    )
    assert isinstance(config.schema_path, Path)


def test_pipeline_config_defaults_are_independent() -> None:
    """Each instance gets its own transforms list."""
    first = PipelineConfig(
        name="a",
        description="d",
        input_format="csv",
        output_format="csv",
        schema_path=Path("config/x.yml"),
    )
    second = PipelineConfig(
        name="b",
        description="d",
        input_format="csv",
        output_format="csv",
        schema_path=Path("config/x.yml"),
    )
    first.transforms.append(...)  # type: ignore[arg-type]
    assert second.transforms == []
