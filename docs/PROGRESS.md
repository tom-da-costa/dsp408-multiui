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
run on the Gitea Docker runner (PR #1).

Findings during the phase:
- The config blob layout (1448 bytes: 16 + 4 × 140 + 8 × 104 + 40) is byte-exact on the real 408
  dump. It confirms 300 frequency steps and the 206 compressor/limiter layouts (PROTOCOL §7).
- Delay, mute and phase offsets in the blob are hypotheses (the only zero bytes left).
- `dataclass(slots=True)` breaks the auto-registration of request/response classes; those
  dataclasses are frozen without slots.

## Phase 1: Simulator and developer tools
- [x] Simulator device state and opcode handling
- [x] Simulator TCP server, second-client policy
- [x] Synthetic meters following the parameters
- [x] Fault injection, scenarios, frame log
- [x] `device/transport.py` (minimal)
- [x] `probe` CLI, `proxy` CLI, `docs/captures.md`

**Status: done.** 279 tests, 96 % total coverage. The CLI offers `simulate`, `probe` and `proxy`.

Notes:
- Requests declare the opcode of their expected response (`Request.RESPONSE`); the transport
  skips late answers to timed-out requests.
- The simulated identity string `DSP408 V1.04` is a placeholder (the real 0x13 reply is unknown).
- PEQ band bypass and channel PEQ bypass are kept outside the config blob (location unknown).

## Phase 2: Editor-vs-simulator capture session (optional)
- [x] Capture procedure and checklist (`docs/captures.md`)
- [ ] Capture session with the official editor (needs the owner's Windows PC; not blocking)

## Phase 3: Device layer
- [x] State models, registry, store
- [x] Command pipeline
- [x] Device session
- [x] Integration tests against the simulator

**Status: done.** 341 tests, 96 % coverage.

Notes:
- Parameter paths are dotted JSON paths into the snapshot (`outputs.3.gain_db`), zero-based.
- Idempotent reads (init sequence, config pages) are retried on timeout: without retries, a 5 %
  loss rate made the ~55-request init fail almost every time.
- A server-side disconnect is only noticed at the next request (at worst one meter period).

## Phase 4: Server
- [x] Auth, sessions, rate limit
- [x] Activity-based lock
- [x] WebSocket hub, settings, health
- [x] `serve` CLI, `--simulator`

**Status: done.** 358 tests. `uv run dsp408-multiui --simulator` serves the API on :8080 (a
placeholder page until the UI is built).

Notes:
- `serve` is the default sub-command; global options work before or after it.
- The lock message carries `idle_remaining_s` (relative) instead of an absolute expiry time.
- Patches are emitted before the matching `result` (the store updates on the device ACK).

## Phase 5: Web UI MVP
- [x] Scaffold, WS client, stores, activity reporting
- [x] Components and screens (Login, Mixer, Matrix, Presets, Settings)

**Status: done.** Svelte 5 + TypeScript + Vite; 27 kB gzipped in total. Checked with headless
Chromium against `serve --simulator`: login (including a wrong code), mixer on a 390 px phone and a
1366 px desktop (all 12 strips fit), knob-only fader drag, mute, matrix, presets, lock seen by a
second client, settings.

Notes:
- Node is not required: `make web` falls back to the `node:22-alpine` Docker image.
- TypeScript is pinned to 5.9 (svelte-check does not support 7 yet).
- A real-phone check (iOS Safari safe areas, touch scrolling) is still to do.

## Phase 6: Distribution
- [x] Committed UI + `web` CI job (fails if the committed build is stale)
- [~] PyInstaller executables: linux-amd64 built and smoke-tested; windows-amd64 built but
  untested (fails under Wine, see docs/release.md); linux-arm64 needs QEMU on the runner
- [x] Docker image, `compose.yaml`, `.env.example` (amd64 tested; arm64 via buildx in the release)
- [~] Release workflow written (`.gitea/workflows/release.yaml`); not run yet: needs Docker access
  and QEMU on the runner plus a `REGISTRY_TOKEN` secret (docs/release.md)

**Status: mostly done.** Remaining: a first tagged release on the Gitea runner, and a test of the
Windows executable on a real Windows machine.

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
| 2026-11-07 | Phase 1 done: simulator, transport, probe/proxy tools. Phase 2 procedure written. |
| 2026-11-07 | Phase 3 done: state models, registry, store, command pipeline, device session. |
| 2026-11-07 | Phase 4 done: FastAPI server, auth, activity lock, WebSocket hub, `serve` CLI. |
| 2026-11-07 | Phase 5 done: web UI (mixer, matrix, presets, settings, lock). |
| 2026-11-07 | Phase 6: Docker image, compose, executables, release workflow (first release pending). |
