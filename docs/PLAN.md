# dsp408-multiui — Implementation Plan

Status: draft v0.2 (2026-11-07)
Inputs: [SPEC.md](SPEC.md), [PROTOCOL.md](PROTOCOL.md)

## Overview

No DSP is available for now. The plan therefore builds a **protocol-accurate simulator early**
and develops everything against it. Uncertain protocol details live in a `ProtocolProfile`
(SPEC §4.6), so the hardware session at the end only adjusts values, not code structure.

| Phase | Goal | Size | Needs |
|---|---|---|---|
| 0 | Scaffolding, protocol core, protocol profile | M | — |
| 1 | Simulator, plus `probe` and `proxy` tools | M | — |
| 2 | Editor-vs-simulator capture session (optional, opportunistic) | S | Windows PC + official editor |
| 3 | Device layer: session, command pipeline, state mirror | M | — |
| 4 | Server: auth, WebSocket hub, activity-based lock, settings | M | — |
| 5 | Web UI MVP: login, mixer and meters, matrix, presets, settings | L | — |
| 6 | Distribution: committed UI, standalone executables, Docker, Compose, releases | M | — |
| 7 | Remaining MVP parameters: PEQ, crossovers, delay, dynamics (+ gate, GEQ, names) | M | — |
| 8 | **Hardware verification** on a real DSP 408 | M | **DSP 408** |
| 9 | Hardening and "should/later" items | open | — |

Every phase from 3 onwards adds **full-stack integration tests** (simulator, real server,
WebSocket clients) to CI. Phases 4 and 5 can overlap once the WebSocket schema (SPEC §5) is
frozen.

---

## Target repository layout

```
pyproject.toml            # uv project, hatchling build, ruff/mypy/pytest config
uv.lock
Makefile                  # lint, test, web, web-check, exe, docker
Dockerfile                # python slim + uv (UI already built and committed)
compose.yaml              # single service, settings through environment variables
.github/workflows/
  ci.yml                  # lint · test · web-check · integration
  release.yml             # on tag: executables, Docker multi-arch, GitHub release
docs/                     # SPEC, PLAN, PROTOCOL, captures.md
src/dsp408_multiui/
  __init__.py  __main__.py  cli.py
  protocol/   framing.py codecs.py commands.py responses.py meters.py config_map.py profile.py
              profiles/default.toml
  device/     transport.py pipeline.py session.py
  state/      models.py store.py registry.py
  simulator/  server.py device.py meters.py faults.py scenarios/
  server/     app.py auth.py ws.py lock.py settings.py
  tools/      probe.py proxy.py
  web/        # built UI, committed (SPEC D9)
web/                      # Svelte 5 + TS + Vite sources
tests/
  fixtures/   # frames (.jsonl), config dumps (.bin), each with a .meta.toml sidecar
  unit/  simulator/  device/  server/  integration/
packaging/pyinstaller.spec
```

Development workflow:

- `uv sync`
- `uv run dsp408-multiui --demo`: backend and simulated DSP in one process
- or `uv run dsp408-sim` and `uv run dsp408-multiui --dsp-host 127.0.0.1`: two programs over TCP
- in `web/`: `npm run dev` (Vite dev server with `/api` and `/ws` proxied to `:8080`)

---

## Phase 0: Scaffolding and protocol core

**0.1 Scaffolding**

- `uv init --package`, Python ≥ 3.12, hatchling. Dependencies: `fastapi`, `uvicorn[standard]`,
  `pydantic`. Dev dependencies: `pytest`, `pytest-asyncio`, `ruff`, `mypy`, `httpx`.
- Ruff (lint + format), mypy strict for `protocol/` and `state/`.
- CI workflow `ci.yml` (GitHub Actions) running `ruff check`, `ruff format --check`, `mypy` and
  `pytest`.
- `docs/SOURCES.md` gets attribution notes (all sources are GPL-3.0, compatible with AGPL-3.0).

**0.2 `protocol/` (pure, I/O-free, fully unit-tested)**

- `framing.py`: `encode_frame(payload, src, dst)`, plus an incremental `FrameDecoder` that frames
  on `LEN`, checks `10 03 CHK` and resyncs on garbage. Works in both directions, so the
  simulator can reuse it.
- `profile.py`: the `ProtocolProfile` dataclass, loaded from TOML. `profiles/default.toml` holds
  the ▶ choices of PROTOCOL.md.
