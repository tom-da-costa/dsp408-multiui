# dsp408-multiui

Self-hosted web app to control a **t.racks DSP 408** over the network from several browsers
at once (phones first), with live metering.

One backend process owns the TCP connection to the DSP. It serves a mobile-first web UI to
every client on the local network and keeps them in sync in real time. It works fully offline.

> [!WARNING]
> **Unofficial software.** This project is not affiliated with, endorsed by or supported by
> Thomann, t.racks or Musicrown. The DSP protocol was reverse-engineered; the official editor
> remains the reference.
>
> **Vibe-coded.** Most of the code and documentation was written by an AI coding assistant
> (Claude Code), directed, reviewed and tested by a human on a real DSP 408. It is tested
> (unit, end-to-end and against hardware), but it has not been audited line by line.
>
> A DSP drives amplifiers and speakers: a wrong value can be loud or damage equipment. Try it
> on the simulator or on a spare preset first, keep backups of your presets, and use it at your
> own risk. The software comes with **no warranty** ([AGPL-3.0](LICENSE), sections 15–16).

Try it without a DSP: `uv run dsp408-multiui --demo`, then open http://localhost:8080 (code
`0000`).

## Features

- Gain, mute, phase, 4 → 8 routing matrix, PEQ (8 bands on inputs, 9 on outputs), high/low-pass
  filters and delay (in ms and metres) on every channel, compressor and limiter on outputs, noise
  gate and 31-band GEQ on inputs, channel names
- Channel links, as on the DSP: linked channels follow each other
- Frequency response graph on each channel page (filters, PEQ, GEQ), with other channels' curves
  as an overlay
- Limiter calculator: compressor and limiter thresholds from the amplifier gain and the speaker
  power, impedance and load
- DSP presets U01–U20: recall, store, rename, with an "unsaved changes" indicator
- Live meters per channel (level, peak, clip, limiter and compressor indicators), 5 Hz by default,
  adjustable from 1 to 10 Hz
- Multi-client: last writer wins by default, plus an exclusive lock held while the owner is
  active (released after 120 s of inactivity)
- Access protected by a shared code (default `0000`, set with `--pin`)
- No database, no internet access needed, no external assets
- `dsp408-sim`: a separate program that simulates a DSP 408 on the network, to test the app
  without a device (presets kept across restarts, fault injection, live console)

## Compatibility

