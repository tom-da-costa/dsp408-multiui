# dsp408-multiui

Self-hosted web app to control a **t.racks DSP 408** over the network from several browsers
at once (phones first), with live metering.

One backend process owns the TCP connection to the DSP. It serves a mobile-first web UI to
every client on the local network and keeps them in sync in real time. It works fully offline.

> **Status: in development, not yet tested on a real DSP 408.** Everything runs against the
> built-in simulator: `uv run dsp408-multiui --simulator`, then open http://localhost:8080
> (code `0000`). Progress is tracked in [docs/PROGRESS.md](docs/PROGRESS.md).

## Planned features

- Gain, mute, phase, 4 → 8 routing matrix, PEQ (8 bands on inputs, 9 on outputs), high/low-pass
  filters, delay, compressor and limiter; then noise gate, 31-band GEQ and channel names
- DSP presets U01–U20: recall, store, rename
- Live meters per channel (level, peak, clip, limiter and compressor indicators), 5 Hz by default,
  adjustable from 1 to 10 Hz
- Multi-client: last writer wins by default, plus an exclusive lock held while the owner is
  active (released after 120 s of inactivity)
- Access protected by a shared code (default `0000`, set with `--pin`)
- No database, no internet access needed, no external assets
- Protocol-accurate DSP simulator for development, tests and demos

## Usage

```bash
# From a clone (needs only uv)
git clone <repo-url> && cd dsp408-multiui
uv run dsp408-multiui --dsp-host 192.168.1.50 --pin 1234

# Demo without a DSP
uv run dsp408-multiui --simulator

# Docker
docker run -d -p 8080:8080 -e DSP408_PIN=1234 <registry>/dsp408-multiui --dsp-host 192.168.1.50

# Docker Compose
cp .env.example .env   # set DSP408_HOST, DSP408_PIN …
docker compose up -d
```

Standalone executables (linux-amd64, linux-arm64, windows-amd64) will be attached to each
release. Then open `http://<server-ip>:8080` from any device on the LAN.

## Documentation

| Document | Content |
|---|---|
| [docs/SPEC.md](docs/SPEC.md) | Requirements, architecture, client/server API, UI, decisions |
| [docs/PLAN.md](docs/PLAN.md) | Phased implementation plan, testing strategy, risks |
| [docs/PROTOCOL.md](docs/PROTOCOL.md) | Cross-referenced synthesis of the DSP network protocol, with confidence levels and open questions |
| [docs/SOURCES.md](docs/SOURCES.md) | Prior reverse-engineering projects and reuse rules |

## Tech stack (planned)

Python ≥ 3.12 with uv, FastAPI and asyncio for the backend; Svelte 5, TypeScript and Vite for the
UI, built and embedded in the Python package; pytest, ruff and mypy for quality checks; CI on
Gitea Actions.

## Credits and license

The protocol knowledge builds on the reverse-engineering work listed in
[docs/SOURCES.md](docs/SOURCES.md). This project is not affiliated with Thomann, t.racks or
Musicrown.

Licensed under the [GNU AGPL-3.0](LICENSE).
