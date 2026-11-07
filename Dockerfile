# syntax=docker/dockerfile:1
# dsp408-multiui: single-process web controller for the t.racks DSP 408.
# The web UI is pre-built and committed (src/dsp408_multiui/web), so no Node stage is needed.

FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim
LABEL org.opencontainers.image.title="dsp408-multiui" \
      org.opencontainers.image.description="Multi-client web controller for the t.racks DSP 408" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later"
RUN useradd --system --uid 10001 --home-dir /app dsp408
COPY --from=build --chown=dsp408:dsp408 /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    DSP408_LISTEN_HOST=0.0.0.0 \
    DSP408_LISTEN_PORT=8080
USER dsp408
WORKDIR /app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('DSP408_LISTEN_PORT', '8080')}/api/health\", timeout=2)"]
ENTRYPOINT ["dsp408-multiui"]
CMD ["serve"]