- `codecs.py`: two-segment gain, EQ gain, frequency, Q, threshold, times, delay, names. Every
  codec reads its parameters from the profile. Round-trip property tests.
- `commands.py` (builders) and `responses.py` (parsers), for **both** directions: requests and
  responses, both encoded and decoded, which the simulator needs.
- `meters.py`: `Float16Decoder` / `Level24Decoder`, with the tail-byte layout taken from the
  profile.
- `config_map.py`: config blob ↔ state model (encode and decode), with offsets taken from the
  partial map in PROTOCOL §7. Unknown bytes are kept as they are.
- Test vectors: known frames from the sources (handshake, every mute frame, gain examples, the
  408 config dump in dsp-408-ui `analyze5.py`). They are copied to `tests/fixtures` with
  attribution. Note: that dump was printed truncated, so it is used only for the layout
  (header, record positions), not as a byte-exact image.

**Exit:** `pytest` is green on all codecs and parsers; the profile loads; a default config blob
round-trips (encode → decode → identical).

---

## Phase 1: Simulator and developer tools

**1.1 Simulator** (SPEC §4.5)

- `simulator/device.py`: device state (identity string, 20 presets plus F00, live config). It
  answers every opcode in PROTOCOL §5:
  - init sequence and config pages;
  - recall/store (with a realistic ~1–2 s delay);
  - writes with ACK;
  - name length guard (it "crashes", i.e. disconnects, on more than 14 characters, like the
    real firmware is known to);
  - F00 store rejected.
- `simulator/server.py`: asyncio TCP server. It processes one request at a time per connection,
  as the DSP does. The behaviour for a second client is configurable: accept, refuse, or kick the
  first one.
- `simulator/meters.py`: per-channel generators (silence, steady level, sine-modulated, noise,
  clip, limiter/compressor active), encoded with the profile's meter decoder in reverse.
  Meters follow the parameters: a muted channel reads silence, gain changes shift the level,
  matrix routing feeds the outputs.
- `simulator/faults.py`: latency, dropped responses, corrupt frames, NaN meter frames, scheduled
  disconnects. Controlled through the API for tests and through CLI flags.
- `simulator/scenarios/`: named setups (`demo`, `silent`, `clipping`, `stress`).
- Frame log (JSONL) of everything received.
- CLI: a separate program, `dsp408-sim --port 9761 --profile … --scenario demo`.

**1.2 Tools**

- `device/transport.py`: asyncio streams, connect timeout, one request in flight (a minimal
  version, which phase 3 extends).
- `probe`: `info`, `meters --watch` (raw bytes plus both decodings), `dump-config -o`,
  `diff-config a.bin b.bin`, `raw HEX`. Developed against the simulator and ready for the
  hardware.
- `proxy`: a TCP man-in-the-middle with a decoded JSONL log (for phase 2 and phase 8).
- `docs/captures.md`: capture procedure and metadata format.

**Exit:** `probe` talks to the simulator for every opcode. The simulator's own test suite
covers state transitions, timing and faults.

---

## Phase 2: Editor-vs-simulator capture session (optional)

Pointing the official *DSP Processor Editor* at the simulator records the **requests** the
editor sends, with no DSP needed. This can settle the request-side questions of PROTOCOL §9:

- Q2: frequency steps and Q scale (set 1 kHz / Q 1.0 and look at the raw values);
- Q3: delay encoding;
- Q4: compressor and limiter layouts;
- Q5: slope table;
- Q6: gate, phase, names, link;
- Q7: the matrix crosspoint gain opcode.

Preconditions: the editor must let us enter an IP address, and it must accept the simulator's
init responses. To give it the best chance, the simulator replays the exact response shapes
known from dsp-408-ui.

Response-side questions remain open until phase 8: Q1 (meter format and tail bytes), Q8–Q11
(device answers, ACKs, TCP behaviour, config map).

Output: fixtures in `tests/fixtures/editor/` and updated profile defaults, with PROTOCOL.md
items marked "verified from editor requests".

If the editor refuses to work with the simulator, skip this phase. Nothing else depends on it.

---

## Phase 3: Device layer

- `state/models.py`: Pydantic models for `DeviceInfo`, `Preset`, `InputChannel`,
  `OutputChannel`, `PeqBand`, `Crossover`, `Compressor`, `Limiter`, `Gate`, `DeviceState`.
- `state/registry.py`: path → schema, bounds, quantiser, encoder, coalescing key,
  `hardware_verified` flag (SPEC §4.2).
