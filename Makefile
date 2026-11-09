.PHONY: help sync lint format typecheck test e2e cov check web web-test web-dev

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

e2e:  ## End-to-end: dsp408-sim and dsp408-multiui run as two programs
	uv run pytest -m e2e -v

cov:  ## Run tests with coverage
	uv run pytest --cov --cov-report=term-missing

check: lint typecheck test e2e  ## Everything CI runs

# --- web UI (Node locally if available, otherwise the node:22 Docker image) -------------------
NODE_DOCKER = docker run --rm -u $$(id -u):$$(id -g) -e HOME=/tmp -e npm_config_update_notifier=false \
	-v $(CURDIR):/app -w /app/web node:22-alpine
NPM = $(if $(shell command -v npm 2>/dev/null),cd web && npm,$(NODE_DOCKER) npm)

web:  ## Build the UI into src/dsp408_multiui/web (the build is committed)
	$(NPM) ci --no-audit --no-fund
	$(NPM) run build

web-test:  ## Type-check and unit-test the UI
	$(NPM) ci --no-audit --no-fund
	$(NPM) run check
	$(NPM) test

web-dev:  ## Vite dev server (run `uv run dsp408-multiui --demo` alongside)
	cd web && npm run dev
