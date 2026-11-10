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
- [x] PEQ, HPF/LPF, delay, compressor, limiter
- [x] Gate, GEQ, channel names
- [x] Channel detail screen (tap a strip name): sections per SPEC §8, verification badges

**Status: done.** Every M and S parameter of SPEC §3.2 works end to end against the simulator.
361 Python tests, 15 UI tests. Checked with headless Chromium on a 390 px phone and a 1366 px
desktop: every section edited (drag, steppers, typing), live sync to a second client, read-only
under another client's lock, back button.

Notes:
- The registry, codecs and simulator already covered these parameters (phases 0–3); this phase
  added the end-to-end tests (write every parameter, re-read the whole config from the
  simulator, compare) and the UI.
- Bug fixed: a partial write (`{freq_hz}` on a PEQ band) was merged onto the acked state, so a
  previous write to the same band that was not acked yet was lost (the pipeline coalesces per
  key). Partial writes now merge onto the in-flight value.
- `hello` carries `limits` (control ranges), so the UI does not hard-code them.
- Inputs have crossover fields in the state model, but the UI shows HPF/LPF on outputs only
  (SPEC §8); whether the 408 filters its inputs is unknown.
- All of these parameters except gain, mute, matrix and GEQ stay "unverified" until phase 8: on a
  real DSP they need `--experimental`, and the UI shows a badge.

## Phase 8: Hardware verification
- [x] Read-only checks on the owner's DSP 408 (V0104P): `probe info`, meters, config dump
- [x] Write session on a test copy (U01 → U04, approved by the owner); every parameter written
  and diffed; DSP restored to its starting state (U08, byte-identical config)
- [x] Meter calibration (gain steps against a reference channel)
- [x] `config_map`, profile defaults, simulator and fixtures updated; PROTOCOL.md tags **HW**
- [x] Full stack (`serve` + UI) checked read-only against the DSP
- [ ] Remaining open points (PROTOCOL §9): Hz / Q / slope / ratio names against the editor's
  display, second TCP client, crosspoint gains, PIN lock

**Status: done** for every MVP parameter. 420 Python tests.

Findings (details in PROTOCOL.md):
- The 408 serves config pages and meters only after the init sequence (`probe` now runs it).
- Meters are float32 (top three bytes), 1.0 = 0 dBFS. dsp-408-ui's float16 reading was wrong
  (silence showed as −8 dB). Tail byte 0 = compressor mask, byte 1 = limiter mask.
- Blob: phase at +98/+134, delay at +100/+136; mute, PEQ bypass and band bypass are trailer
  masks. The "HYP" offsets were wrong (delay was being read as mute + phase).
- Inputs have a delay and HPF/LPF. Linked channels follow each other (except name and
  matrix); the server state now mirrors that.
- Recall ~3.2 s, store ~7.4 s (slow timeout raised to 10 s, UI preset timeout 30 s); the
  preset-name ACK echoes the name; stored names are Latin-1.
- The simulator reproduces all 40 recorded writes byte for byte
  (`tests/fixtures/hardware/write_diffs.json`).

## Standalone simulator (`dsp408-sim`)

- [x] Separate program `dsp408-sim` (entry point, `python -m dsp408_multiui.simulator`, own
  executable in the release, `compose.sim.yaml`); `dsp408-multiui simulate` removed
- [x] `serve --simulator` renamed `--demo` (`DSP408_DEMO`, `--demo-scenario`, hello field `demo`,
  "DEMO" badge in the UI)
- [x] Presets kept across restarts (`--state-dir`), config dumps loaded into slots (`--preset`),
  `--active`, `--identity`, `--fast`, fault options, `DSP408_SIM_*` environment variables
- [x] Interactive console: status, presets, front-panel recall, kick, offline, faults, signals
- [x] Fixes found on the way: the init state is now per connection (a second client no longer
  stops the first one's meters); preset names read from the device are sent back in Latin-1
  (the simulator crashed on "Pas touché svp")
- [x] Tests: storage, console, CLI, the backend's device session against the program, the program
  as a subprocess (SIGTERM, console on stdin); compose bench and both executables built locally
- [x] End-to-end tests in CI (`e2e` job, `make e2e`, `tests/e2e/`): `dsp408-sim` and
  `dsp408-multiui` start side by side; HTTP login, two WebSocket clients, writes fanned out to
  linked channels and checked on the simulated DSP over TCP, lock, preset store persisted, DSP
  restart → reconnect with the stored preset active

## Rolling "main" release

- [x] `release.yaml` also runs on every push to `main`: tests, then the pre-release **main** (tag
  `main-latest`) is recreated with the executables of the app and of `dsp408-sim`
  (`packaging/release.sh`); image tag `:main`
- [x] Runner checked: Docker and buildx OK; no QEMU (arm64 skipped with a warning); the Actions
  token cannot push packages, so the image waits for a `REGISTRY_TOKEN` secret

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
| 2026-11-07 | Phase 7 done: channel detail screens for every parameter; partial-write fix. |
| 2026-11-08 | Phase 8: DSP 408 verified on hardware; protocol, simulator and UI updated. |
| 2026-11-09 | Standalone simulator program `dsp408-sim`; `--simulator` renamed `--demo`. |
| 2026-11-09 | Rolling "main" pre-release rebuilt on every push to `main`. |
| 2026-11-10 | Limiter calc tab (Hornplans method): thresholds from amp gain, speaker power, impedance, load; hard = Hornplans, soft = +2 dB (matches the owner's other calculator); applied as compressor (Limit, 1/1000 ms, knee 0) + limiter 6 dB above. |
| 2026-11-10 | Live view (meters with thresholds, fader, mute, big CLIP/CMP/LIM); web app manifest, icons, full-screen button. |
| 2026-11-10 | "Unsaved changes" indicator: top bar badge, Presets › Save to Uxx, warning before a recall. |
| 2026-11-10 | Channel links verified on the DSP (2a copies, 3b sets the mask) and editable (Params › Link). Exact device steps on − / +, held buttons repeat. |
| 2026-11-09 | UI: Params / Channels / All-in-one views, left tab rail. Meters and thresholds shown in dBu (full scale = +20 dBu), from a read-only observation on the DSP. |