- `state/store.py`: authoritative mirror, `rev` counter, `apply(changes) -> Patch`,
  subscribers.
- `device/pipeline.py`: one queue, coalescing by key, writes before polls with a guaranteed
  meter slot, barrier sequences, timeout and retry, metrics (SPEC §4.3).
- `device/session.py`: lifecycle `connecting → initialising → online ↔ offline`; init sequence;
  config read; poll loop at `meter_rate`; reconnect with backoff; `recall()`, `store()`,
  `resync()`; meter events; state updates after the ACK.
- Tests:
  - unit tests with a scripted fake transport and a fake clock;
  - integration tests against the simulator: bursts of 200 writes coalesce, the meter rate stays
    ≥ 1 Hz while the queue is saturated, reconnect after the simulator restarts, recall barrier,
    behaviour under injected faults.

**Exit:** a session against the simulator connects, mirrors the state, polls at 5 Hz and
survives every fault scenario.

---

## Phase 4: Server

- `server/auth.py`: login/logout, in-memory sessions (**no database**), cookie, rate limit.
- `server/lock.py`: `LockManager` with an **activity-based** idle timeout (default 120 s, SPEC
  F-MC-4):
  - the owner's writes, preset actions, lock actions and `activity` messages reset the timer;
  - keepalives and meters do not;
  - the lock is released on idle timeout, on explicit release, or on logout;
  - the clock is injected for tests.
- `server/ws.py`: connection hub; `hello`/`snapshot` on join; fan-out through per-client bounded
  queues (a slow client drops meter frames and never blocks the others); request path:
  validation → lock check → pipeline → `result`.
- `server/settings.py`: live meter rate (1–10 Hz), broadcast on change.
- `server/app.py` and `cli.py`: the `serve` options and environment variables (SPEC §7);
  `--demo` (formerly `--simulator`) starts an embedded simulated DSP; static files with an SPA fallback;
  `/api/health`.
- Tests: FastAPI `TestClient` with several WebSocket clients against the embedded simulator:
  last-writer-wins ordering, lock denial, idle expiry, renewal through activity, Origin check,
  auth required, slow-client isolation.

**Exit:** two scripted WebSocket clients see each other's writes. The lock blocks the other
client, stays held while the owner sends activity, and is released 120 s after the last
activity.

---

## Phase 5: Web UI MVP

- Scaffold: Vite, Svelte 5, TypeScript, `svelte-check`, `vitest`. No UI kit and no web fonts;
  CSS custom properties with a dark theme. UI in English, with strings kept in one module for a
  later French translation.
- `lib/ws.ts`: reconnect with backoff, `rev` gap → re-snapshot, `req` ids and promises,
  heartbeat.
- `lib/activity.ts`: global pointer/keyboard listener that sends `activity` at most every 10 s
  while the user interacts.
- `lib/store.ts`: Svelte stores for state, meters, lock, device and self; the "dragging" guard
  (SPEC §4.4).
- Components:
  - `Fader` (knob-only drag, ± buttons, tap to type);
  - `Meter` (peak hold; clip, limit and comp LEDs);
  - `Toggle`, `NumberField`, `ConfirmDialog`, `Toast`, `LockButton` (idle countdown),
    `StatusDot`, `SimulatorBadge`.
- Screens: Login, Mixer, Matrix, Presets, Settings.
- Checks on a real phone against `serve --demo` or `dsp408-sim`: 360 px layout, scrolling never moves a
  fader, nothing is hidden under the iOS safe area.
- Optional: a Playwright smoke test (headless Chromium, phone viewport) against the simulator,
  in CI.

**Exit:** against the simulator, from a phone and a PC at the same time: gain, mute, phase,
matrix, preset recall/store and live meters work, and the lock behaves as specified.

---

## Phase 6: Distribution

- **Committed UI** (SPEC D9): `make web` builds into `src/dsp408_multiui/web/`. The CI job
  `web-check` rebuilds and fails if `git diff` is not empty. This makes
  `git clone && uv run dsp408-multiui --dsp-host IP` work without Node.
- **Standalone executables** (SPEC D10): PyInstaller one-file builds of the CLI (UI and default
  profile included) for linux-amd64, linux-arm64 and windows-amd64. A smoke test runs
  `--version` and `--demo` with a health check on each.
- **Docker**: slim Python image, multi-arch (amd64 and arm64, built with buildx), non-root user,
  `HEALTHCHECK` on `/api/health`, pushed to the GitHub container registry (`ghcr.io`).
