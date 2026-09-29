# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-09-29

First stable release. The CLI, config format, and module APIs are now
considered public.

### Added

- Documentation: README with usage, configuration reference, and architecture
  overview; Google-style docstrings throughout.

## [0.11.0] - 2026-09-29

### Added

- Multi-stage `Dockerfile` installing dependencies in a cached layer above the
  source copy, with a runtime stage containing no build tooling and running as
  a non-root user.
- `docker-compose.yml` declaring the data, config, and output mounts.
- CI job building the image and smoke-testing the entrypoint.

### Fixed

- Missing space in the `apply_pipeline` log message.

## [0.10.0] - 2026-09-29

### Added

- `tests/conftest.py` with shared fixtures, scoped by mutability.
- Tests for simulated failure paths: failed temporary file creation, failed
  rename, permission errors.
- Coverage floor of 90% enforced in CI.

### Fixed

- Transform registry no longer leaks between tests.

## [0.9.0] - 2026-09-28

### Added

- Typer CLI with `inspect`, `validate`, `run`, and `quality` commands.
- `--verbose` flag switching the package log level to DEBUG.
- `quality.py` combining validation results and column profiles into a JSON
  report with a per-type issue breakdown.
- Error boundary translating `PipeForgeError` into exit code 1 while letting
  unexpected exceptions propagate with a traceback.

## [0.8.0] - 2026-09-28

### Added

- `inspectors.py` profiling files without a schema: inferred type, nulls,
  uniqueness, ranges, and sample values.
- Dominant-type reporting, so a mostly-numeric column with a few bad values is
  identified as a data problem rather than a text column.

## [0.7.0] - 2026-09-28

### Added

- CSV, JSON, and Parquet writers with a format factory.
- `AtomicPath` context manager writing to a temporary file and renaming into
  place only on success.

### Fixed

- Parquet output no longer drops columns absent from the first row.

## [0.6.0] - 2026-09-28

### Added

- Eight transform functions, all pure: `rename`, `cast`, `filter`,
  `add_column`, `drop_column`, `deduplicate`, `sort`, `fill_nulls`.
- Registry mapping operation names to transforms, with `register_transform`
  for extension from outside the module.
- `@log_transform` decorator reporting row counts and duration.

## [0.5.0] - 2026-09-28

### Added

- Schema validation reporting every issue found rather than raising on the
  first, with row, column, expected, and actual on each.
- Eleven checks: required and unexpected columns, types, nulls, numeric
  ranges, allowed values, date formats, regex patterns, primary key
  uniqueness, unique columns, duplicate rows.

## [0.4.0] - 2026-09-28

### Added

- CSV, JSON, JSON Lines, and Parquet readers yielding rows lazily as
  dictionaries, with a factory dispatching on format or extension.

## [0.3.0] - 2026-09-18

### Added

- Pydantic models for schemas and pipeline configuration.
- YAML loading that fails on load with the offending field named.

## [0.2.0] - 2026-09-14

### Added

- Package-level logging configuration with console and optional file output.
- Exception hierarchy under `PipeForgeError`, each carrying a message and
  optional context.

## [0.1.0] - 2026-09-3

### Added

- Project structure with `src/` layout and `pyproject.toml`.
- Pre-commit hooks, GitHub Actions CI, Makefile.

[1.0.0]: https://github.com/addetsi/pipeforge/releases/tag/v1.0.0
[0.11.0]: https://github.com/addetsi/pipeforge/releases/tag/v0.11.0
