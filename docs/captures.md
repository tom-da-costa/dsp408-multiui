# Capturing protocol traffic

How to record frames between the official *DSP Processor Editor* and a DSP 408 (or our
simulator), and how to turn the recordings into test fixtures. This is how the open questions of
[PROTOCOL.md §9](PROTOCOL.md) get answered.

## Tools

| Tool | Command | Use |
|---|---|---|
| Simulator | `uv run dsp408-sim --frame-log editor.jsonl` (or the `dsp408-sim` Windows executable) | Fake DSP; logs every request it receives |
| Proxy | `uv run dsp408-multiui proxy --dsp-host <DSP-IP> --log session.jsonl` | Sits between the editor and a real DSP; logs both directions |
| Probe | `uv run dsp408-multiui probe --dsp-host <IP> {info,meters,dump-config,diff-config,raw}` | Query the device directly |
| Wireshark | filter `tcp.port == 9761` | Fallback when the editor cannot be pointed at an arbitrary IP |

Each line of a JSONL frame log is `{"ts", "dir", "hex", "decoded"}`. `dir` is `host->dsp` or
`dsp->host`.

## Editor against the simulator (no DSP needed)

Goal: learn how the editor **encodes requests**. This answers Q2–Q7 and Q12.

1. On the Linux machine, run:
   `uv run dsp408-sim --scenario demo --frame-log editor.jsonl` (it listens on all interfaces).
   Open TCP port 9761 in the firewall if needed.
2. On the Windows PC, start the editor and connect to the Linux machine's IP. If the editor only
   offers device discovery, try entering the IP manually. If that is impossible, use the proxy
   method below with a real DSP.
3. If the editor connects and shows the demo presets ("Demo 3-way", "Mono Sub"), the simulator's
   init responses were accepted. If it hangs, keep the log: it shows the last request the editor
   waited on.
4. Do **one action per capture**. Restart the simulator with a new `--frame-log` file for each
   action, and write down the exact values shown in the editor UI:

| Question | Actions in the editor | Values to note |
|---|---|---|
| Q2 frequency / Q | Out1 PEQ band 1: set 1000 Hz, then 100 Hz, then 10 kHz; Q 1.0, then 4.0, then 0.5 | Displayed Hz and Q |
| Q3 delay | Out1 delay: 0, 1 ms, 10 ms, 100 ms, maximum | Displayed ms and maximum |
| Q4 dynamics | Out1 compressor: change each parameter alone; same for the limiter | Displayed values |
| Q5 slopes | Out1 HPF: step through every slope; bypass on/off | Slope names, in order |
| Q6 gate / phase / names / link | Gate on In A (each parameter); phase on In A and Out1; rename Out1; link Out1+Out2 | Displayed values |
| Q7 crosspoint gain | Change the In A → Out1 matrix level, if the editor has one | Displayed dB |
| Q12 input filters / delay | Check whether inputs have HPF/LPF or delay in the UI; capture if so | — |

5. Save each log as `tests/fixtures/editor/<question>_<action>.jsonl`, with a sidecar
   `<same name>.meta.toml` (format below).

## Editor against the real DSP (proxy)

Goal: learn how the **device answers**. This answers Q1 and Q8–Q11.

1. Run `uv run dsp408-multiui proxy --dsp-host <DSP-IP> --log session.jsonl` on a machine that
   can reach the DSP, and point the editor at that machine.
2. Q1 (meters): play a steady sine of known level into In A, then raise the gain until the clip
   LED lights. Trigger the limiter on Out1 by lowering its threshold. Then run
   `probe meters --watch` on its own (editor closed) and compare the float16 and level24
   columns.
3. Q8–Q10: capture a full connect; also try `probe info` while the editor is connected.
4. Q11 (config map): for each unknown field, `probe dump-config -o before.bin`, then change one
   value in the editor (mute Out3, phase Out3, delay Out3 = 10 ms, bypass one PEQ band), then
   `probe dump-config -o after.bin`, then `probe diff-config before.bin after.bin`. The diff
   prints field names; a hypothesis field (`… (HYP)`) changing confirms it.

## Fixture metadata (`.meta.toml`)

```toml
device = "DSP 408"            # or "simulator"
firmware = "V1.04"            # from probe info / the 0x13 reply
editor = "DSP Processor Editor x.y"
date = 2026-11-07
question = "Q2"
action = "Out1 PEQ band 1 frequency 1000 Hz -> 100 Hz -> 10 kHz"
values = { freq_hz = [1000, 100, 10000] }
notes = ""
```

## After a capture session

Update these together:

1. the confidence tags in `PROTOCOL.md`;
2. the defaults in `protocol/profiles/default.toml`;
3. the fixtures and the tests that replay them.