- **Docker Compose**: `compose.yaml` with one service, `restart: unless-stopped`, port 8080, and
  `DSP408_HOST`, `DSP408_PIN`, `DSP408_METER_RATE` and other settings from a `.env` file
  (`.env.example` provided).
- **Releases**: on a `vX.Y.Z` tag, `release.yaml` builds the executables and the Docker image and
  creates a GitHub release with the executables attached. The version comes from the git tag; a
  changelog is maintained.
- README quickstart for each launch mode (SPEC §7.1).

**Exit:** each of the 4 launch modes works on a fresh machine, including a Raspberry Pi.

---

## Phase 7: Remaining MVP parameters

- Channel detail screens: PEQ (bands, types, bypass, whole-channel bypass), HPF/LPF (slopes; the
  server remembers the last active slope), delay (ms with metres shown), compressor, limiter.
- Then the "should" items: gate, GEQ (31 sliders), channel names.
- Each feature goes through the same steps:
  1. registry entry;
  2. codec and simulator support;
  3. integration test;
  4. UI.

  It stays flagged "not hardware-verified" until phase 8.

**Exit:** every **M** requirement in SPEC §3 works end to end against the simulator.

---

## Phase 8: Hardware verification (when a DSP 408 is available)

- Run `probe info`, `probe meters --watch` and `probe dump-config` against the device. Answer
  the remaining questions of PROTOCOL §9 (Q1, Q8–Q12, plus Q2–Q7 if phase 2 was skipped), using
  the editor, `proxy` and `diff-config`.
- Update `profiles/default.toml`, `config_map.py` and the fixtures. Replace the simulator's
  assumptions with the verified behaviour. Set `hardware_verified` on each confirmed parameter.
- Manual smoke checklist (`docs/captures.md`) on the real device, with several clients.

**Exit:** all MVP parameters are hardware-verified and the simulator matches the device on
every recorded fixture.

---

## Phase 9: Hardening and later items

Each item gets its own small iteration, prioritised with the owner:

- periodic resync and front-panel change detection;
- device model check (F-DEV-5);
- DSP PIN unlock (F-DEV-6);
- matrix crosspoint gains and channel link;
- PWA manifest (install to home screen);
- French translation;
- `DeviceManager` for several DSPs (URL `/d/<id>`, one `DeviceSession` per device; the
  simulator can run several instances);
- import/export of the editor's preset files.

---

## Testing strategy (summary)

| Layer | Tooling | What |
|---|---|---|
| Protocol | pytest (+ hypothesis, optional) | Frames and codecs against captured vectors, round-trips, decoder resync, config blob encode/decode |
| Simulator | pytest-asyncio | Opcode coverage, state transitions, timing, fault injection |
| Device | fake transport + fake clock; simulator | Pipeline coalescing, priorities, timeouts, session lifecycle, reconnect |
| Server | FastAPI TestClient (WebSocket) + embedded simulator | Auth, activity lock, fan-out, validation, slow-client isolation |
| UI | vitest + svelte-check (+ optional Playwright) | Store logic (rev gaps, drag guard, activity throttle), units, smoke test |
| Distribution | CI smoke tests | Executable `--demo` health check, Docker health check, `web-check` |
| Hardware | manual checklist (phase 8) | Real-device verification before releases |

## Main risks

| Risk | Impact | Mitigation |
|---|---|---|
| The simulator encodes our assumptions, so tests can pass while the real device differs | Surprises in phase 8 | Every uncertainty is a profile field; parameters are flagged "not hardware-verified"; phase 2 captures, if possible, reduce the gap early |
| Sources are wrong for the 408 (several conflicts found) | Wrong values sent to a live system | Server-side clamping; `--experimental` gate on a real DSP until verified |
| The DSP accepts only one TCP client | The editor and the app cannot run together | Documented; the app is the sole client |
| The 408 does not report compressor/limiter activity separately | Missing LEDs | Fall back to one combined "dyn" LED, or derive from levels |
| Write bursts destabilise the DSP firmware | Device hangs | Coalescing, one request in flight, configurable maximum write rate per key |
| Committed build artefacts drift from the sources | Stale UI in `uv run` | `web-check` CI job |
| PyInstaller executables are large (~30–50 MB), and Windows may raise antivirus false positives | Download friction | Docker and the clone are the alternatives; signing can come later |
