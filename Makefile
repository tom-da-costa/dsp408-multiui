.PHONY: help sync lint format typecheck test e2e cov check web web-test web-dev backend dev

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

e2e:  ## End-to-end: tracks-dsp-sim and tracks-dsp-controller run as two programs
	uv run pytest -m e2e -v

cov:  ## Run tests with coverage
	uv run pytest --cov --cov-report=term-missing

check: lint typecheck test e2e  ## Everything CI runs

# --- web UI (Node locally if available, otherwise the node:22 Docker image) -------------------
NODE_DOCKER = docker run --rm -u $$(id -u):$$(id -g) -e HOME=/tmp -e npm_config_update_notifier=false \
	-v $(CURDIR):/app -w /app/web node:22-alpine
NPM = $(if $(shell command -v npm 2>/dev/null),cd web && npm,$(NODE_DOCKER) npm)
# The dev server needs the host network (to reach the backend on 127.0.0.1:8080 and to be
# reachable from phones on the LAN), and a TTY when there is one.
NPM_DEV = $(if $(shell command -v npm 2>/dev/null),cd web && npm,docker run --rm --init \
	$$([ -t 0 ] && echo -it) --network host -u $$(id -u):$$(id -g) -e HOME=/tmp \
	-e npm_config_update_notifier=false -v $(CURDIR):/app -w /app/web node:22-alpine npm)

web:  ## Build the UI into src/tracks_dsp_controller/web (the build is committed)
	$(NPM) ci --no-audit --no-fund
	$(NPM) run build

web-test:  ## Type-check and unit-test the UI
	$(NPM) ci --no-audit --no-fund
	$(NPM) run check
	$(NPM) test

web-dev:  ## Vite dev server only, hot reload on :5173 (start a backend on :8080 alongside)
	$(NPM_DEV) run dev -- --host 0.0.0.0

# Backend of `make dev`: demo mode by default. Against the separate simulator instead:
#   uv run tracks-dsp-sim --host 127.0.0.1   then   make dev DEV_BACKEND="--dsp-host 127.0.0.1"
DEV_BACKEND ?= --demo
backend:  ## Backend only (--demo) on :8080, for `make web-dev` in another terminal
	uv run tracks-dsp-controller $(DEV_BACKEND) --host 127.0.0.1 --port 8080

dev:  ## UI with hot reload on http://<this-machine>:5173, backend (--demo) on :8080
	@trap 'kill 0' INT TERM EXIT; \
	uv run tracks-dsp-controller $(DEV_BACKEND) --host 127.0.0.1 --port 8080 & \
	$(NPM_DEV) run dev -- --host 0.0.0.0
