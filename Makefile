.PHONY: help sync lint format typecheck test cov check

help:  ## Show this help
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

sync:  ## Install the project and dev dependencies
	uv sync

lint:  ## Lint and check formatting
	uv run ruff check .
	uv run ruff format --check .

format:  ## Auto-fix lint issues and format
	uv run ruff check --fix .
	uv run ruff format .

typecheck:  ## Run mypy
	uv run mypy

test:  ## Run the test suite
	uv run pytest

cov:  ## Run tests with coverage
	uv run pytest --cov --cov-report=term-missing

check: lint typecheck test  ## Everything CI runs
