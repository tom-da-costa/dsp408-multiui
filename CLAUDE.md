# CLAUDE.md

Guidance for Claude Code working in this repository.

## Project

A web app that controls one t.racks DSP 408 over TCP (port 9761). Several browsers (phones
first) control it at the same time with live meters. A single Python process owns the DSP
connection and serves the API, the WebSocket and the static UI.

Read these before doing anything substantial:

- `README.md`: features, compatibility, usage, sources and the attribution table
- `CONTRIBUTING.md`: development setup, checks, code rules, device safety
- `docs/ARCHITECTURE.md`: components, state model, command pipeline, simulator, WebSocket API,
  security, design choices (keep it in sync with the code)
- `docs/PROTOCOL.md`: protocol synthesis. Every item is tagged HW / 408 / SIB / CONFLICT / UNKNOWN.

The repository is public: do not commit private details (the owner's LAN addresses, host names,
credentials). Release notes come from the merged PRs (`gh release create --generate-notes`).

## Language

- Code, comments, docs, commit messages and UI strings: **English**.
- Talk to the owner in **French**.

## Hard constraints

- **No database.** Presets live in the DSP; server state is in memory only.
- **Fully offline.** No CDN, web fonts, telemetry or other external requests, at runtime or in
  the built UI.
- **One-command launch** in every mode: `uv run` from a clone (works without Node, because the
  built UI in `src/dsp408_multiui/web/` is committed), standalone PyInstaller executable,
  `docker run`, `docker compose up`.
- **Develop and test against the simulator.** It reproduces the DSP 408's recorded behaviour
  (`tests/hardware/`). `dsp408-sim` is a separate program that the backend reaches over TCP
  like the real device; `serve --demo` runs the same simulated device in-process. Never assume
  an unverified protocol detail is true: put it in the `ProtocolProfile` (ARCHITECTURE §6).
- **The owner's real DSP 408 is in production use.** Read-only commands (`probe info`, `probe
  meters`, `probe dump-config`, `serve` without clients writing) are fine. **Never write to it,
  recall or store a preset without the owner's explicit approval in the current session**, and
  never touch the preset they flag as live. When writes are approved, work on a copy of a preset
  in a free slot, dump the config first, and restore and compare at the end.
- Mobile-first UI. A fader only moves on a drag that starts on its knob.

## Architecture rules

- `protocol/` is pure: no I/O, no imports from other packages of this project. It is shared by
  the backend and the simulator.
- Only `device/session.py` talks to the transport. All DSP traffic goes through the single
  command pipeline: one request in flight, coalescing per parameter key, a guaranteed meter
  poll slot.
- The backend state is authoritative and is updated **after** the DSP ACK; every change goes
  out to all clients as a patch with a `rev`.
- Clients send physical units (dB, Hz, ms). The server validates, clamps and quantises; it never
  trusts client ranges.
- No global singletons for the device: keep a future multi-DSP `DeviceManager` possible.
- Frame on `LEN`, never by searching for `10 03` (the payload can contain those bytes).

## Device safety (never break these)

- Never store to preset slot 0 (F00).
- Preset names: at most 14 printable ASCII characters. Longer names can crash the firmware.
- Do not implement the test-tone generator (`0x39`) or the device-PIN setter (`0x2f`).
- On a real DSP, parameters not yet hardware-verified stay behind `--experimental`.

## Tooling

```bash
uv sync                                   # install
uv run dsp408-multiui --demo              # demo: backend + in-process simulated DSP on :8080
uv run dsp408-sim --host 127.0.0.1        # separate simulated DSP 408 on :9761, with a console
uv run dsp408-multiui --dsp-host 127.0.0.1  # backend connected to it like to a real DSP
uv run pytest                             # tests
make e2e                                  # dsp408-sim + dsp408-multiui as two programs (pytest -m e2e)
uv run ruff check . && uv run ruff format --check . && uv run mypy
make dev                                  # UI hot reload on :5173 + backend --demo on :8080 (Node or Docker)
make web                                  # rebuild the committed UI (Node or Docker; CI fails if stale)
make web-test                             # svelte-check + vitest
```

- Python ≥ 3.12, uv, hatchling. FastAPI + uvicorn, Pydantic v2.
- UI: Svelte 5 + TypeScript + Vite.
- mypy is strict on `protocol/` and `state/`. Coverage on `protocol/` must stay ≥ 90 %.

## Repository conventions

- Hosted on **GitHub** (public): https://github.com/tom-da-costa/dsp408-multiui. CI and releases use
  GitHub Actions (`.github/workflows/`) on GitHub-hosted runners: native arm64 runner for the
  linux-arm64 executable, Windows runner for the Windows executable, images on `ghcr.io`.
- Conventional Commits (`feat:`, `fix:`, `docs:` …).
- Upstream projects (README, "Sources and credits") can be cloned for reference **outside the repo**, in a
  scratch directory. Never vendor them. Copied code or test vectors keep their copyright notice
  and get a row in the README attribution table.
- When a protocol question is answered, update `docs/PROTOCOL.md` (confidence tag), the profile
  defaults and the fixtures together.