| Component | Status |
|---|---|
| **t.racks DSP 408**, firmware **V0104P** | Supported. Every parameter the app edits was verified on this device: the DSP acknowledged the write and its config read showed the expected bytes |
| DSP 408 with another firmware | Probably works, not tested. Parameters behave the same as long as the protocol did not change; reports welcome |
| Other t.racks / Musicrown models (DSP 206, DSP 4x4 Mini, …) | Not supported. They share the protocol family but have other channel counts and config layouts |
| Connection to the DSP | Ethernet, TCP port 9761. No USB. Use the app **or** the official editor, not both at the same time |
| Server: Linux x86-64 and arm64 | Standalone executables (glibc ≥ 2.36: Debian 12, Ubuntu 24.04, Raspberry Pi OS bookworm 64-bit and later), Docker image, or `uv run` |
| Server: Raspberry Pi 3 / 4 / 5 | Designed for it (64-bit OS, arm64 executable or Docker image); not tested on a Pi yet |
| Server: Windows 10 / 11 x64 | Standalone executable built in CI; not tested on a real Windows machine yet |
| Server: macOS | No executable; `uv run` from a clone or Docker should work, not tested |
| Server: from source | Python ≥ 3.12 with [uv](https://docs.astral.sh/uv/); Node is not needed |
| Clients | Current Safari (iOS), Chrome (Android), Firefox and Chrome (desktop), at 360 px width and up |

## Usage

```bash
# From a clone (needs only uv)
git clone https://github.com/tom-da-costa/dsp408-multiui.git && cd dsp408-multiui
uv run dsp408-multiui --dsp-host 192.168.1.50 --pin 1234

# Demo without a DSP (a simulated DSP runs inside the app)
uv run dsp408-multiui --demo

# Docker
docker run -d -p 8080:8080 -e DSP408_PIN=1234 ghcr.io/tom-da-costa/dsp408-multiui --dsp-host 192.168.1.50

# Docker Compose
cp .env.example .env   # set DSP408_HOST, DSP408_PIN …
docker compose up -d
```

Standalone executables (linux-amd64, linux-arm64, windows-amd64) are attached to each
[release](https://github.com/tom-da-costa/dsp408-multiui/releases): download one and run
`./dsp408-multiui-<version>-linux-amd64 --dsp-host 192.168.1.50`. The latest build of `main` is
always available as the
[**main** pre-release](https://github.com/tom-da-costa/dsp408-multiui/releases/tag/main-latest)
(fixed file names, rebuilt on every push).

Then open `http://<server-ip>:8080` from any device on the LAN. Run
`dsp408-multiui --help` for every option; each one can also be set with a `DSP408_<NAME>`
environment variable.

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
| [CONTRIBUTING.md](CONTRIBUTING.md) | Development setup, checks, code rules, device safety |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, state model, command pipeline, simulator, client/server API, security |
| [docs/PROTOCOL.md](docs/PROTOCOL.md) | The DSP 408 network protocol, with a confidence level for each item and the open questions |
| [docs/captures.md](docs/captures.md) | How to capture protocol traffic (editor, proxy, probe) |
| [docs/release.md](docs/release.md) | Distribution and releases |

## Tech stack

Python ≥ 3.12 with uv, FastAPI and asyncio for the backend; Svelte 5, TypeScript and Vite for the
UI, built and embedded in the Python package; pytest, ruff and mypy for quality checks; CI on
GitHub Actions.

## Sources and credits

The protocol knowledge builds on the reverse-engineering work of these projects (all GPL-3.0).
[docs/PROTOCOL.md §0](docs/PROTOCOL.md) says how much each one is trusted.

| Project | Device | Transport | Used for |
|---|---|---|---|
| [Aeternitaas/dsp-408-ui](https://github.com/Aeternitaas/dsp-408-ui) | DSP 408 | TCP 9761 | The only prior source tested on a DSP 408 (Flutter app): framing, gain, mute, matrix, GEQ, presets, meter poll |
| [juli303/t-dsp-ui](https://github.com/juli303/t-dsp-ui) | DSP 408 | TCP 9761 | Identical fork of dsp-408-ui |
| [FlexiFlizz/t.racks-DSP-control](https://github.com/FlexiFlizz/t.racks-DSP-control) | DSP 206 | TCP + USB HID | Python driver and simulator: delay, phase, dynamics, slopes |
| [IMBArator/miniDSP-Linux](https://github.com/IMBArator/miniDSP-Linux) | DSP 4x4 Mini | USB HID | The most rigorous documentation of the protocol family: framing, ACKs, presets, link, meter tail |

The **Limiter calc** tab (`web/src/lib/limiter.ts`) implements the method of **Marc.O**'s
"Intelligent limiter threshold" calculator ([hornplans.free.fr/limiteur.html](http://hornplans.free.fr/limiteur.html)),
dBu mode: formulas and constants (open load AES / 1.5625, closed AES / 2.34375, amplifier at
half power, 0.775 V = 0 dBu). It is re-implemented from the published formulas; no code was
copied.

Files that reuse material from these projects keep their original notices:

| File in this repo | Origin |
|---|---|
| `tests/fixtures/config/forest_408.bin` | dsp-408-ui, `analyze5.py` (hex dump of a DSP 408 config read); 4 missing bytes filled with 0, see the `.meta.toml` |
| `tests/unit/test_framing.py` (frame vectors) | dsp-408-ui `protocol.dart` / `protocol_service.dart`; miniDSP-Linux `analysis/protocol.md` |
| `tests/unit/test_meters.py` (24-bit vectors) | miniDSP-Linux `analysis/protocol.md` (sine-sweep meter triplets) |

GPL-3.0 code may be combined with this AGPL-3.0 project (GPLv3 §13 / AGPLv3 §13).

## License

[GNU AGPL-3.0](LICENSE). t.racks is a brand of Thomann; the names are used only to describe
compatibility.
