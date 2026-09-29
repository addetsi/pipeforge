"""Command-line interface for PipeForge."""

import contextlib
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

import typer

from pipeforge import __version__
from pipeforge.config import load_pipeline_config, load_schema
from pipeforge.exceptions import PipeForgeError
from pipeforge.inspectors import format_report, inspect_file
from pipeforge.logger import configure_logging, get_logger
from pipeforge.quality import generate_quality_report
from pipeforge.readers import read_file
from pipeforge.transformers import apply_pipeline
from pipeforge.validators import ValidationResult, validate_schema
from pipeforge.writers import AtomicPath, write_file

logger = get_logger(__name__)

app = typer.Typer(
    help="PipeForge: a config-driven data pipeline CLI tool.",
    no_args_is_help=True,
    add_completion=False,
)


@contextlib.contextmanager
def error_boundary() -> Iterator[None]:
    """Turn PipeForge errors into a clean message and exit code 1.

    Errors outside the PipeForge hierarchy are left to propagate, since
    they indicate a bug rather than a user-facing failure.

    Yields:
        Control to the wrapped block.

    Raises:
        typer.Exit: With code 1 when a PipeForgeError is caught.
    """
    try:
        yield
    except PipeForgeError as e:
        logger.error("%s", e)
        raise typer.Exit(code=1) from e


def _version_callback(value: bool) -> None:
    """Print the version and exit when --version is passed."""
    if value:
        typer.echo(f"pipeforge {__version__}")
        raise typer.Exit


@app.callback()
def main(
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Enable debug logging.")
    ] = False,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
) -> None:
    """Configure logging before any command runs."""
    configure_logging(level=logging.DEBUG if verbose else logging.INFO)


@app.command()
def inspect(
    input_path: Annotated[
        Path,
        typer.Option(
            "--input",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Input file path.",
        ),
    ],
) -> None:
    """Inspect a data file and show statistics."""
    with error_boundary():
        typer.echo(format_report(inspect_file(input_path)))


@app.command()
def validate(
    input_path: Annotated[
        Path,
        typer.Option(
            "--input",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Input file path.",
        ),
    ],
    schema_path: Annotated[
        Path,
        typer.Option(
            "--schema",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Schema YAML path.",
        ),
    ],
) -> None:
    """Validate a data file against a schema."""
    with error_boundary():
        schema = load_schema(schema_path)
        result = validate_schema(read_file(input_path), schema)
        _echo_result(result)
        if not result.is_valid:
            raise typer.Exit(code=1)


def _echo_result(result: ValidationResult) -> None:
    """Print a validation result as a readable summary."""
    typer.echo(
        f"{result.row_count} rows, {result.invalid_rows} invalid, "
        f"{len(result.errors)} errors, {len(result.warnings)} warnings"
    )
    for issue in sorted(result.errors, key=lambda i: (i.row or 0, i.column or "")):
        location = f"row {issue.row}" if issue.row else "file"
        column = f" {issue.column}" if issue.column else ""
        typer.echo(f"  ERROR  {location}{column}: {issue.message} (got {issue.actual})")
    for issue in result.warnings:
        location = f"row {issue.row}" if issue.row else "file"
        typer.echo(f"  WARN   {location}: {issue.message}")


@app.command()
def run(
    config_path: Annotated[
        Path,
        typer.Option(
            "--config",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Pipeline config path.",
        ),
    ],
    input_path: Annotated[
        Path,
        typer.Option(
            "--input",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Input file path.",
        ),
    ],
    output_dir: Annotated[
        Path, typer.Option("--output", file_okay=False, help="Output directory.")
    ],
    skip_validation: Annotated[
        bool,
        typer.Option("--skip-validation", help="Transform without validating first."),
    ] = False,
) -> None:
    """Run a full pipeline: validate, transform, and write output."""
    with error_boundary():
        config = load_pipeline_config(config_path)
        data = list(read_file(input_path, config.input_format))

        if not skip_validation:
            schema = load_schema(config.schema_path)
            result = validate_schema(data, schema)
            _echo_result(result)
            if not result.is_valid:
                typer.echo("Validation failed; no output written.")
                raise typer.Exit(code=1)

        transformed = apply_pipeline(data, config.transforms)
        destination = output_dir / f"{input_path.stem}.{config.output_format}"
        write_file(
            transformed, destination, config.output_format, config.output_options
        )
        typer.echo(f"Wrote {len(transformed)} rows to {destination}")


@app.command()
def quality(
    input_path: Annotated[
        Path,
        typer.Option(
            "--input",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Input file path.",
        ),
    ],
    schema_path: Annotated[
        Path,
        typer.Option(
            "--schema",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Schema YAML path.",
        ),
    ],
    output_path: Annotated[
        Path | None,
        typer.Option("--output", dir_okay=False, help="Write the report as JSON."),
    ] = None,
) -> None:
    """Generate a data quality report."""
    with error_boundary():
        report = generate_quality_report(input_path, schema_path)

        if output_path is not None:
            with AtomicPath(output_path) as tmp:
                tmp.write_text(report.model_dump_json(indent=2), encoding="utf-8")
            typer.echo(f"Wrote quality report to {output_path}")
        else:
            typer.echo(
                f"{report.file_name}: valid={report.is_valid}, "
                f"{report.row_count} rows, "
                f"{report.completeness}% complete"
            )
            for name, count in sorted(report.issues_by_type.items()):
                typer.echo(f"  {name}: {count}")


if __name__ == "__main__":
    app()
