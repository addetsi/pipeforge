# PipeForge

A config-driven CLI for validating, transforming, and converting tabular data.

Point it at a messy CSV and a YAML schema. It tells you every row that violates
your rules, transforms the data through configurable steps, and writes clean
output as CSV, JSON, or Parquet. The pipeline lives in YAML, not in Python, so a
new dataset means a new config file not new code.

```bash
pipeforge validate --input data/orders.csv --schema config/orders_schema.yml
pipeforge run --config config/pipeline.yml --input data/orders.csv --output output/
```

## Why

Most data cleaning starts as a script, grows conditionals, and ends up as
something only its author can run. PipeForge separates the engine from the
rules: the Python never changes per dataset, only the YAML does.

- **Every error at once.** Validation doesn't stop at the first problem. A
  10,000-row file gives you the full list in one run, each issue carrying its
  row, column, expected value, and actual value.
- **Types that survive the format.** The same column arrives as `"1200.00"`
  from CSV and `1200.0` from Parquet. Validation asks whether a value *can be*
  the declared type, not whether `isinstance` happens to match.
- **Atomic output.** Results are written to a temporary file and renamed into
  place. A crash mid-write leaves your previous output intact rather than a
  plausible-looking truncated file.
- **Extensible without forking.** Transforms live in a registry. Adding one is
  a function plus a registry entry; the pipeline runner never changes.

## Install

Requires Python 3.11 or later.

```bash
git clone https://github.com/addetsi/pipeforge.git
cd pipeforge
make install
source .venv/bin/activate
```

Or with Docker, which needs no local Python:

```bash
docker build -t pipeforge .
docker run --rm -v "$PWD/data:/data/data:ro" pipeforge inspect --input data/orders.csv
```

## Commands

### `inspect` - profile a file

Shows what's actually in your data before you write any rules for it.

```bash
pipeforge inspect --input data/orders_messy.csv
```

```
orders_messy.csv  (501 bytes, csv)
8 rows x 6 columns
COLUMN          TYPE           NULLS   UNIQUE  RANGE            SAMPLE
----------------------------------------------------------------------
order_id        integer    1 (12.5%)        6  1001 .. 1006     1001, 1002
amount          string      0 (0.0%)        7  len 5 .. 12      1200.00, 800.00
                -> 87.5% of values parse as float
```

That last line is the point. A column of 10,000 amounts with nine `"N/A"`
entries is technically a string column and reporting it as one would hide
the nine values that are the actual story.

### `validate` - check against a schema

```bash
pipeforge validate --input data/orders_messy.csv --schema config/orders_schema.yml
```

```
8 rows, 6 invalid, 8 errors, 1 warnings
  ERROR  row 2 order_id: Duplicate primary key, first seen on row 1 (got 1001)
  ERROR  row 3 customer_email: customer_email must not be null (got '')
  ERROR  row 4 amount: amount is not a valid float (got 'not_a_number')
  ERROR  row 5 amount: amount is below the minimum (got -50.00)
  WARN   row 2: Row is identical to row 1
```

Exits 1 when the data is invalid, so it works as a gate in CI or a scheduler.

### `run` - validate, transform, write

```bash
pipeforge run \
  --config config/pipeline.yml \
  --input data/orders.csv \
  --output output/
```

Refuses to write output for data that fails validation. Pass
`--skip-validation` to transform anyway.

### `quality` - a report you can archive

```bash
pipeforge quality \
  --input data/orders.csv \
  --schema config/orders_schema.yml \
  --output output/report.json
```

Combines validation results with column profiles and a per-type issue count,
as JSON. Trend `issues_by_type` across runs and you have data quality
monitoring.

## Configuration

A **schema** describes what valid data looks like:

```yaml
name: orders
description: Order data schema
columns:
  - name: order_id
    data_type: integer
    required: true
    nullable: false
  - name: customer_email
    data_type: string
    pattern: "^[\\w.-]+@[\\w.-]+\\.\\w+$"
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
```

A **pipeline** describes what to do with the data:

```yaml
name: orders_pipeline
description: Clean and transform raw order data
input_format: csv
output_format: parquet
schema_path: config/orders_schema.yml
transforms:
  - operation: rename
    params:
      mapping:
        orderDate: order_date
  - operation: cast
    params:
      order_date: date
      amount: float
  - operation: filter
    params:
      column: amount
      operator: ">"
      value: 0
  - operation: add_column
    params:
      name: order_year
      expression: "order_date.year"
output_options:
  compression: snappy
```

Available operations: `rename`, `cast`, `filter`, `add_column`,
`drop_column`, `deduplicate`, `sort`, `fill_nulls`.

Transforms run in the order listed, each one's output feeding the next.
`add_column` expressions are deliberately limited to a literal or
`source.attribute` — config files are data, not code, so nothing is `eval`'d.

## Architecture

```
cli.py          Typer commands; the boundary where exceptions become exit codes
config.py       Pydantic models; YAML in, validated objects out
readers.py      CSV, JSON, JSONL, Parquet -> iterator of row dicts
validators.py   Rows + schema -> a result listing every issue found
transformers.py Pure functions plus a registry driving them from config
writers.py      Row dicts -> CSV, JSON, Parquet, written atomically
inspectors.py   Profiling and type inference without a schema
quality.py      Validation and profiling combined into one report
```

Data enters as an iterator of `dict[str, Any]` and stays in that shape
throughout, so no module needs to know which format it came from. Readers
yield lazily; callers that need random access materialize with `list()`.

Every module raises subclasses of `PipeForgeError`. The CLI catches those and
exits 1. Anything else propagates with a traceback, because it's a bug rather
than a user-facing failure.

## Extending

A new transform is a function and a registry entry:

```python
from pipeforge.transformers import register_transform
from pipeforge.utils import Data


def split_name(data: Data, params: dict) -> Data:
    """Split one column into two on a separator."""
    source = params["column"]
    return [
        {**row, "first": row[source].split()[0], "last": row[source].split()[-1]}
        for row in data
    ]


register_transform("split_name", split_name)
```

It's then usable as `operation: split_name` in any pipeline config. Nothing
in `apply_pipeline` changes.

## Development

```bash
make install     # venv, dependencies, pre-commit hooks
make check       # lint, type check, tests
make test        # tests with coverage
make docker-build
```

Type-checked with mypy in strict mode, linted and formatted with ruff, tested
with pytest. Every push runs the same checks on a clean Linux runner.

## Limitations

Tabular, row-oriented data only: rows of records with named columns. Nested
JSON, multi-file joins, incremental loads, and streaming are out of scope.

## License

MIT
