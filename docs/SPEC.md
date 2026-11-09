# dsp408-multiui — Specification

Status: draft v0.2 (2026-11-07)
Related: [PROTOCOL.md](PROTOCOL.md) (device protocol synthesis), [PLAN.md](PLAN.md) (implementation plan)

## 1. Goal

A self-hosted web application that controls one **t.racks DSP 408** over the network and lets
**several browsers control it at the same time**, with live metering. One backend process owns
the TCP connection to the DSP and serves a mobile-first web UI to every client on the local
network.

```
 phone ─┐                     ┌──────────────────────────────┐   TCP 9761   ┌─────────┐
 phone ─┼── HTTP + WebSocket ─┤  dsp408-multiui (1 process)  ├──────────────┤ DSP 408 │
 PC ────┘      (LAN only)     │  FastAPI · state · protocol  │  (sole client)└─────────┘
                              └──────────────────────────────┘
```

## 2. Context and constraints

| Constraint | Consequence |
|---|---|
| Private LAN, **no internet access** at the venue | No CDN, no external fonts, no telemetry: every asset ships in the package. |
| Clients are browsers on **phones first**, then desktop, then tablet | Mobile-first layout, touch-safe controls, works at 360 px width. |
| DSP connected via a router (Ethernet) | TCP client only. No USB support. |
| Start with **one command** | A single process serves the API, the WebSocket and the static UI. Supported launch modes: `uv run` from a git clone, `docker run`, `docker compose up`, and a downloadable standalone executable (see §7.1). |
| **No database** | All persistent data (presets) lives in the DSP. The server keeps only in-memory state. |
| **No DSP available during development** | A protocol-accurate **simulator** is a first-class component, used for development, tests and demos (§4.5). Uncertain protocol details are kept configurable (§4.6). |
| Python + uv for the backend; TypeScript allowed for the UI | FastAPI backend; the UI is built with Vite and embedded in the Python package. |
| Repository on a personal **Gitea** | CI runs on Gitea Actions (GitHub-Actions syntax); packages are published to the Gitea registries. |
| One DSP for now, possibly several later | Device code is isolated behind a `DeviceSession` object. No global singletons. |

## 3. Functional requirements

Priorities: **M** = MVP, **S** = should (right after the MVP), **L** = later.
Every parameter feature is built and tested against the simulator first. On a **real** DSP, a
feature whose encoding is not yet verified on hardware (PROTOCOL §9) stays hidden unless
`--experimental` is given. Against the simulator, everything is enabled.

### 3.1 Device connection

| ID | Requirement | Prio |
|---|---|---|
| F-DEV-1 | Connect to the DSP at `--dsp-host[:--dsp-port]`, run the init sequence, and read the device identity, preset names, active preset and full configuration. | M |
| F-DEV-2 | Reconnect automatically with exponential backoff (1 s → 30 s) and re-read the full state after reconnecting. | M |
| F-DEV-3 | Show the device status to every client: `connecting`, `initialising`, `online`, `offline`, `locked`, plus the last error. | M |
| F-DEV-4 | "Refresh from device" action: re-read the configuration (detects front-panel edits). An optional periodic resync is available (`--resync-interval`, off by default). | M |
| F-DEV-5 | Refuse to drive a device whose identity string is not a DSP 408 unless `--force-model` is given. | S |
| F-DEV-6 | Unlock a PIN-protected DSP (`0x2d`) with `--dsp-pin`. | L |

### 3.2 Parameters

