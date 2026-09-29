# syntax=docker/dockerfile:1

FROM python:3.11-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    VIRTUAL_ENV=/app/.venv

WORKDIR /app

# Dependencies first: this layer is cached until pyproject.toml changes.
# __init__.py is needed because the version is read from it at build time.
COPY pyproject.toml README.md ./
COPY src/pipeforge/__init__.py src/pipeforge/__init__.py
RUN uv venv "$VIRTUAL_ENV" && uv pip install --no-cache .

# Source last: a code change rebuilds only from here down.
COPY src/ src/
RUN uv pip install --no-cache --no-deps .


FROM python:3.11-slim AS runtime

RUN useradd --create-home --uid 1000 pipeforge

COPY --from=builder /app/.venv /app/.venv
COPY config/ /app/config/

ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /data
USER pipeforge

ENTRYPOINT ["pipeforge"]
CMD ["--help"]
