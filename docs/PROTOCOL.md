# t.racks DSP 408 — Network Protocol Synthesis

This document cross-references the reverse-engineering work of the projects listed in
[`SOURCES.md`](SOURCES.md) and condenses it into a single, actionable reference for
this project. It is **not** a verified specification yet: every item carries a confidence
tag. The [implementation plan](PLAN.md) confirms the open points: Phase 2 (editor against
our simulator) and Phase 8 (real hardware).

## 0. Sources and how much to trust them

| Project | Device | Transport | Language | Method | Trust |
|---|---|---|---|---|---|
| [Aeternitaas/dsp-408-ui](https://github.com/Aeternitaas/dsp-408-ui) (`juli303/t-dsp-ui` is an identical fork) | **DSP 408** | TCP 9761 | Dart/Flutter | Wireshark captures of the official editor, working app | **Only source tested on a DSP 408.** Reliable for what the app ships (gain, mute, matrix, GEQ, presets, meter poll). PEQ / crossover are marked "in development" there and contain errors (see §4). |
| [FlexiFlizz/t.racks-DSP-control](https://github.com/FlexiFlizz/t.racks-DSP-control) | DSP 206 (2×6) | TCP 9761 + USB HID | Python | Wireshark captures, hardware tests on a 206 | Good for opcodes the 408 project lacks (delay, phase, compressor, limiter, gate, slopes). 408 support is "untested" in that repo. |
| [IMBArator/miniDSP-Linux](https://github.com/IMBArator/miniDSP-Linux) | DSP 4x4 Mini | USB HID | Python | Very rigorous: every claim backed by a capture, plus a Ghidra pass on the editor | Best documentation of the *protocol family*: framing, ACKs, presets, link, lock, test tone, meter tail. Values and ranges differ per model. |

All three are **GPL-3.0**. This project is **AGPL-3.0**; GPLv3 §13 / AGPLv3 §13 explicitly
allow combining the two, so code may be reused **with attribution** (keep copyright
headers, list the origin in `docs/SOURCES.md`).

Confidence tags used below:

- **408**: observed on a DSP 408 over TCP (dsp-408-ui).
- **SIB**: verified on a sibling model only (206 or 4x4 Mini); very likely the same on the 408.
- **CONFLICT**: sources disagree; the value we will use first is marked ▶.
- **UNKNOWN**: not documented anywhere; must be captured.

---

## 1. Transport

| Item | Value | Conf. |
|---|---|---|
| Transport | Plain TCP, DSP is the server | 408 |
| Port | **9761** | 408 |
| Discovery | None known; the IP is entered manually in every source | UNKNOWN |
| Concurrent TCP clients | Unknown; assume **one**. Our backend must be the only client (the official editor cannot run at the same time). | UNKNOWN |
| Keepalive | The client polls meters (`0x40`) continuously; the editor polls at ~150 ms, dsp-408-ui at 300 ms. Whether the DSP drops an idle socket is unknown. | 408 / UNKNOWN |
| Flow control | **Strict request/response, one frame in flight.** Every request gets exactly one response frame (data or ACK). dsp-408-ui and miniDSP both serialise like this; dsp-408-ui unblocks after 500 ms without an answer. | 408 + SIB |

---

## 2. Frame format

```
 10 02 | SRC | DST | LEN | PAYLOAD (LEN bytes) | 10 03 | CHK
 └STX┘                    payload[0] = opcode    └ETX┘
```

| Field | Size | Host → DSP | DSP → host |
|---|---|---|---|
| STX | 2 | `10 02` | `10 02` |
| SRC | 1 | `00` | `01` |
| DST | 1 | `01` | `00` |
| LEN | 1 | length of PAYLOAD | idem |
| PAYLOAD | LEN | opcode + arguments | opcode + data, or `01` (ACK) |
| ETX | 2 | `10 03` | `10 03` |
| CHK | 1 | `LEN ^ payload[0] ^ … ^ payload[LEN-1]` | idem |

- **Checksum**: some sources describe it as "XOR of everything between STX and ETX, seeded
  with 1". The two definitions are equivalent because `SRC ^ DST == 1`. Use the LEN+payload
  form. (408 + SIB)
- **No byte stuffing** has been observed (a `0x10` inside the payload is sent as-is).
  The parser **must** therefore frame on `LEN` and then check `10 03 CHK`; it must **not**
  search for the first `10 03` like dsp-408-ui does, because a payload can legitimately
  contain those bytes (e.g. a gain or frequency value). (SIB)
- **CONFLICT on DST**: t.racks-DSP-control claims the editor sends `DST = 02` on the 206. That
  changes the checksum, and nothing else confirms it. ▶ Use `00 01` (what works on the 408).
- Generic **ACK** from the DSP: payload `01`, i.e. `10 02 01 00 01 01 10 03 00`. (SIB; dsp-408-ui
  treats "any response" as an ACK, which is compatible.)
- TCP is a byte stream: one `recv()` can return several frames, or part of one. Buffer and resync on
  `10 02`, dropping frames with a bad checksum.

---

## 3. Channel addressing (DSP 408)

| Index | Channel | Index | Channel |
|---|---|---|---|
| `0x00` | In A | `0x04`–`0x0B` | Out 1 … Out 8 |
| `0x01` | In B | | |
| `0x02` | In C | | |
| `0x03` | In D | | |

(408) Note that the 206 uses contiguous indexes (outputs from `0x02`). The 408 does not, so do not
reuse the 206 tables.

Bitmasks:

- **Matrix input mask**: In A `0x01`, In B `0x02`, In C `0x04`, In D `0x08`. (408)
- **Output bitmasks** (limiter flags, link): Out 1 = bit 0 … Out 8 = bit 7, presumably. (UNKNOWN on 408)

---

## 4. Value encodings

| Quantity | Raw ↔ physical | Range | Conf. |
|---|---|---|---|
| Channel gain (`0x34`) | **Two segments.** raw < 80: `dB = raw/2 − 60` (0.5 dB steps); raw ≥ 80: `dB = (raw−80)/10 − 20` (0.1 dB steps). Encode: `dB < −20 → (dB+60)·2`, else `80 + (dB+20)·10`. Unity gain = 280. | raw 0–400 = −60 … +12 dB | 408 (encode) + SIB (decode) |
| PEQ / GEQ gain | `dB = (raw − 120)/10` | raw 0–240 = ±12 dB | 408 |
| Frequency (PEQ, HPF, LPF) | `Hz = 19.70 · (20160/19.70)^(raw/N)` | **N = 300**. The 4x4 Mini and the 206 agree, and the 408 config dump only makes sense with N = 300: evenly spaced default PEQ bands (raw 31, 63 … 285) and crossover points of a coherent 3-way system (25/80 Hz, 80/161 Hz, 370 Hz/4.8 kHz). dsp-408-ui uses N = 1000, which is wrong. | 408 (dump) + SIB |
| PEQ Q | `Q = 0.4 · 320^(raw/M)` | **CONFLICT** on M: ▶ **M = 100** (the 4x4 Mini formula and the 206 formula `10^((raw−16)/40)` are the same curve). dsp-408-ui uses M = 255. | CONFLICT |
| Threshold (gate / comp / limiter) | `dB = raw/2 − 90` (i.e. raw = 2·dB + 180) | gate −90…0, comp/lim −90…+20 | SIB (both siblings agree) |
| Attack / release / hold | `ms = raw + 1` | attack 1–999, release 1/10–3000, hold 10–999 | SIB |
| Knee | `dB = raw` | 0–12 | SIB |
| Delay (`0x38`) | **CONFLICT**: 4x4 Mini `ms = raw/48` (48 kHz, max 680 ms); 206 `ms = raw/96`. ▶ **96 kHz** (206, same TCP generation); a profile setting. | uint16, max 680 ms | CONFLICT |
| Compressor ratio | enum 0–15: 1:1, 1:1.1, 1:1.3, 1:1.5, 1:1.7, 1:2, 1:2.5, 1:3, 1:3.5, 1:4, 1:5, 1:6, 1:8, 1:10, 1:20, Limit | | SIB |
| Names | ASCII. Channel names are 8 bytes, zero-padded. Preset names are 14 bytes, space-padded. **Never send more than 14 characters** (that crashes the 4x4 Mini firmware). | | SIB |

**PEQ filter types (CONFLICT):** the 206 and dsp-408-ui list 9 types (0 Peak, 1 Low Shelf, 2 High Shelf,
3 LP −6, 4 LP −12, 5 HP −6, 6 HP −12, 7 Allpass 1, 8 Allpass 2); the 4x4 Mini has 7. ▶ 9-type list,
to verify.

**Crossover slopes (`0x31`/`0x32` last byte):** slope `0x00` means *bypass*. The 206 table has 21
entries:

| raw | slope | raw | slope | raw | slope |
|---|---|---|---|---|---|
| 00 | bypass | 07 | BL-18 | 0E | BL-36 |
| 01 | BW-6 | 08 | BW-24 | 0F | LR-36 |
| 02 | BL-6 | 09 | BL-24 | 10 | BW-42 |
| 03 | BW-12 | 0A | LR-24 | 11 | BL-42 |
| 04 | BL-12 | 0B | BW-30 | 12 | BW-48 |
| 05 | LR-12 | 0C | BL-30 | 13 | BL-48 |
| 06 | BW-18 | 0D | BW-36 | 14 | LR-48 |

On the 4x4 Mini, entries 00–0A match. dsp-408-ui sends `enable ? 1 : 0` for the HPF, which is wrong:
it selects BW-6. (SIB, 408 table to verify.) The DSP forgets the slope when bypassed, so the
backend must remember the last active slope to restore it.

---

## 5. Opcodes

Request payloads are shown without the framing. `ch` is a channel index (§3).

### 5.1 Session and information

| Op | Request | Response | Purpose | Conf. |
|---|---|---|---|---|
| `10` | `10` | `10 xx` (4x4 Mini: `10 1e`) | Handshake, always first | 408 |
| `13` | `13` | `13` + ASCII model/firmware string | Device identification (lets us check that it is a 408) | 408 |
| `2c` | `2c` | 8 bytes. 4x4 Mini: byte 6 = **lock flag**. dsp-408-ui reads byte 7 as "preset count". | Device info / lock status | CONFLICT |
| `22` | `22` | `22 ff ff` + zeros | Active preset header (part of the editor's init sequence) | 408 (sent) |
| `14` | `14` | `14 slot` | Active preset index (0 = F00, 1 = U01 …) | 408 (sent) + SIB |
| `12` | `12` | ACK | "Activate / config load done", sent after a config read | 408 + SIB |
| `40` | `40` | meters (§6) | Meter poll, also acts as keepalive | 408 |
| `2d` | `2d 00 p0 p1 p2 p3` (ASCII digits) | `2d 00 01` OK, `2d 00 00` wrong | Unlock a PIN-locked DSP | SIB |
| `2f` | `2f p0 p1 p2 p3` | ACK, then the device **locks** | Set the device PIN. **Out of scope: dangerous** | SIB |

**Init sequence** (editor and dsp-408-ui):
`10` → `13` → `2c` → `22` → `14` → `29`×20 → `27`×29 → `12` → `40` loop.

### 5.2 Presets

| Op | Request | Response | Notes | Conf. |
|---|---|---|---|---|
| `29` | `29 i` (i = 0…19 → U01…U20) | `29 i` + 14-char name | Read a preset name. The 408 has **20 user presets** (4x4 Mini: 30). | 408 |
| `20` | `20 slot` (0 = F00, 1…20 = U01…U20) | ACK, **slow** (allow 2 s) | Recall a preset. Afterwards, re-read the config (`27`×29) and send `12`. | 408 |
| `26` | `26` + 14 bytes, space-padded | ACK | Set the name for the next store | 408 |
| `21` | `21 slot` | ACK after ~2 s (flash write) | Store the current state. **Never use slot 0 (F00).** | 408 |
| `27` | `27 n` (n = 0x00…0x1C) | `24 n` + 50 bytes (the last page has 48) | Read the live config page by page (§7) | 408 |
| `24`/`28` | `24 slot` then `28 n` | `28 n` + data | Read a stored preset without recalling it | SIB |

### 5.3 Parameters (write, ACK expected)

| Op | Payload | Applies to | Conf. |
|---|---|---|---|
| `34` | `34 ch lo hi`: gain (§4) | all | 408 |
| `35` | `35 ch 00/01`: mute off/on | all | 408 |
| `36` | `36 ch 00/01`: phase normal/inverted | all | SIB |
| `3a` | `3a out mask`: matrix, full input mask each time | outputs | 408 |
| `48` | `48 ch band val 00`: GEQ band (31 bands, ISO 1/3 octave 20 Hz–20 kHz; `val` = PEQ gain encoding) | inputs | 408 |
| `33` | `33 ch band gain_lo gain_hi f_lo f_hi q type bypass`: PEQ band. Inputs have 8 bands, outputs 9 (DSP 408). | all | 408 (layout) / CONFLICT (encodings) |
| `3c` | `3c ch 00/01`: bypass all PEQ bands of a channel | all? | SIB |
| `32` | `32 ch f_lo f_hi slope`: high-pass | outputs (+inputs?) | 408 (layout) / SIB (values) |
| `31` | `31 ch f_lo f_hi slope`: low-pass | outputs (+inputs?) | idem |
| `38` | `38 ch lo hi`: delay (§4) | outputs (inputs?) | SIB / CONFLICT |
| `30` | Compressor. **CONFLICT on layout**: 206 = `30 ch ratio(2) atk(2) rel(2) knee(2) thr(2)`; 4x4 Mini = `30 ch ratio(1) knee(1) atk(2) rel(2) thr(2)`. ▶ 206 layout: the 408 config blob stores exactly these five LE16 fields (§7). | outputs | CONFLICT |
| `3f` | `3f ch atk(2) rel(2) ?(2) thr(2)`: limiter (206 only; the 4x4 Mini has no separate limiter) | outputs | SIB (206) |
| `3e` | `3e ch atk(2) rel(2) hold(2) thr(2)`: noise gate | inputs | SIB |
| `3d` | `3d ch` + 8 ASCII bytes: channel name | all | SIB |
| `3b` / `2a` | Channel link: `2a master slave` per pair, then `3b ch flags` per channel, then `12`, then a full config re-read | all | SIB |
| `39` | `39 mode freq_idx`: test generator (0 off, 1 pink, 2 white, 3 sine). **Out of scope: speaker safety** | global | SIB |
| `15` | `15 unit`: delay display unit (cosmetic) | global | SIB |

Matrix per-input level: the 408 config stores four LE16 values of 280 (0 dB) for each output,
one per input, which suggests that each matrix crosspoint has a gain. The opcode is **UNKNOWN**
(dsp-408-ui lists it as "in development").

---

## 6. Meters (`0x40` response)

DSP 408 response: `LEN = 0x27` (39), i.e. payload = `40` + **12 × 3 bytes** (In A–D, then Out 1–8) +
**2 tail bytes**. (408)

**CONFLICT on the meaning of the 3 bytes per channel:**

| Hypothesis | Source | Decoding |
|---|---|---|
| ▶ A: float16 + peak | dsp-408-ui (408), t.racks-DSP-control (206) | bytes 0–1 = IEEE-754 half float, little-endian, linear level; byte 2 = "peak" (0–255). `ff ff` = NaN, sent while the DSP recomputes a PEQ: treat it as "no data". dsp-408-ui observed an idle floor around 0.5 and a maximum around 2.0. |
| B: 24-bit linear | miniDSP-Linux (4x4 Mini, confirmed with Ghidra) | `level24 = b2 + (b0<<8) + (b1<<16)`; editor dB = `20·log10(level24/2^19) + 28`; clip at level24 ≥ 74058. |

Bytes 0–1 are the same in both hypotheses, so a short capture with a known signal settles it. The
decoder must be pluggable, with calibration constants kept in configuration.

**Tail bytes (2 on the 408, 3 on the 4x4 Mini).** On the Mini, the tail holds:

- byte 25: per-output **limiter/compressor active** bitmask;
- byte 26: state flag;
- byte 27: "some input clips" flag.

On the 408, the most likely mapping is one byte of limiter-active mask (Out 1–8) and one byte of
clip or comp flags, but this is **UNKNOWN**. The UI needs it for the "limit" and "comp" LEDs.

Clip LED fallback: derive it from the level (threshold calibrated per hypothesis), as the official
editor does.

---

## 7. Configuration blob (`0x27` pages)

29 pages: 28 × 50 bytes + 1 × 48 bytes = **1448 bytes**. This is a live dump of the active preset.

The layout below is **byte-exact on a real DSP 408 dump** (preset "Forest" from dsp-408-ui,
stored as `tests/fixtures/config/forest_408.bin`). Every record has a fixed size, the values make
sense (a 3-way system: sub 25–80 Hz BW-24, low 80–161 Hz, mid 370 Hz–4.8 kHz LR-24, GEQ cuts
around 2 kHz), and the field layouts match the 206 command layouts. It is implemented in
`protocol/config_map.py`.

| Offset | Size | Content | Conf. |
|---|---|---|---|
| 0 | 2 | Marker: `ff ff` = modified user preset, `ff 00` = factory/empty | 408 |
| 2 | 14 | Active preset name, space-padded | 408 |
| 16 | 4 × 140 | Input records | 408 |
| 576 | 8 × 104 | Output records | 408 |
| 1408 | 40 | Trailer: unknown, preserved as-is | UNKNOWN |

**Input record (140 bytes):**

| Off | Field | Conf. |
|---|---|---|
| 0 | name (8 bytes, zero-padded) | 408 |
| 8 | gate: attack, release, hold, threshold (4 × LE16; default `0, 99, 99, 0`) | 408 (order SIB) |
| 16 | GEQ: 31 × LE16 (EQ gain encoding) | 408 |
| 78 | PEQ: 8 bands × 6 bytes `[gain LE16][freq LE16][Q u8][type u8]` | 408 |
| 126 | HPF freq LE16, LPF freq LE16, HPF slope u8, LPF slope u8 | 408 |
| 132 | gain LE16 | 408 |
| 134 | delay LE16 | HYP (zero in every dump) |
| 136 | mute u8, phase u8 | HYP (zero in every dump) |
| 138 | link flags LE16 (standalone = own bit: 1, 2, 4, 8) | 408 |

**Output record (104 bytes):**

| Off | Field | Conf. |
|---|---|---|
| 0 | name (8 bytes) | 408 |
| 8 | matrix input mask LE16 | 408 |
| 10 | 4 × crosspoint gain LE16 (280 = 0 dB) | 408 (meaning SIB) |
| 18 | HPF freq, LPF freq, HPF slope, LPF slope (as inputs) | 408 |
| 24 | PEQ: 9 bands × 6 bytes | 408 |
| 78 | compressor: ratio, attack, release, knee, threshold (5 × LE16; default `0, 49, 499, 0, 220`) | 408 (= 206 command layout) |
| 88 | limiter: attack, release, reserved, threshold (4 × LE16) | 408 (= 206 command layout) |
| 96 | gain LE16 | 408 |
| 98 | delay LE16 | HYP |
| 100 | mute u8, phase u8 | HYP |
| 102 | link flags LE16 (standalone: 1, 2, 4 … 128) | 408 |

Not located yet: PEQ band bypass and channel PEQ bypass (not stored in the band data, as on the
4x4 Mini), anything in the trailer. The hypothetical fields (HYP) are the only zero bytes left in
the records, so they are the natural candidates; one diff capture each settles them (Q11).

dsp-408-ui finds records by searching for the strings `"InA"` / `"Out1"`. That breaks as soon as
a user renames a channel. We use the fixed offsets above.

---

## 8. Behaviour notes

- **Fader bursts:** the editor sends roughly one gain frame per 150 ms of fader movement, each
  ACKed, and polls only when the fader is idle. The backend must coalesce bursts (see [SPEC](SPEC.md), "Command pipeline").
- **Preset recall** takes up to ~2 s before the ACK. After a recall or a link change, re-read the
  whole config.
- After `12`, give the DSP a short grace period before polling again (4x4 Mini: back-to-back
  polls can time out).
- The front panel of the DSP can change values without notifying the client. Only a periodic
  config re-read detects that.
- A `0x40` answer with `ff ff` levels happens during DSP recomputation; it is not an error.

---

## 9. Open questions

Until they are answered, every uncertain value is a field of the `ProtocolProfile` (SPEC §4.6),
with the ▶ choice as default. The *Side* column says what is needed to answer each question:
**req** = the editor's requests, which can be captured against our simulator without a DSP
(PLAN, Phase 2); **resp** = the device's answers, which need a real DSP 408 (PLAN, Phase 8).

| # | Question | How | Side |
|---|---|---|---|
| Q1 | Meter encoding (float16 vs 24-bit) and meaning of the 2 tail bytes (limit/comp/clip) | Sine at a known level; trigger the limiter on one output; clip one input | resp |
| Q2 | Frequency step count (300 vs 1000) and Q scale (100 vs 255) | Set PEQ band to 1 kHz / Q 1.0 in the editor and capture | req |
| Q3 | Delay unit (/48 vs /96) and maximum | Sweep delay in the editor | req |
| Q4 | Compressor `0x30` and limiter `0x3f` layouts on the 408 | One capture per parameter | req |
| Q5 | Slope table on the 408 (number of entries) and bypass | Sweep slopes | req |
| Q6 | Gate `0x3e`, phase `0x36`, names `0x3d`, link `0x3b`/`0x2a` on the 408 | One capture each | req |
| Q7 | Matrix crosspoint gain opcode | Capture | req |
| Q8 | `0x2c` and `0x10` responses on the 408; DSP PIN lock behaviour | Capture at connect | resp |
| Q9 | Write ACK format; any unsolicited frames | Observe | resp |
| Q10 | Second TCP client: refused, accepted, or kicks the first one? Idle timeout? | Two sockets | resp |
| Q11 | Remaining config-blob fields (HYP offsets for delay/mute/phase, band bypass, trailer); the record layout itself is confirmed (§7) | Diff dumps before/after each single change | resp |
| Q12 | Input HPF/LPF and input delay availability | Editor UI + capture | req |

Capture method: Wireshark on the PC that runs the official editor (`tcp.port == 9761`), or the
built-in `proxy` sub-command of this project (see PLAN, Phase 1).
