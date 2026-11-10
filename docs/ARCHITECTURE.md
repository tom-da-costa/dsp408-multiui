# Architecture

How tracks-dsp-controller is built: components, state, the command pipeline to the DSP, the simulator,
the client/server API and the security model. The device protocol itself is in
[PROTOCOL.md](PROTOCOL.md).

```
 phone ─┐                     ┌─────────────────────────────────────┐   TCP 9761   ┌─────────┐
 phone ─┼── HTTP + WebSocket ─┤  tracks-dsp-controller (1 process)  ├──────────────┤ DSP 408 │
 PC ────┘      (LAN only)     │  FastAPI · state · protocol         │ (sole client)└─────────┘
                              └─────────────────────────────────────┘
```

## 1. Constraints

| Constraint | Consequence |
|---|---|
| Private LAN, no internet access at the venue | No CDN, no external fonts, no telemetry: every asset ships in the package. |
| Clients are phones first, then desktop and tablet | Mobile-first layout, touch-safe controls, works at 360 px width. |
| DSP connected to the network over Ethernet | TCP client only, no USB. |
| Start with one command | One process serves the API, the WebSocket and the static UI. |
| No database | Presets live in the DSP; the server keeps only in-memory state. |
| The DSP drives a real sound system | A protocol-accurate simulator is used for development and tests; parameters not verified on hardware stay behind `--experimental`. |

## 2. Components

A single Python process, asyncio throughout.

```
src/tracks_dsp_controller/
  protocol/   pure, I/O-free: framing, checksum, value codecs, command builders, response parsers,
              config-blob map (offsets → model), protocol profile
  device/     asyncio TCP transport · CommandPipeline (queue, coalescing, ACK/timeout) ·
              DeviceSession (init, polling, reconnect, resync)
  state/      Pydantic models of the device state · StateStore (authoritative mirror, revision
              counter, change events) · parameter registry (path → validator, encoder, opcode)
  server/     FastAPI app · auth (code, sessions) · WebSocket hub (fan-out) · LockManager ·
              static file serving of the built UI
  simulator/  protocol-accurate fake DSP 408, 206 or 204 (asyncio TCP server), see §5
  tools/      CLI sub-commands: probe, proxy (frame logger)
  web/        built UI, generated from /web and committed
web/          Svelte 5 + TypeScript + Vite sources of the UI
```

Rules:

- `protocol/` imports nothing from the rest of the code base and does no I/O. The backend and
  the simulator share it.
- Only `DeviceSession` talks to the transport.
- No global singleton for the device: the server depends on `StateStore` and `DeviceSession`, so
  a future `DeviceManager` (several DSPs) stays a mechanical change.
- The built UI is committed, so `git clone && uv run` works without Node. CI fails when it is out
  of date with the sources in `web/`.

## 3. State model

- The backend holds the **authoritative mirror** of the DSP state, read from the config blob at
  connect time and after every recall, link change or resync.
