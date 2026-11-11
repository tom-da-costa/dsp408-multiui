# syntax=docker/dockerfile:1
# tracks-dsp-controller: single-process web controller for the t.racks DSP 408.
# The image also contains the simulated DSP: run it with `--entrypoint tracks-dsp-sim` (compose.sim.yaml).
# The web UI is pre-built and committed (src/tracks_dsp_controller/web), so no Node stage is needed.

FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim
LABEL org.opencontainers.image.title="tracks-dsp-controller" \
      org.opencontainers.image.description="Multi-client web controller for the t.racks DSP 408" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later"
RUN useradd --system --uid 10001 --home-dir /app dsp408 \
 && mkdir -p /app/state /app/tls \
 && chown dsp408:dsp408 /app/state /app/tls   # tracks-dsp-sim --state-dir, self-signed cert
COPY --from=build --chown=dsp408:dsp408 /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    DSP408_LISTEN_HOST=0.0.0.0 \
    DSP408_LISTEN_PORT=8080 \
    DSP408_TLS_DIR=/app/tls
USER dsp408
WORKDIR /app
EXPOSE 8080 9761
# HTTPS first (a self-signed certificate is fine here), then plain HTTP.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD ["python", "-c", "import os, ssl, urllib.request as u; p = os.environ.get('DSP408_LISTEN_PORT', '8080'); c = ssl._create_unverified_context()\ntry: u.urlopen(f'https://127.0.0.1:{p}/api/health', timeout=2, context=c)\nexcept Exception: u.urlopen(f'http://127.0.0.1:{p}/api/health', timeout=2)"]
ENTRYPOINT ["tracks-dsp-controller"]
CMD ["serve"]