| ID | Requirement | Channels | Prio |
|---|---|---|---|
| F-P-1 | Gain (−60 … +12 dB, using the device's step rules) | all 12 | M |
| F-P-2 | Mute | all | M |
| F-P-3 | Phase / polarity invert | all | M |
| F-P-4 | Routing matrix 4 → 8 (on/off per crosspoint) | outputs | M |
| F-P-5 | Parametric EQ: per band gain, frequency, Q, type and bypass, plus whole-channel PEQ bypass | 8 bands on inputs, 9 on outputs | M |
| F-P-6 | High-pass and low-pass: frequency and slope (bypass = slope "off"; the server remembers the last active slope) | all (the 408 filters its inputs too) | M |
| F-P-7 | Delay in ms, also shown in m (cosmetic) | all (the 408 delays its inputs too) | M |
| F-P-8 | Compressor: ratio, knee, attack, release, threshold | outputs | M |
| F-P-9 | Limiter: attack, release, threshold | outputs | M |
| F-P-10 | Noise gate: attack, hold, release, threshold | inputs | S |
| F-P-11 | 31-band graphic EQ | inputs | S |
| F-P-12 | Channel names (8 ASCII characters) | all | S |
| F-P-13 | Matrix crosspoint gain | outputs | L |
| F-P-14 | Channel link | all | L |
| — | **No frequency-response curves** (explicit non-goal) | | — |
| — | **No test-tone generator** (speaker safety) and **no device-PIN setting** (`0x2f` can brick access) | | — |

### 3.3 Presets (stored in the DSP only)

| ID | Requirement | Prio |
|---|---|---|
| F-PR-1 | List U01–U20 with names; highlight the active preset. | M |
| F-PR-2 | Recall a preset (U01–U20 and F00), after confirmation. The full configuration is then re-read and pushed to every client. | M |
| F-PR-3 | Store the current state into U01–U20 with a name (≤ 14 printable ASCII characters, validated on the server), after an overwrite confirmation. **Storing to F00 is impossible by design.** | M |
| F-PR-4 | Import/export of the official editor's preset files. | L (maybe) |

### 3.4 Real-time meters

| ID | Requirement | Prio |
|---|---|---|
| F-M-1 | Per channel: level bar, peak-hold marker (held ~1.5 s, computed in the client), **clip** LED (latched 2 s). | M |
| F-M-2 | Per output: **limiter active** and **compressor active** LEDs, if the device reports them (PROTOCOL Q1). | M |
| F-M-3 | Refresh rate: default **5 Hz**, adjustable from **1 to 10 Hz**. The default comes from `--meter-rate`; it can be changed live from the Settings page and applies to everyone. The rate never drops below 1 Hz, even while the command queue is busy. | M |
| F-M-4 | Meters stay visible to everyone, including clients without the lock and while another client holds it. | M |

### 3.5 Multi-client behaviour

| ID | Requirement | Prio |
|---|---|---|
| F-MC-1 | Any number of clients (target ≥ 10) can connect at once and see the same state. | M |
| F-MC-2 | **Normal mode: last writer wins.** The server applies writes in arrival order and broadcasts the resulting state to all clients, the sender included. | M |
| F-MC-3 | **Exclusive lock:** a client can take an exclusive write lock. While it holds the lock, every other client is read-only (meters keep working). | M |
| F-MC-4 | **Activity-based lock.** The owner keeps the lock as long as it is active. The lock is released when the owner releases it, when the owner logs out, or after **120 s without activity** from the owner (`--lock-idle-timeout`). "Activity" means any write, preset action or lock action, plus any user interaction in the UI (tap, drag, key press), which the client reports with a throttled `activity` message (at most one every 10 s). Background traffic (WebSocket keepalive, meters) does **not** count. So a disconnected or forgotten client loses the lock after 120 s. | M |
| F-MC-5 | Every client sees who holds the lock (display name). The owner sees the time left before the idle release. | M |
| F-MC-6 | The list of connected clients (display names) is visible in Settings. | S |

### 3.6 Access

| ID | Requirement | Prio |
|---|---|---|
| F-A-1 | Access requires a shared **code** (default `0000`), set with `--pin` or `DSP408_PIN`. A warning is logged when the default is in use. | M |
| F-A-2 | The login screen asks for the code and an optional display name (e.g. "FOH phone"). | M |
| F-A-3 | The session survives page reloads (cookie) until logout or a server restart. | M |

## 4. Architecture

### 4.1 Components (single Python process, asyncio)

```
src/dsp408_multiui/
  protocol/   pure, I/O-free: framing, checksum, value codecs, command builders, response parsers,
              config-blob map (offsets → model). 100 % unit-tested.
  device/     asyncio TCP transport · CommandPipeline (queue, coalescing, ACK/timeout) ·
              DeviceSession (init, polling, reconnect, resync) · meter decoders
  state/      Pydantic models of the device state · StateStore (authoritative mirror, revision
              counter, change events) · parameter registry (path → validator, encoder, opcode)
  server/     FastAPI app · auth (PIN, sessions) · WebSocket hub (fan-out) · LockManager ·
              static file serving of the built UI
  simulator/  protocol-accurate fake DSP 408 (asyncio TCP server), see §4.5
  tools/      CLI sub-commands: probe, proxy (frame logger)
  web/        built static UI assets, generated from /web and committed (D9)
web/          Svelte 5 + TypeScript + Vite sources
```

Rules:

- `protocol/` imports nothing from the rest of the code base and does no I/O.
- Only `DeviceSession` talks to the transport.
- The server layer depends on `StateStore` and `DeviceSession` interfaces, which keeps a future
  `DeviceManager` (several DSPs) a mechanical change.

### 4.2 State model

- The backend holds the **authoritative mirror** of the DSP state, filled from the config blob at
  connect time and after every recall or resync.
- Every parameter has a **path**: its dotted location in the JSON snapshot, with zero-based
  indexes, e.g. `outputs.3.gain_db`, `outputs.3.peq.2` (a whole band, partial objects are
  merged), `inputs.1.geq.17`, `outputs.5.matrix` (one boolean per input),
  `outputs.2.crossover.hpf`, `outputs.2.compressor`. Clients write with the same paths they use to
  apply patches. The registry (`state/registry.py`) maps each path to:
  1. a schema with units and bounds (clients send **physical units**: dB, Hz, ms);
  2. a quantiser (snap to the device's steps);
  3. an encoder that builds the frame;
  4. a coalescing key.
- `StateStore` keeps a monotonically increasing `rev`. Every change produces a `patch` with the
  new `rev`. A client that detects a gap asks for a full snapshot.
- Parameter kinds not yet verified on a DSP 408 are flagged in the registry
  (`HARDWARE_VERIFIED` lists the verified ones). On a real DSP they are refused unless
  `--experimental` is given.

### 4.3 Command pipeline (DSP side)

The DSP handles one request at a time (PROTOCOL §1), so all traffic goes through a single queue:

1. **Coalescing.** A pending write for an existing key replaces the queued value in place. A
   fader dragged by three clients therefore produces at most one frame in flight and one pending
   frame per key.
2. **Priorities.** Writes come before meter polls. However, when the meter period has elapsed,
   the next free slot goes to a poll, which guarantees the configured rate (and ≥ 1 Hz).
3. **Barriers.** Preset recall/store and resync are exclusive sequences with long timeouts (2–3 s).
   Writes received in the meantime wait in the queue.
4. **ACK handling.** Timeout of 500 ms (configurable) and one retry. On failure, the server
   broadcasts an error, marks the parameter for re-read and, after N consecutive failures,
   reconnects.
5. **Ordering.** The state store is updated (and the patch broadcast) **after** the DSP
   acknowledges the write, so every client converges on what the device accepted.

### 4.4 Client behaviour

- **Optimistic UI.** Controls move immediately and send values throttled to ~20 Hz while being
  dragged. While the user drags, server patches for that control are ignored; on release, the
  control snaps to the last server value.
- **Rejected writes** (lock, validation, device error) restore the server value and show a toast.
- The client reconnects its WebSocket automatically, then gets a fresh snapshot. If the session
  is gone (server restart), it shows the login screen.

### 4.5 Simulator

A fake DSP 408 that the real backend cannot tell apart from the device, as far as we know the
protocol.

- It is an asyncio TCP server (default port 9761). It reuses `protocol/` to decode requests and
  encode responses, so both sides share one implementation of the protocol.
- It holds a full device state (20 presets plus F00, live config) and answers every implemented
  opcode: init sequence, config pages, preset recall/store, parameter writes with ACKs, meter polls.
- Meters are synthetic and scriptable per channel (silence, sine level, noise, clipping, limiter
  or compressor active).
- Fault injection: latency, dropped responses, malformed frames, NaN meters, disconnects, slow
  recall/store, refusal of a second TCP client.
- It loads the same protocol profile as the backend (§4.6), so each hypothesis can be tested.
- It also logs every frame it receives. Pointing the **official editor** at the simulator
  captures the editor's requests (how it encodes a frequency, a delay, a compressor) without a
  DSP. See PLAN, Phase 2.
- It keeps stored presets across restarts in a state directory (`--state-dir`), loads config
  dumps from a real device (`--preset 8=u08.bin`), and has an interactive console to change
  faults and input signals while it runs (`kick`, `offline 10`, `drop 0.1`, `signal A steady -3`…).
- Each TCP connection needs its own init sequence, as on the 408.
- It is a **separate program**, `dsp408-sim` (separate executable, same Docker image with
  `--entrypoint dsp408-sim`, `compose.sim.yaml`). The backend connects to it over TCP exactly
  as to a real DSP, so it tests the real network path: reconnects, timeouts, several clients.
- The **demo mode** (`serve --demo`) runs the same simulated device inside the backend process,
  for a one-command demo without any DSP.
- Uses: UI development, automated integration tests, test benches, demos.

### 4.6 Protocol profile

Every protocol detail that is still uncertain (PROTOCOL §9) is a field of a `ProtocolProfile`:

- meter decoder and tail-byte layout;
- frequency step count and Q scale;
- delay sample rate;
- compressor and limiter layouts;
- slope table;
- frame DST byte;
- command timeouts.

The defaults are the ▶ choices in PROTOCOL.md. Once the hardware is available, verification only
changes profile values and test fixtures, not the architecture. The profile ships with the
package and can be overridden with `--profile file.toml`.

## 5. Client ↔ server API

HTTP (JSON):

| Method | Path | Body / result |
|---|---|---|
| `POST` | `/api/login` | `{pin, name?}` → sets the `session` cookie (HttpOnly, SameSite=Strict); 401 on a wrong code |
| `POST` | `/api/logout` | Clears the session and releases any lock it held |
| `GET` | `/api/session` | `{authenticated, client_id, name}`; 401 when not logged in (used by the UI at start-up) |
| `GET` | `/api/health` | `{status, device_status, version}`, no auth (for Docker healthchecks) |
| `GET` | `/` and assets | The SPA; static files need no auth, all data goes through the authenticated WebSocket |

WebSocket `/ws` (cookie auth plus an `Origin` check). JSON messages `{type, ...}`:

| Direction | Type | Payload |
|---|---|---|
| S→C | `hello` | `client_id`, `name`, `server_version`, `demo`, `experimental`, `verified_kinds`, `profile` (channel counts, PEQ types, slopes, ratios, frequency/Q/delay ranges), `limits` (control ranges), `settings` |
| S→C | `snapshot` | `rev`, full `state` (device info, presets, channels) |
| S→C | `patch` | `rev`, `changes: [{path, value}]`, `origin` (client_id or `device`) |
| S→C | `meters` | `seq`, `levels` (12 values in dB or `null`; the whole field is `null` when the poll failed), `clip` (12 bools), `limit` (8 bools or `null`), `comp` (8 bools or `null`), `input_clip` |
| S→C | `device` | `status`, `error?`, `model`, `firmware` |
| S→C | `lock` | `owner_id?`, `owner_name?`, `idle_remaining_s?`, `idle_timeout_s` (relative time: no clock-skew issue) |
| S→C | `settings` | `meter_rate_hz`, `lock_idle_timeout_s` (sent on change) |
| S→C | `self` | `name` (after a `rename`) |
| S→C | `pong` | `req` |
| S→C | `clients` | list of `{id, name}` |
| S→C | `result` | `req`, `ok`, `error?` (`locked`, `invalid`, `experimental`, `device_offline`, `device_timeout`), `message?` |
| C→S | `set` | `req`, `path`, `value` |
| C→S | `preset.recall` | `req`, `slot` |
| C→S | `preset.store` | `req`, `slot` (1–20), `name` |
| C→S | `lock.acquire` / `lock.release` | `req` |
| C→S | `activity` | (no payload; user interaction, throttled to one every 10 s; resets the lock idle timer when sent by the owner) |
| C→S | `settings.set` | `req`, `meter_rate_hz` (clamped to 1–10) |
| C→S | `rename` | `req`, `name` (display name) |
| C→S | `resync` | `req` |
| C→S | `ping` | (keepalive; the server answers `pong`) |

At 5 Hz with 12 channels, meter messages are ~300 bytes, so JSON is fine. A binary frame is a
possible later optimisation, not a requirement.

## 6. Security model

The threat model is a trusted private LAN, with the goal of stopping casual or accidental access:

- one shared code; sessions are random 256-bit tokens kept in memory;
- login rate limit: 5 failures per IP, then a 30 s cool-down;
- WebSocket `Origin` must match the `Host` header (prevents cross-site WebSocket hijacking);
- the server validates and clamps every value; the client is never trusted for ranges or name
  lengths (a name over 14 characters can crash the DSP);
- plain HTTP. TLS is out of scope (LAN only); a reverse proxy can add it;
- the code can also come from an environment variable so that it does not show up in `ps` or
  `docker inspect` output.

## 7. Configuration (CLI)

Single entry point `dsp408-multiui`. Every option also reads `DSP408_<NAME>` from the environment.

```
dsp408-multiui serve --dsp-host 192.168.1.50 [options]   # "serve" is the default sub-command
  --dsp-port 9761          --host 0.0.0.0        --port 8080
  --pin 0000               --meter-rate 5        (1–10 Hz)
  --lock-idle-timeout 120  --resync-interval 0   (seconds, 0 = off)
  --command-timeout 0.5    --experimental        --profile file.toml
  --demo                   (demo mode: a simulated DSP inside this process, no device needed)
  --log-level info
dsp408-multiui probe  --dsp-host IP {info|meters|dump-config|diff-config|raw HEX}  # dev / RE
dsp408-multiui proxy  --listen 0.0.0.0:9761 --dsp-host IP --log frames.jsonl

dsp408-sim [--host 0.0.0.0] [--port 9761] [--scenario demo] [--state-dir DIR]   # separate program:
           [--preset SLOT=FILE] [--active N] [--fast] [--latency-ms] [--drop-rate] …  # fake DSP 408
```

The server keeps **no persistent state**: presets live in the DSP and settings come from the CLI,
with live changes kept in memory. There is **no database** and no data volume.

### 7.1 Launch modes

| Mode | Command | Needs |
|---|---|---|
| From a git clone | `git clone … && cd dsp408-multiui && uv run dsp408-multiui --dsp-host IP` | git, uv. **No Node**: the built UI is committed (see D9). |
| Standalone executable | Download `dsp408-multiui-<version>-<os>-<arch>` from the Gitea release page, then `./dsp408-multiui --dsp-host IP` | Nothing (Python is bundled). Targets: linux-amd64, linux-arm64, windows-amd64. |
| Docker | `docker run -d -p 8080:8080 -e DSP408_PIN=1234 <registry>/dsp408-multiui --dsp-host IP` | Docker |
| Docker Compose | `docker compose up -d` with the provided `compose.yaml` (settings through environment variables) | Docker Compose |
| Demo without a DSP | any of the above with `--demo` | — |
| Test bench without a DSP | `dsp408-sim` (executable, `uv run dsp408-sim`, or `docker compose -f compose.sim.yaml up`), then the app with `--dsp-host` pointing at it | — |

## 8. User interface

Mobile-first, dark theme by default (stage use), system font stack, no external assets.

**Global chrome.** A top bar shows the DSP status dot, the active preset name and the **lock
button**, which has three states: free / mine (idle countdown, tap to release) / other (owner's
name, read-only badge). A "DEMO" badge is shown in demo mode. On a phone, a bottom tab bar offers **Mixer ·
Matrix · Presets · Settings**; on desktop it becomes a side bar.

**Mixer.** Channel strips for In A–D, then Out 1–8. On a phone, the strips scroll horizontally
with "In / Out / All" filter chips; on desktop, all 12 strips fit on screen. Each strip shows:

- the name;
- the meter: bar, peak tick, clip LED and, on outputs, LIM and COMP LEDs;
- the gain value (tap it to type a value);
- a vertical fader;
- MUTE and Ø (phase) buttons.

A fader only reacts to a drag that **starts on its knob**, so scrolling the page never moves a
fader. ± step buttons allow precise adjustments. Tapping a strip name opens the channel detail.

**Channel detail** (sections):

- Inputs: gain/mute/phase, delay, HPF/LPF, PEQ (8 bands), Gate, GEQ (31 sliders, horizontally
  scrollable), name.
- Outputs: gain/mute/phase, delay, HPF/LPF, PEQ (9 bands), compressor, limiter, name.
- A linked channel shows which channels it is linked with: the DSP applies every change except
  the name and the matrix to the whole group, and the server mirrors that in its state.

Each PEQ band is a row with enable, type, frequency, gain and Q. Each field can be set by typing a
number, with steppers, or with a slider. There are **no response curves**.

**Matrix.** A grid of 4 inputs × 8 outputs with toggles. On a phone, outputs are the rows.

**Presets.** The list of U01–U20 (plus F00 for recall only), with the active preset highlighted.
Recall and Store actions both ask for confirmation, and Store has a 14-character name field.

**Settings.** Meter rate (global), my display name, connected clients, Refresh from device, DSP
model and firmware, version, logout.

## 9. Non-functional requirements

| Topic | Target |
|---|---|
| Control latency | Under 150 ms from a client action to the DSP ACK and the broadcast, on a LAN |
| Meter rate | Configured rate ±1 frame. A 30-client fan-out must not slow down DSP polling, because broadcasting is decoupled from polling. |
| Host hardware | Runs on a Raspberry Pi 3/4/5 (arm64) and on x86-64. The Docker image is multi-arch; standalone executables exist for linux-amd64, linux-arm64 and windows-amd64. |
| Resources | Under 100 MB RSS; idle CPU under 5 % on a Raspberry Pi 4 at 5 Hz |
| Browsers | Current Safari iOS, Chrome Android, Firefox and Chrome desktop |
| UI weight | Under 250 kB gzipped in total; first paint under 1 s on the LAN |
| Robustness | Survives a DSP power cycle, a network cable pull and a backend restart without manual action (clients reconnect) |
| Quality | `ruff` (lint and format), `mypy --strict` on `protocol/` and `state/`, pytest coverage ≥ 90 % on `protocol/` |

## 10. Out of scope / future

- Several DSPs from one backend: planned for in the design, not implemented.
- Import/export of the editor's preset files; automatic DSP discovery; DSP PIN unlock UI;
  channel link; matrix crosspoint gains; PWA "install to home screen"; UI translations
  (the code is i18n-ready, the UI ships in English).
- OSC, MQTT, a public REST API: explicitly not wanted.

## 11. Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | FastAPI + uvicorn, asyncio throughout | Native WebSocket support, Pydantic models, one process |
| D2 | Svelte 5 + TypeScript + Vite for the UI, built into the Python package | All-Python UI frameworks (NiceGUI, Reflex) round-trip every update through the server and make 5 Hz × 12 meters plus smooth faders on phones harder to get right. Svelte compiles to small, fast vanilla JS. |
| D3 | Backend state is authoritative; the store updates after the ACK | All clients converge on the device's real state |
| D4 | Coalescing per parameter key | Several people moving faders must not flood a one-request-at-a-time device |
| D5 | Unverified protocol items are gated by `--experimental` | We can ship verified features early, without risking wrong values on a live system |
| D6 | **No database** (owner requirement) | Presets live in the DSP; there is nothing else to persist |
| D7 | Activity-based lock with a 120 s idle timeout | The owner keeps the lock while working; a forgotten or disconnected client loses it automatically |
| D8 | Simulator first, protocol profile for uncertain details | No DSP is available during development; hardware verification later only adjusts the profile |
| D9 | The built UI (`src/dsp408_multiui/web/`) is committed to git; CI fails if it is out of date with `web/` sources | `git clone && uv run` works without Node. Only people who change the UI need Node. |
| D10 | Standalone executables built with PyInstaller in CI, one per OS/architecture | A single downloadable file, no Python or uv needed on the target machine |
| D11 | UI in English, French translation later | Owner decision |

| D12 | Standalone executable targets: linux-amd64, linux-arm64, windows-amd64 (no macOS) | Owner decision |
| D13 | CI runs on the Gitea **Docker runner**. arm64 builds use QEMU emulation (`binfmt` + `docker buildx`); the arm64 PyInstaller executable is built inside an emulated arm64 container. | Only a Docker runner is available. Emulated builds are slow but only run on release tags. The Windows executable is cross-built with Wine (`tobix/pywine`); it still has to be tested on a real Windows machine (docs/release.md). |

## 12. Open questions for the owner

None at this stage.