- Every parameter has a **path**: its dotted location in the JSON snapshot, with zero-based
  indexes, e.g. `outputs.3.gain_db`, `outputs.3.peq.2` (a whole band; partial objects are
  merged), `inputs.1.geq.17`, `outputs.5.matrix` (one boolean per input),
  `outputs.2.crossover.hpf`, `outputs.2.compressor`. Clients write with the same paths they use to
  apply patches. The registry (`state/registry.py`) maps each path to:
  1. a schema with units and bounds (clients send **physical units**: dB, Hz, ms);
  2. a quantiser (snap to the device's steps);
  3. an encoder that builds the frame;
  4. a coalescing key.
- `StateStore` keeps a monotonically increasing `rev`. Every change produces a `patch` with the
  new `rev`. A client that detects a gap asks for a full snapshot.
- Linked channels: the DSP applies a write to every member of a link group (except names and
  matrix), and the store mirrors that.
- Parameter kinds not yet verified on a DSP 408 are left out of `HARDWARE_VERIFIED` in the
  registry. On a real DSP they are refused unless `--experimental` is given. Against the
  simulator, everything is enabled.

## 4. Command pipeline

The DSP handles one request at a time ([PROTOCOL.md §1](PROTOCOL.md)), so all traffic goes
through a single queue (`device/pipeline.py`):

1. **Coalescing.** A pending write for an existing key replaces the queued value in place. A
   fader dragged by three clients therefore produces at most one frame in flight and one pending
   frame per key.
2. **Priorities.** Writes come before meter polls, but when the meter period has elapsed the next
   free slot goes to a poll, which guarantees the configured rate (and at least 1 Hz).
3. **Barriers.** Preset recall/store, link changes and resync are exclusive sequences with long
   timeouts. Writes received in the meantime wait in the queue.
4. **ACK handling.** Timeout of 500 ms (`--command-timeout`) and one retry. On failure, the server
   reports an error, marks the parameter for re-read and, after several consecutive failures,
   reconnects.
5. **Ordering.** The state store is updated, and the patch broadcast, **after** the DSP
   acknowledges the write, so every client converges on what the device accepted.

The device session goes through `connecting → initialising → online ↔ offline`. It reconnects
with exponential backoff (1 s → 30 s) and re-reads the full state after reconnecting.

### Client behaviour

- **Optimistic UI.** Controls move immediately and send values throttled to ~20 Hz while being
  dragged. While the user drags, server patches for that control are ignored; on release, the
  control snaps to the last server value.
- **Rejected writes** (lock, validation, device error) restore the server value and show a toast.
- The client reconnects its WebSocket automatically and gets a fresh snapshot. If the session is
  gone (server restart), it shows the login screen.
- A fader only moves on a drag that starts on its knob, so scrolling never moves a fader.

### Multi-client rules

- Each client has a display name, chosen at login; it cannot be changed during the session.
- Any number of clients see the same state. By default the **last writer wins**: writes are
  applied in arrival order and the result goes to every client, the sender included.
- A client can take an **exclusive lock**; every other client is then read-only (meters keep
  working). The owner keeps it while active: any write, preset or lock action, or UI interaction
  (reported with a throttled `activity` message). It is released on request, on logout, or after
  120 s without activity (`--lock-idle-timeout`).

## 5. Simulator

A fake DSP that the backend cannot tell apart from the device, as far as the protocol is known.
It plays a DSP 408 by default, or a 206 or 204 (`--model`, `simulator/models.py`): the model
selects a built-in protocol profile (§6) and the bytes of the init replies. The 206 follows
captures of a real device, the 204 the notes of an app tested on one ([PROTOCOL.md §10](PROTOCOL.md)).

- An asyncio TCP server (default port 9761). It reuses `protocol/` to decode requests and encode
  responses.
- It holds a full device state (20 presets plus F00, live config) and answers every implemented
  opcode: init sequence, config pages, preset recall/store, parameter writes with ACKs, links,
  meter polls. Each TCP connection needs its own init sequence, as on the 408.
- Meters are synthetic and scriptable per channel (silence, sine level, noise, clipping, limiter
  or compressor active).
- Fault injection: latency, dropped responses, malformed frames, NaN meters, disconnects, slow
  recall/store, refusal of a second TCP client.
- It loads the same protocol profile as the backend (§6) and logs every frame it receives, so the
  official editor can be pointed at it to capture its requests ([captures.md](captures.md)).
- It is a **separate program**, `tracks-dsp-sim`, reached over TCP like a real DSP, so tests
  cover the real network path. The **demo mode** (`serve --demo`) runs the same simulated device inside the
  backend process.

## 6. Protocol profile

Every protocol detail that is not certain is a field of a `ProtocolProfile`
(`protocol/profile.py`, defaults in `protocol/profiles/default.toml`): meter decoder, slots and
tail bytes, frequency step count and Q scale, delay sample rate, compressor and limiter layouts,
slope table, device address, channel counts, config pages, command timeouts. Other models are
small files layered on top of the 408 defaults (`dsp206.toml`, `dsp204.toml`,
`load_profile(model=...)`); the config blob layout follows the channel counts
(`ConfigLayout` in `protocol/config_map.py`). Verifying something on hardware changes profile values
and test fixtures, not the architecture. The profile can be overridden with `--profile file.toml`.

## 7. Client ↔ server API

HTTP (JSON):

| Method | Path | Body / result |
|---|---|---|
| `POST` | `/api/login` | `{pin, name?}` → sets the `session` cookie (HttpOnly, SameSite=Strict); 401 on a wrong code |
| `POST` | `/api/logout` | Clears the session and releases any lock it held |
| `GET` | `/api/session` | `{authenticated, client_id, name}`; 401 when not logged in |
| `GET` | `/api/health` | `{status, device_status, version}`, no auth (Docker healthcheck) |
| `GET` | `/` and assets | The single-page app; static files need no auth, all data goes through the authenticated WebSocket |

WebSocket `/ws` (cookie auth plus an `Origin` check). JSON messages `{type, ...}`:

| Direction | Type | Payload |
|---|---|---|
| S→C | `hello` | `client_id`, `name`, `server_version`, `demo`, `experimental`, `verified_kinds`, `profile` (channel counts, PEQ types, slopes, ratios, frequency/Q/delay ranges), `limits`, `settings` |
| S→C | `snapshot` | `rev`, full `state` (device info, presets, channels, `modified`: the live setup changed since the last recall or store, `null` when unknown) |
| S→C | `patch` | `rev`, `changes: [{path, value}]`, `origin` (client_id or `device`) |
| S→C | `meters` | `seq`, `levels` (12 values in dB or `null`; the whole field is `null` when the poll failed), `clip` (12 bools), `limit` (8 bools or `null`), `comp` (8 bools or `null`), `input_clip` |
| S→C | `device` | `status`, `error?`, `model`, `firmware` |
| S→C | `lock` | `owner_id?`, `owner_name?`, `idle_remaining_s?`, `idle_timeout_s` |
| S→C | `settings` | `meter_rate_hz`, `lock_idle_timeout_s` (sent on change) |
| S→C | `clients` | list of `{id, name}` |
| S→C | `result` | `req`, `ok`, `error?` (`locked`, `invalid`, `experimental`, `device_offline`, `device_timeout`), `message?` |
| S→C | `pong` | `req` |
| C→S | `set` | `req`, `path`, `value` |
| C→S | `preset.recall` | `req`, `slot` |
| C→S | `preset.store` | `req`, `slot` (1–20), `name` |
| C→S | `lock.acquire` / `lock.release` | `req` |
| C→S | `activity` | no payload; user interaction, throttled to one every 10 s |
| C→S | `settings.set` | `req`, `meter_rate_hz` (clamped to 1–10) |
| C→S | `resync` | `req` |
| C→S | `link.set` | `req`, `side` (`inputs` / `outputs`), `groups` (lists of channel indices; channels in no group are unlinked) |
| C→S | `ping` | keepalive |

`web/src/lib/types.ts` mirrors these messages and `state/models.py`.

## 8. Security model

The threat model is a trusted private LAN; the goal is to stop casual or accidental access.

- One shared code (`--pin`, or `DSP408_PIN` so that it does not show in `ps` or
  `docker inspect`); a warning is logged while the default `0000` is in use.
- Sessions are random 256-bit tokens kept in memory; they end on logout or server restart.
- Login rate limit: 5 failures per IP, then a 30 s cool-down.
- The WebSocket `Origin` must match the `Host` header (no cross-site WebSocket hijacking).
- The server validates, clamps and quantises every value; it never trusts client ranges or name
  lengths (a preset name over 14 characters can crash the DSP firmware).
- Plain HTTP; put a reverse proxy in front for TLS.
- Device safety: no store to preset F00, no test-tone generator (`0x39`), no device-PIN setter
  (`0x2f`).

## 9. Command line

Every option also reads `DSP408_<NAME>` from the environment.

```
tracks-dsp-controller [serve] --dsp-host 192.168.1.50 [options]   # "serve" is the default sub-command
  --dsp-port 9761          --host 0.0.0.0        --port 8080
  --pin 0000               --meter-rate 5        (1–10 Hz)
  --lock-idle-timeout 120  --resync-interval 0   (seconds, 0 = off)
  --command-timeout 0.5    --experimental        --profile file.toml
  --demo [--demo-scenario demo|silent|clipping|stress]
  --log-level info
tracks-dsp-controller probe --dsp-host IP {info|meters|dump-config|diff-config|raw HEX}
tracks-dsp-controller proxy --listen 0.0.0.0:9761 --dsp-host IP --log frames.jsonl

tracks-dsp-sim [--model 408|206|204] [--host 0.0.0.0] [--port 9761] [--scenario demo]
               [--state-dir DIR] [--preset SLOT=FILE] [--fast] [--latency-ms N] …
```

## 10. Design choices

| Choice | Why |
|---|---|
| FastAPI + uvicorn, asyncio | Native WebSocket support, Pydantic models, one process |
| Svelte 5 + TypeScript + Vite, built into the Python package | Server-driven Python UI frameworks round-trip every update through the server, which makes 5 Hz × 12 meters and smooth faders on phones harder. Svelte compiles to small vanilla JS. |
| Store updated after the DSP ACK | Every client converges on the device's real state |
| Coalescing per parameter key | Several people moving faders must not flood a one-request-at-a-time device |
| `--experimental` gate for unverified parameters | Ship verified features without risking wrong values on a live system |
| No database | Presets live in the DSP; nothing else needs to persist |
| Simulator first, protocol profile for uncertain details | Development and CI without a DSP; hardware verification only adjusts the profile |
| Standalone executables with PyInstaller (linux-amd64, linux-arm64, windows-amd64) | One downloadable file, no Python needed on the target machine |
