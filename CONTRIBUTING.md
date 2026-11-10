# Contributing

Thanks for your interest! Bug reports, protocol findings and pull requests are welcome. This is a
hobby project maintained in spare time, so answers may take a while.

Before you start, read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (how the code is organised)
and, for anything that touches the device, [docs/PROTOCOL.md](docs/PROTOCOL.md).

## Development setup

You need [uv](https://docs.astral.sh/uv/) (it installs Python ≥ 3.12 if needed). Node 22 is only
needed to work on the UI; without it, the `make` targets fall back to a `node:22-alpine` Docker
image.

```bash
uv sync                              # install the backend and dev tools
uv run tracks-dsp-controller --demo  # app + in-process simulated DSP on :8080 (code 0000)
make dev                             # UI with hot reload on :5173, backend --demo on :8080
```

To test the real network path, run the simulator as a separate program:

```bash
uv run dsp408-sim --host 127.0.0.1                 # simulated DSP 408 on :9761, with a console
uv run tracks-dsp-controller --dsp-host 127.0.0.1  # the app, connected to it like to a real DSP
```

## Checks

Run what CI runs before opening a pull request:

```bash
make check     # ruff lint + format check, mypy, pytest, end-to-end tests
make web-test  # svelte-check + vitest (UI changes)
make web       # rebuild the committed UI (UI changes)
```

- `mypy` is strict on `protocol/` and `state/`; coverage on `protocol/` must stay at 90 % or more.
- The built UI in `src/tracks_dsp_controller/web/` is committed, so that `uv run` works without Node.
  After any change in `web/`, run `make web` and commit the result with your sources; CI fails if
  the build is stale.

## Rules of the code base

- `protocol/` is pure: no I/O and no imports from the rest of the project. The backend and the
  simulator share it.
- Only `device/session.py` talks to the transport. All DSP traffic goes through the single
  command pipeline (one request in flight, coalescing per parameter key, a guaranteed meter slot).
- The backend state is authoritative and is updated **after** the DSP ACK; every change reaches
  all clients as a patch with a `rev`.
- Clients send physical units (dB, Hz, ms). The server validates, clamps and quantises; it never
  trusts client ranges.
- Frame on the `LEN` byte, never by searching for `10 03` (the payload can contain those bytes).
- Fully offline: no CDN, web fonts, telemetry or any other external request, at runtime or in the
  built UI.
- Mobile first: check your UI change at 360 px width. A fader only moves on a drag that starts on
  its knob.

## Device safety

The DSP 408 drives real sound systems, so a few things are off limits:

- never store to preset slot 0 (F00);
- preset names: at most 14 printable ASCII characters (longer names can crash the firmware);
- do not implement the test-tone generator (`0x39`) or the device-PIN setter (`0x2f`);
- a parameter that has not been verified on a real DSP 408 stays out of `HARDWARE_VERIFIED`
  (`state/registry.py`), so it is only writable with `--experimental`.

**Develop and test against the simulator.** If you test on a real DSP, use a copy of a preset in
a free slot, dump the config first (`tracks-dsp-controller probe --dsp-host IP dump-config`), and
compare after restoring. Never run the app and the official editor against the same DSP at the
same time.

## Protocol findings

Captures from the official editor or a real device are very welcome, especially for the open
questions of [PROTOCOL.md §9](docs/PROTOCOL.md) and for other firmware versions.
[docs/captures.md](docs/captures.md) explains how to record them. When a question is answered,
update these together:

1. the confidence tag in `docs/PROTOCOL.md`;
2. the defaults in `src/tracks_dsp_controller/protocol/profiles/default.toml`;
3. the fixtures in `tests/` and the tests that replay them.

## Pull requests

- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat:`, `fix:`, `docs:`, `ci:` …).
- Code, comments, docs and UI strings are in English.
- Keep a pull request focused on one topic, and update the docs it affects.
- Code or test vectors copied from another project keep their copyright notice and get a row in
  the attribution table of the [README](README.md#sources-and-credits). Reference projects can be
  cloned outside the repository; do not vendor them.

## License

By contributing, you agree that your contributions are licensed under the
[GNU AGPL-3.0](LICENSE), like the rest of the project.
