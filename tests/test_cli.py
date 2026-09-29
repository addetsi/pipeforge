"""End-to-end tests for the command-line interface."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pipeforge.cli import app

runner = CliRunner()

CSV_CLEAN = """order_id,customer_email,product,amount,order_date,status
1001,alice@example.com,Laptop,1200.00,2026-01-15,completed
1002,bob@example.com,Phone,800.00,2026-01-16,pending
"""

CSV_MESSY = """order_id,customer_email,product,amount,order_date,status
1001,alice@example.com,Laptop,1200.00,2026-01-15,completed
1001,,Phone,-50.00,2026-01-16,unknown_status
"""

SCHEMA_YAML = """
name: orders
description: Order data schema
columns:
  - name: order_id
    data_type: integer
  - name: customer_email
    data_type: string
  - name: product
    data_type: string
  - name: amount
    data_type: float
    min_value: 0
  - name: order_date
    data_type: date
    date_format: "%Y-%m-%d"
  - name: status
    data_type: string
    allowed_values: [completed, pending, shipped, cancelled]
primary_key: [order_id]
"""

PIPELINE_YAML = """
name: orders_pipeline
description: Clean orders
input_format: csv
output_format: json
schema_path: {schema_path}
transforms:
  - operation: cast
    params:
      amount: float
  - operation: filter
    params:
      column: amount
      operator: ">"
      value: 0
"""


@pytest.fixture
def schema_file(tmp_path: Path) -> Path:
    """Write a schema YAML and return its path."""
    path = tmp_path / "schema.yml"
    path.write_text(SCHEMA_YAML)
    return path


@pytest.fixture
def clean_csv(tmp_path: Path) -> Path:
    """Write a valid data file and return its path."""
    path = tmp_path / "clean.csv"
    path.write_text(CSV_CLEAN)
    return path


@pytest.fixture
def messy_csv(tmp_path: Path) -> Path:
    """Write an invalid data file and return its path."""
    path = tmp_path / "messy.csv"
    path.write_text(CSV_MESSY)
    return path


@pytest.fixture
def pipeline_file(tmp_path: Path, schema_file: Path) -> Path:
    """Write a pipeline config pointing at the schema fixture."""
    path = tmp_path / "pipeline.yml"
    path.write_text(PIPELINE_YAML.format(schema_path=schema_file))
    return path


def test_help_lists_commands() -> None:
    """Running with no arguments shows the available commands."""
    result = runner.invoke(app, [])
    assert "inspect" in result.stdout
    assert "validate" in result.stdout


def test_version_flag() -> None:
    """--version prints the package version and exits cleanly."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "pipeforge" in result.stdout


def test_inspect_succeeds(clean_csv: Path) -> None:
    """Inspect profiles a file and exits 0."""
    result = runner.invoke(app, ["inspect", "--input", str(clean_csv)])
    assert result.exit_code == 0
    assert "order_id" in result.stdout


def test_inspect_missing_file_exits_2(tmp_path: Path) -> None:
    """A nonexistent input is rejected by option validation."""
    result = runner.invoke(app, ["inspect", "--input", str(tmp_path / "nope.csv")])
    assert result.exit_code == 2


def test_validate_valid_data_exits_0(clean_csv: Path, schema_file: Path) -> None:
    """Valid data exits 0."""
    result = runner.invoke(
        app, ["validate", "--input", str(clean_csv), "--schema", str(schema_file)]
    )
    assert result.exit_code == 0


def test_validate_invalid_data_exits_1(messy_csv: Path, schema_file: Path) -> None:
    """Invalid data exits 1 and reports every error."""
    result = runner.invoke(
        app, ["validate", "--input", str(messy_csv), "--schema", str(schema_file)]
    )
    assert result.exit_code == 1
    assert "ERROR" in result.stdout


def test_run_writes_output(
    clean_csv: Path, pipeline_file: Path, tmp_path: Path
) -> None:
    """A successful pipeline writes a file named after the input."""
    output_dir = tmp_path / "out"
    result = runner.invoke(
        app,
        [
            "run",
            "--config",
            str(pipeline_file),
            "--input",
            str(clean_csv),
            "--output",
            str(output_dir),
        ],
    )
    assert result.exit_code == 0
    assert (output_dir / "clean.json").exists()


def test_run_invalid_data_writes_nothing(
    messy_csv: Path, pipeline_file: Path, tmp_path: Path
) -> None:
    """Validation failure aborts before any output is written."""
    output_dir = tmp_path / "out"
    result = runner.invoke(
        app,
        [
            "run",
            "--config",
            str(pipeline_file),
            "--input",
            str(messy_csv),
            "--output",
            str(output_dir),
        ],
    )
    assert result.exit_code == 1
    assert not output_dir.exists()


def test_run_skip_validation_writes_output(
    messy_csv: Path, pipeline_file: Path, tmp_path: Path
) -> None:
    """--skip-validation transforms data that would fail validation."""
    output_dir = tmp_path / "out"
    result = runner.invoke(
        app,
        [
            "run",
            "--config",
            str(pipeline_file),
            "--input",
            str(messy_csv),
            "--output",
            str(output_dir),
            "--skip-validation",
        ],
    )
    assert result.exit_code == 0
    assert (output_dir / "messy.json").exists()


def test_quality_exits_0_on_invalid_data(messy_csv: Path, schema_file: Path) -> None:
    """Reporting on bad data is a success, unlike validating it."""
    result = runner.invoke(
        app, ["quality", "--input", str(messy_csv), "--schema", str(schema_file)]
    )
    assert result.exit_code == 0


def test_quality_writes_json_report(
    messy_csv: Path, schema_file: Path, tmp_path: Path
) -> None:
    """--output writes a parseable JSON report."""
    output_path = tmp_path / "report.json"
    result = runner.invoke(
        app,
        [
            "quality",
            "--input",
            str(messy_csv),
            "--schema",
            str(schema_file),
            "--output",
            str(output_path),
        ],
    )
    assert result.exit_code == 0

    report = json.loads(output_path.read_text())
    assert report["is_valid"] is False
    assert report["row_count"] == 2
    assert "duplicate_key" in report["issues_by_type"]
