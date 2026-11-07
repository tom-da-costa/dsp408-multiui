# Progress

Tracks the implementation against [PLAN.md](PLAN.md). Update this file as part of each change:
tick items, add notes, record deviations from the plan.

Legend: `[x]` done · `[~]` in progress · `[ ]` to do · `[-]` dropped or deferred (with reason)

## Phase 0: Scaffolding and protocol core

### 0.1 Scaffolding
- [ ] `pyproject.toml` (uv, hatchling, Python ≥ 3.12), `src/dsp408_multiui/` layout, CLI stub
- [ ] Ruff (lint + format), mypy strict on `protocol/` and `state/`, pytest + coverage config
- [ ] `Makefile`, `.gitignore`
- [ ] Gitea Actions `ci.yaml` (lint, format check, mypy, tests)
- [ ] `docs/SOURCES.md` attribution entries for copied vectors

### 0.2 `protocol/`
- [ ] `framing.py`: `encode_frame`, incremental `FrameDecoder` (frame on LEN, resync)
- [ ] `profile.py` + `profiles/default.toml`: `ProtocolProfile`
- [ ] `codecs.py`: gain, EQ gain, frequency, Q, threshold, times, delay, names
- [ ] `commands.py`: request builders and request parsers (simulator side)
- [ ] `responses.py`: response builders and parsers
- [ ] `meters.py`: float16 and 24-bit decoders/encoders, tail-byte layout
- [ ] `config_map.py`: config blob ↔ state model (layout from PROTOCOL §7)
- [ ] Test vectors from upstream projects in `tests/fixtures/`

**Exit:** codecs and parsers green; profile loads; a default config blob round-trips.

## Phase 1: Simulator and developer tools
- [ ] Simulator device state and opcode handling
- [ ] Simulator TCP server, second-client policy
- [ ] Synthetic meters following the parameters
- [ ] Fault injection, scenarios, frame log
- [ ] `device/transport.py` (minimal)
- [ ] `probe` CLI, `proxy` CLI, `docs/captures.md`

## Phase 2: Editor-vs-simulator capture session (optional)
- [ ] Capture session with the official editor

## Phase 3: Device layer
- [ ] State models, registry, store
- [ ] Command pipeline
- [ ] Device session
- [ ] Integration tests against the simulator

## Phase 4: Server
- [ ] Auth, sessions, rate limit
- [ ] Activity-based lock
- [ ] WebSocket hub, settings, health
- [ ] `serve` CLI, `--simulator`

## Phase 5: Web UI MVP
- [ ] Scaffold, WS client, stores, activity reporting
- [ ] Components and screens (Login, Mixer, Matrix, Presets, Settings)

## Phase 6: Distribution
- [ ] Committed UI + `web-check`
- [ ] PyInstaller executables (linux-amd64, linux-arm64, windows-amd64)
- [ ] Docker image (multi-arch), `compose.yaml`, `.env.example`
- [ ] Release workflow

## Phase 7: Remaining MVP parameters
- [ ] PEQ, HPF/LPF, delay, compressor, limiter
- [ ] Gate, GEQ, channel names

## Phase 8: Hardware verification
- [ ] Answer PROTOCOL §9 response-side questions on a real DSP 408

## Phase 9: Hardening and later items
- [ ] (see PLAN)

---

## Log

| Date | Change |
|---|---|
| 2026-11-07 | Docs committed (SPEC, PLAN, PROTOCOL, SOURCES, README, CLAUDE.md). Phase 0 started. |
