# Progress

Tracks the implementation against [PLAN.md](PLAN.md). Update this file as part of each change:
tick items, add notes, record deviations from the plan.

Legend: `[x]` done · `[~]` in progress · `[ ]` to do · `[-]` dropped or deferred (with reason)

## Phase 0: Scaffolding and protocol core

### 0.1 Scaffolding
- [x] `pyproject.toml` (uv, hatchling, Python ≥ 3.12), `src/dsp408_multiui/` layout, CLI stub
- [x] Ruff (lint + format), mypy strict on `protocol/` and `state/`, pytest + coverage config
- [x] `Makefile`, `.gitignore`
- [x] Gitea Actions `ci.yaml` (lint, format check, mypy, tests)
- [x] `docs/SOURCES.md` attribution entries for copied vectors

### 0.2 `protocol/`
- [x] `framing.py`: `encode_frame`, incremental `FrameDecoder` (frame on LEN, resync)
- [x] `profile.py` + `profiles/default.toml`: `ProtocolProfile`
- [x] `codecs.py`: gain, EQ gain, frequency, Q, threshold, times, delay, names
- [x] `commands.py`: request builders and request parsers (simulator side)
- [x] `responses.py`: response builders and parsers
- [x] `meters.py`: float16 and 24-bit decoders/encoders, tail-byte layout
- [x] `config_map.py`: config blob ↔ state model (layout from PROTOCOL §7)
- [x] Test vectors from upstream projects in `tests/fixtures/`

**Exit:** codecs and parsers green; profile loads; a default config blob round-trips.
**Status: done.** 218 tests, 97 % coverage on `protocol/`. The Gitea CI workflow is written but
not yet run (no runner observed yet).

Findings during the phase:
- The config blob layout (1448 bytes: 16 + 4 × 140 + 8 × 104 + 40) is byte-exact on the real 408
  dump. It confirms 300 frequency steps and the 206 compressor/limiter layouts (PROTOCOL §7).
- Delay, mute and phase offsets in the blob are hypotheses (the only zero bytes left).
- `dataclass(slots=True)` breaks the auto-registration of request/response classes; those
  dataclasses are frozen without slots.

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
| 2026-11-07 | Phase 0 done: scaffolding, protocol core, config layout confirmed on the real dump. |
