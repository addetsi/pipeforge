"""Configuration models and YAML loading for pipeForge."""

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from pipeforge.exceptions import ConfigError, SchemaError
from pipeforge.logger import get_logger

logger = get_logger(__name__)

DataType = Literal["string", "integer", "float", "date", "boolean"]
FileFormat = Literal["csv", "json", "parquet"]


class ColumnSchema(BaseModel):
    """Definition of a single column in a data schema.

    Attributes:
        name: The column name as it appears in the data.
        data_type: Expected type: string, integer, float, date, or boolean.
        required: whether the column must be present in the data.
        nullable: whether the column may contain null values.
        min_value: Minimum allowed value for the column.
        max_value: Maximum allowed value for the column.
        allowed_values: if set, the column value must be one of these values.
        date_format: strptime format string for date columns.
        pattern: Regex the column value must match.
    """

    name: str
    data_type: DataType
    required: bool = True
    nullable: bool = False
    min_value: float | None = None
    max_value: float | None = None
    allowed_values: list[str] | None = None
    date_format: str | None = None
    pattern: str | None = None


class DataSchema(BaseModel):
    """A complete data schema: a names collection of column definitions.

    Attributes:
        name: Identifier for the schema.
        description: Human-readable summary of the dataset.
        columns: Definitions for every column in the data.
        primary_key: Columns that together uniquely identify a row.
        unique_columns: Columns that must have unique values across all rows.
    """

    name: str
    description: str
    columns: list[ColumnSchema]
    primary_key: list[str] | None = None
    unique_columns: list[str] | None = None


class TransformRule(BaseModel):
    """Definition of a transformation rule.

    Attributes:
        operation: Name of the transformation operation to apply or filter.
        params: Operation-specific parameters for the transformation.
    """

    operation: str
    params: dict[str, Any] = Field(default_factory=dict)


class PipelineConfig(BaseModel):
    """Top-level configuration for a pipeline run.

    Attributes:
        name: Identifier for the pipeline.
        description: Human-readable summary of the pipeline's purpose.
        input_format: Format of the input file.
        output_format: Format to write the output in.
        transforms: ordered list of transformations to apply.
        output_options: Writer-specific options such as compression.
    """

    name: str
    description: str
    input_format: FileFormat
    output_format: FileFormat
    schema_path: Path
    transforms: list[TransformRule] = Field(default_factory=list)
    output_options: dict[str, Any] = Field(default_factory=dict)


def load_yaml(path: Path) -> dict[str, Any]:
    """Read a YAML file and return its top-level mapping.

    Args:
        path: Path to the YAML file.

    Returns:
        The parsed file contents.

    Raises:
        ConfigError: If the file is missing, unreadable, not valid YAML,
            or does not contain a mapping at the top level.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise ConfigError("File not found", {"path": str(path)}) from e
    except OSError as e:
        raise ConfigError("Could not read file", {"path": str(path)}) from e

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ConfigError("Invalid YAML", {"path": str(path)}) from e

    if not isinstance(data, dict):
        raise ConfigError("Top level must be a mapping", {"path": str(path)})

    return data


def _format_errors(error: PydanticValidationError) -> str:
    """Flatten a Pydantic error into one readable line."""
    return "; ".join(
        f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}"
        for err in error.errors()
    )


def load_schema(path: Path) -> DataSchema:
    """Load and validate a data schema from YAML.

    Args:
        path: Path to the schema file.

    Returns:
        The validated schema.

    Raises:
        SchemaError: If the file is unreadable or the schema is invalid.
    """
    try:
        data = load_yaml(path)
    except ConfigError as e:
        raise SchemaError(e.message, e.context) from e

    try:
        schema = DataSchema.model_validate(data)
    except PydanticValidationError as e:
        raise SchemaError(
            "Invalid schema", {"path": str(path), "errors": _format_errors(e)}
        ) from e

    logger.info("Loaded schema %s with %d columns", schema.name, len(schema.columns))
    return schema


def load_pipeline_config(path: Path) -> PipelineConfig:
    """Load and validate a pipeline configuration from YAML.

    Args:
        path: Path to the pipeline config file.

    Returns:
        The validated pipeline configuration.

    Raises:
        ConfigError: If the file is unreadable or the config is invalid.
    """
    data = load_yaml(path)

    try:
        config = PipelineConfig.model_validate(data)
    except PydanticValidationError as e:
        raise ConfigError(
            "Invalid pipeline config", {"path": str(path), "errors": _format_errors(e)}
        ) from e

    logger.info("Loaded pipeline %s", config.name)
    return config
