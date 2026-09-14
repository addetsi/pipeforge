.PHONY: install lint format typecheck test check clean

install:
	uv venv --python 3.11
	uv pip install -e ".[dev]"
	pre-commit install

lint:
	ruff check .

format:
	ruff format .

typecheck:
	mypy src/

test:
	pytest

check: lint typecheck test

clean:
	rm -rf .venv dist build *.egg-info
	rm -rf .mypy_cache .ruff_cache .pytest_cache .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +.PHONY: install lint format typecheck test check clean

install:
	uv venv --python 3.11
	uv pip install -e ".[dev]"
	pre-commit install

lint:
	ruff check .

format:
	ruff format .

typecheck:
	mypy src/

test:
	pytest

check: lint typecheck test

clean:
	rm -rf .venv dist build *.egg-info
	rm -rf .mypy_cache .ruff_cache .pytest_cache .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
