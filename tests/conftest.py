"""Shared fixtures for the PipeForge test suite."""

from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from pipeforge.config import ColumnSchema, DataSchema

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


@pytest.fixture(scope="session")
def orders_schema() -> DataSchema:
    """An in-memory schema for the orders dataset.

    Session-scoped: the object is immutable in practice and building it
    for every test would be wasted work.
    """
    return DataSchema(
        name="orders",
        description="Order data schema",
        columns=[
            ColumnSchema(name="order_id", data_type="integer"),
            ColumnSchema(name="customer_email", data_type="string"),
            ColumnSchema(name="product", data_type="string"),
            ColumnSchema(name="amount", data_type="float", min_value=0),
            ColumnSchema(name="order_date", data_type="date", date_format="%Y-%m-%d"),
            ColumnSchema(
                name="status",
                data_type="string",
                allowed_values=["completed", "pending", "shipped", "cancelled"],
            ),
        ],
        primary_key=["order_id"],
    )


@pytest.fixture
def clean_rows() -> list[dict[str, Any]]:
    """Rows that satisfy the orders schema.

    Function-scoped and rebuilt per test, because a test that mutates
    this must not affect any other.
    """
    return [
        {
            "order_id": "1001",
            "customer_email": "alice@example.com",
            "product": "Laptop",
            "amount": "1200.00",
            "order_date": "2026-01-15",
            "status": "completed",
        },
        {
            "order_id": "1002",
            "customer_email": "bob@example.com",
            "product": "Phone",
            "amount": "800.00",
            "order_date": "2026-01-16",
            "status": "pending",
        },
    ]


@pytest.fixture
def typed_rows() -> list[dict[str, Any]]:
    """Rows with real Python types, as a Parquet reader would produce."""
    return [
        {"order_id": 1001, "amount": 1200.0, "order_date": date(2026, 1, 15)},
        {"order_id": 1002, "amount": 800.0, "order_date": date(2026, 1, 16)},
    ]


@pytest.fixture
def schema_file(tmp_path: Path) -> Path:
    """A schema YAML written to a temporary file."""
    path = tmp_path / "schema.yml"
    path.write_text(SCHEMA_YAML)
    return path


@pytest.fixture
def clean_csv(tmp_path: Path) -> Path:
    """A valid CSV written to a temporary file."""
    path = tmp_path / "clean.csv"
    path.write_text(CSV_CLEAN)
    return path


@pytest.fixture
def messy_csv(tmp_path: Path) -> Path:
    """A CSV with schema violations, written to a temporary file."""
    path = tmp_path / "messy.csv"
    path.write_text(CSV_MESSY)
    return path


@pytest.fixture
def pipeline_file(tmp_path: Path, schema_file: Path) -> Path:
    """A pipeline config pointing at the schema fixture."""
    path = tmp_path / "pipeline.yml"
    path.write_text(PIPELINE_YAML.format(schema_path=schema_file))
    return path


@pytest.fixture(autouse=True)
def restore_transform_registry() -> Iterator[None]:
    """Undo registry changes after each test.

    The transform registry is module-level state. A test that registers
    an operation would otherwise leak it into every test that follows.
    """
    from pipeforge.transformers import _TRANSFORMS

    original = dict(_TRANSFORMS)
    yield
    _TRANSFORMS.clear()
    _TRANSFORMS.update(original)
