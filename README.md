# dsp408-multiui

Self-hosted web app to control a **t.racks DSP 408** over the network from several browsers
at once (phones first), with live metering.

One backend process owns the TCP connection to the DSP. It serves a mobile-first web UI to
every client on the local network and keeps them in sync in real time. It works fully offline.

> **Status: in development, verified on a real DSP 408 (firmware V0104P).** Try it without a
> DSP: `uv run dsp408-multiui --demo`, then open http://localhost:8080 (code `0000`).
> Progress is tracked in [docs/PROGRESS.md](docs/PROGRESS.md).

## Features

- Gain, mute, phase, 4 → 8 routing matrix, PEQ (8 bands on inputs, 9 on outputs), high/low-pass
  filters and delay (in ms and metres) on every channel, compressor and limiter on outputs, noise
  gate and 31-band GEQ on inputs, channel names; linked channels follow each other as on the DSP
- DSP presets U01–U20: recall, store, rename
- Live meters per channel (level, peak, clip, limiter and compressor indicators), 5 Hz by default,
  adjustable from 1 to 10 Hz
- Multi-client: last writer wins by default, plus an exclusive lock held while the owner is
  active (released after 120 s of inactivity)
- Access protected by a shared code (default `0000`, set with `--pin`)
- No database, no internet access needed, no external assets
- `dsp408-sim`: a separate program that simulates a DSP 408 on the network, to test the app
  without a device (presets kept across restarts, fault injection, live console)

## Usage

```bash
# From a clone (needs only uv)
git clone <repo-url> && cd dsp408-multiui
uv run dsp408-multiui --dsp-host 192.168.1.50 --pin 1234

# Demo without a DSP (a simulated DSP runs inside the app)
uv run dsp408-multiui --demo

# Docker
docker run -d -p 8080:8080 -e DSP408_PIN=1234 ghcr.io/OWNER/dsp408-multiui --dsp-host 192.168.1.50

# Docker Compose
cp .env.example .env   # set DSP408_HOST, DSP408_PIN …
docker compose up -d
```

The latest build of `main` is always available as the
[**main** pre-release](https://github.com/OWNER/dsp408-multiui/releases/tag/main-latest) (fixed
file names, rebuilt on every push). Standalone executables (linux-amd64, linux-arm64,
windows-amd64) are attached to each [release](https://github.com/OWNER/dsp408-multiui/releases): download one and run `./dsp408-multiui-<version>-linux-amd64 --dsp-host 192.168.1.50`.
Then open `http://<server-ip>:8080` from any device on the LAN. See
[docs/release.md](docs/release.md) for how releases are built.

## On a phone

- **Live** view (first tab): per channel, CLIP / CMP / LIM indicators, a meter graduated every
  10 dB with the compressor (C) and limiter (L) thresholds, the gain fader with − / + and MUTE.
- **Full screen:** the ⛶ button at the bottom of the tab bar (Android, desktop browsers).
- **Install on the home screen:** iPhone: Safari › Share › *Add to Home Screen*; it then opens
  full screen without the browser bars. Android: Chrome installs web apps only over HTTPS (or
  on localhost); over plain `http://` on the LAN, use the full-screen button, or put the app
  behind an HTTPS reverse proxy with a valid certificate to get *Install app*.

## Testing without a DSP: `dsp408-sim`

`dsp408-sim` is a separate program that behaves like a DSP 408 on the network (TCP port 9761).
The app connects to it exactly as to the real device, so the whole path is tested: connection,
init sequence, timeouts, reconnects, several clients.

```bash
# Terminal 1: the simulated DSP (listens on 0.0.0.0:9761, like a real one)
uv run dsp408-sim --state-dir sim-state
# Terminal 2: the app, pointed at it (or at the IP of the machine running dsp408-sim)
uv run dsp408-multiui --dsp-host 127.0.0.1

# Both in Docker; `docker attach dsp408-sim` opens the simulator console
docker compose -f compose.sim.yaml up -d
```

- `--state-dir DIR` keeps stored presets and the active preset across restarts (one `Uxx.bin`
  per preset, the same format as `dsp408-multiui probe dump-config`).
- `--preset 8=u08.bin` loads a config dumped from a real DSP into U08.
- `--scenario demo|silent|clipping|stress` sets the initial presets and input signals.
- `--fast` answers preset recall and store at once (the real DSP takes about 3 s and 7 s).
- `--latency-ms`, `--drop-rate`, `--corrupt-rate`, `--nan-rate` and `--second-client
  accept|refuse|kick` inject faults.
- Console (when run in a terminal; type `help`): `status`, `presets`, `recall N` (front-panel
  recall), `kick` (drop the connections), `offline 10` (unreachable for 10 s), `latency 200`,
  `drop 0.1`, `signal A steady -3`, `quit`.

Every option also reads a `DSP408_SIM_<NAME>` environment variable. A `dsp408-sim` executable is
attached to each release next to the app's.

## Documentation

| Document | Content |
|---|---|
| [docs/SPEC.md](docs/SPEC.md) | Requirements, architecture, client/server API, UI, decisions |
| [docs/PLAN.md](docs/PLAN.md) | Phased implementation plan, testing strategy, risks |
| [docs/PROTOCOL.md](docs/PROTOCOL.md) | Cross-referenced synthesis of the DSP network protocol, with confidence levels and open questions |
| [docs/SOURCES.md](docs/SOURCES.md) | Prior reverse-engineering projects and reuse rules |
| [docs/PROGRESS.md](docs/PROGRESS.md) | Implementation progress |
| [docs/captures.md](docs/captures.md) | How to capture protocol traffic (editor, proxy, probe) |
| [docs/release.md](docs/release.md) | Distribution and releases |

## Tech stack

Python ≥ 3.12 with uv, FastAPI and asyncio for the backend; Svelte 5, TypeScript and Vite for the
UI, built and embedded in the Python package; pytest, ruff and mypy for quality checks; CI on
GitHub Actions.

## Credits and license

The protocol knowledge builds on the reverse-engineering work listed in
[docs/SOURCES.md](docs/SOURCES.md). This project is not affiliated with Thomann, t.racks or
Musicrown.

Licensed under the [GNU AGPL-3.0](LICENSE).
