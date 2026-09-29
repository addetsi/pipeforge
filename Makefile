.PHONY: install lint format typecheck test check clean docker-build docker-run

docker-build:
	docker build -t pipeforge:$(shell python -c "import pipeforge; print(pipeforge.__version__)") -t pipeforge:latest .

docker-run:
	docker compose run --rm pipeforge $(ARGS)

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
