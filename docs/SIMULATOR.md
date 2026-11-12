# Testing without a DSP: `tracks-dsp-controller sim`

`tracks-dsp-controller sim` runs a simulated t.racks DSP on the network (TCP port 9761), in a
process of its own. The app, started as a second process, connects to it exactly as to the real
device, so the whole path is tested: connection, init sequence, timeouts, reconnects, several
clients. From a clone, `uv run tracks-dsp-sim` is the same command.

For a quick look, `tracks-dsp-controller --demo` runs the same simulated device inside the app,
with no second program.

## Running it

```bash
# Terminal 1: the simulated DSP (listens on 0.0.0.0:9761, like a real one)
uv run tracks-dsp-controller sim --state-dir sim-state
# Terminal 2: the app, pointed at it (or at the IP of the machine running the simulator)
uv run tracks-dsp-controller --dsp-host 127.0.0.1

# Both in Docker; `docker attach tracks-dsp-sim` opens the simulator console
docker compose -f compose.sim.yaml up -d
```

The standalone executable of each
[release](https://github.com/tom-da-costa/tracks-dsp-controller/releases) includes it:

```bash
./tracks-dsp-controller-<version>-linux-amd64 sim --model 206           # terminal 1
./tracks-dsp-controller-<version>-linux-amd64 --dsp-host 127.0.0.1      # terminal 2
```

Up to 0.7 the simulator was a separate executable, `tracks-dsp-sim-<version>-…`.

## Options

Every option also reads a `TDSP_SIM_<NAME>` environment variable
(`TDSP_SIM_MODEL=206`). `tracks-dsp-controller sim --help` lists them all.
The options go after `sim`.

| Option | Default | What it does |
|---|---|---|
| `--model 408\|206\|204` | `408` | The simulated device. The 206 follows captures of a real DSP 206, the 204 the protocol notes of BetterDSPControl, tested on a real 204 ([PROTOCOL.md §10](PROTOCOL.md)). The app detects the model it is connected to |
| `--host`, `--port` | `0.0.0.0`, `9761` | Listen address and port. `--host 127.0.0.1` keeps it off the network |
| `--scenario demo\|silent\|clipping\|stress` | `demo` | Initial presets and input signals |
| `--preset SLOT=FILE` | | Loads a config dumped from a real DSP (`tracks-dsp-controller probe dump-config`), or a preset file of the official editor (`.prs`), of the same model, into user preset SLOT (1-20). Repeatable: `--preset 8=u08.bin` |
| `--active N` | | Active preset at start-up (0 = F00) |
| `--state-dir DIR` | | Keeps stored presets and the active preset across restarts (one `Uxx.bin` per preset, the format of `probe dump-config`) |
| `--device-id N` | 1 (2 for a 206) | The front-panel ID number, 1-250: the simulated DSP only answers frames sent to it |
| `--identity TEXT` | the model's | The reply to the identity request (`0x13`) |
| `--fast` | | Answers preset recall and store at once (a DSP 408 takes about 3 s and 7 s) |
| `--second-client queue\|accept\|refuse\|kick` | `queue` | What a second TCP client gets. `queue` is what a DSP 408 does: the connection waits, unanswered, until the first client leaves |
| `--latency-ms`, `--drop-rate`, `--corrupt-rate`, `--nan-rate` | 0 | Fault injection: delay every answer, drop, corrupt, or send meter frames without data |
| `--frame-log FILE` | | Appends every frame to this JSONL file |
| `--console auto\|on\|off` | `auto` | Interactive console on stdin (`auto`: when run in a terminal) |
| `--log-level`, `--profile` | `info` | As for `tracks-dsp-controller` |

## Console

When run in a terminal, type `help` for the full list:

| Command | Effect |
|---|---|
| `status`, `presets` | Show the live state and the stored presets |
| `recall N` | Recall preset N, as from the front panel |
| `kick` | Drop the connections |
| `offline 10` | Unreachable for 10 s |
| `latency 200`, `drop 0.1` | Change the fault injection |
| `signal A steady -3` | Set the signal of input A |
| `quit` | Stop |

## How faithful it is

The simulator reproduces the DSP 408's recorded behaviour (`tests/hardware/`): the init
sequence, ACKs, config reads, preset recall and store timings, links, meters (an input meter
reads before the input mute, a muted output reads zero) and a second client that is kept
waiting. [ARCHITECTURE.md](ARCHITECTURE.md) describes its design, and
[PROTOCOL.md](PROTOCOL.md) gives the confidence level of each protocol detail it relies on.
