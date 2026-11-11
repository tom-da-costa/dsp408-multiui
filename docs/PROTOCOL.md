# t.racks DSP 408 — Network Protocol Synthesis

This document cross-references the reverse-engineering work of the projects listed in
the [README](../README.md#sources-and-credits) and condenses it into a single, actionable reference for
this project. Every item carries a confidence tag. A hardware verification session verified most
of it on a real DSP 408 (firmware V0104P, 2026-11-08): items tagged **HW** below. What is still
open is listed in §9. The DSP 206 and 204, which the simulator can also play, are in §10.

## 0. Sources and how much to trust them

| Project | Device | Transport | Language | Method | Trust |
|---|---|---|---|---|---|
| [Aeternitaas/dsp-408-ui](https://github.com/Aeternitaas/dsp-408-ui) (`juli303/t-dsp-ui` is an identical fork) | **DSP 408** | TCP 9761 | Dart/Flutter | Wireshark captures of the official editor, working app | **Only source tested on a DSP 408.** Reliable for what the app ships (gain, mute, matrix, GEQ, presets, meter poll). PEQ / crossover are marked "in development" there and contain errors (see §4). |
| [FlexiFlizz/t.racks-DSP-control](https://github.com/FlexiFlizz/t.racks-DSP-control) | DSP 206 (2×6) | TCP 9761 + USB HID | Python | Wireshark captures, hardware tests on a 206 | Good for opcodes the 408 project lacks (delay, phase, compressor, limiter, gate, slopes). 408 support is "untested" in that repo. Its Wireshark captures (`*.pcapng`) of the official editor and a real 206 are the source of §10; its own 206 simulator invents its config data and is not used. |
| [Givou/BetterDSPControl](https://git.thiemoo.at/Givou/BetterDSPControl) (MIT) | **DSP 204**, DSP 408 | TCP 9761 + USB HID | Python | Control app, tested on a real 204 (V0104P, over USB); the 408 "briefly tried" | Source for the 204 (§10). Its protocol notes agree with our 408 verification (frame, checksum, layout, meters, links, encodings). |
| [IMBArator/miniDSP-Linux](https://github.com/IMBArator/miniDSP-Linux) | DSP 4x4 Mini | USB HID | Python | Very rigorous: every claim backed by a capture, plus a Ghidra pass on the editor | Best documentation of the *protocol family*: framing, ACKs, presets, link, lock, test tone, meter tail. Values and ranges differ per model. |

The first three are **GPL-3.0**, BetterDSPControl is **MIT**. This project is **AGPL-3.0**;
GPLv3 §13 / AGPLv3 §13 allow combining GPL code, and MIT code can be included with its notice, so
code may be reused **with attribution** (keep copyright
headers, list the origin in the README's attribution table).

Confidence tags used below:

- **HW**: verified by this project on a real DSP 408 (firmware V0104P): the device ACKed the
  request and a config read showed exactly the expected bytes, or the value was compared with
  the official editor. The recorded writes are in `tests/fixtures/hardware/write_diffs.json`.
- **408**: observed on a DSP 408 over TCP (dsp-408-ui).
- **206**: observed on a real DSP 206 (firmware V0104P) in the Wireshark captures of
  t.racks-DSP-control, decoded by this project (§10).
- **204**: documented by BetterDSPControl from a real DSP 204 (firmware V0104P) (§10).
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
| Concurrent TCP clients | **One.** A second client's TCP connection is neither accepted nor refused: it waits until the first client disconnects, then completes at once (tested 2026-11-11: a connect pending for 6 s completed the instant the first client closed). The first client is not disturbed. So the official editor and this app cannot run at the same time: whichever connects second waits. | HW |
| Keepalive | The client polls meters (`0x40`) continuously; the editor polls at ~150 ms, dsp-408-ui at 300 ms. The DSP keeps an idle socket open (it still holds the slot), but after **5–7 s without any request** it stops answering reads (`14`, `40` … all tried), until a handshake `10`, which is enough to bring them back (no full init needed). Writes are still acknowledged and applied meanwhile. | HW |
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
| SRC | 1 | `00` | device address: `01` (408), `02` (206) |
| DST | 1 | device address | `00` |
| LEN | 1 | length of PAYLOAD | idem |
| PAYLOAD | LEN | opcode + arguments | opcode + data, or `01` (ACK) |
| ETX | 2 | `10 03` | `10 03` |
| CHK | 1 | `1 ^ SRC ^ DST ^ LEN ^ payload[0] ^ … ^ payload[LEN-1]` | idem |

- **Checksum**: the XOR of everything between STX and ETX, seeded with 1. On the 408
  (`SRC ^ DST == 1`) it reduces to `LEN ^ payload`, the form dsp-408-ui uses; on the 206
  (address `02`) only the full form is right: it checks on all 8303 captured frames. (408 + 206)
- **No byte stuffing** has been observed (a `0x10` inside the payload is sent as-is).
  The parser **must** therefore frame on `LEN` and then check `10 03 CHK`; it must **not**
  search for the first `10 03` like dsp-408-ui does, because a payload can legitimately
  contain those bytes (e.g. a gain or frequency value). (SIB)
- **Device address = the "ID number" set on the DSP's front panel** (1–250, `01` from the
  factory; HW, 2026-11-11). With the ID set to 6, a 408 answers frames sent to `06` only, from
  `06`; frames to `01`, `02`, any other ID, `00` or `ff` (no broadcast) get no answer. It lets
  several DSPs share a serial bus; over TCP each one has its own IP anyway. The editor addressed
  the captured 206 as `02` — most likely that unit's ID; it also answered frames sent to `01`,
  replying from `01` (206). The profile's `host_dst` is only the first address tried: the app
  then tries `01`, `02`, and searches every ID (handshakes spaced 40 ms apart, the first
  answer wins), or uses `--device-id`; the ID found is tried first at the next connection.
- **One frame at a time, also on the wire (HW).** Two frames in one TCP write (even two
  handshakes for different IDs), or frames less than ~15 ms apart, are missed, and after two
  frames in one write the connection stops answering altogether (a new connection is fine).
  Hence one request in flight, and the 40 ms spacing of the ID search.
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

(408) The outputs start at `0x04`, right after the 4 inputs. On the 206 they also follow the
inputs, so they start at `0x02` (§10): output `n` is always `input_count + n`.

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
| Threshold (gate / comp / limiter), in **dBu** | `dBu = raw/2 − 90` (i.e. raw = 2·dBu + 180) | gate −90…0, comp/lim −90…+20 dBu | SIB (both siblings agree); unit dBu confirmed by the owner |
| Attack / release / hold | `ms = raw + 1` | attack 1–999, release 1/10–3000, hold 10–999 | SIB |
| Knee | `dB = raw` | 0–12 | SIB |
| Delay (`0x38`) | `ms = raw/96` (samples at 96 kHz): the editor shows raw 426 as 4.44 ms. The 4x4 Mini uses 48 kHz. | uint16, max 680 ms (not tested) | HW |
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
| `10` | `10` | `10 13` | Handshake, always first | HW |
| `13` | `13` | `13` + ASCII `DSP408 V0104P` | Device identification (lets us check that it is a 408) | HW |
| `2c` | `2c` | `2c 00 27 0f 00 00 00` | Device info / lock status. 4x4 Mini: byte 6 = **lock flag**; the 408 meaning is unknown | HW (bytes) |
| `22` | `22` | `22 ff ff` + zeros | Active preset header (part of the editor's init sequence) | 408 (sent) |
| `14` | `14` | `14 slot` | Active preset index (0 = F00, 1 = U01 …) | HW |
| `12` | `12` | ACK | "Activate / config load done", sent after a config read | 408 + SIB |
| `40` | `40` | meters (§6) | Meter poll, also acts as keepalive | HW |
| `2d` | `2d 00 p0 p1 p2 p3` (ASCII digits) | `2d 00 01` OK, `2d 00 00` wrong | Unlock a PIN-locked DSP | SIB |
| `2f` | `2f p0 p1 p2 p3` | ACK, then the device **locks** | Set the device PIN. **Out of scope: dangerous** | SIB |

**Init sequence** (editor and dsp-408-ui):
`10` → `13` → `2c` → `22` → `14` → `29`×20 → `27`×29 → `12` → `40` loop.

**The init sequence is required (HW).** On a fresh connection the 408 does not answer `27`
(config pages) at all, and `40` is either not answered or returns stale, frozen levels. After the
sequence above (up to the preset names) both work. Which request of the sequence unlocks them is
not known; the simulator uses the handshake. Parameter writes work without it.

### 5.2 Presets

| Op | Request | Response | Notes | Conf. |
|---|---|---|---|---|
| `29` | `29 i` (i = 0…19 → U01…U20) | `29 i` + 14-char name | Read a preset name. The 408 has **20 user presets** (4x4 Mini: 30). Names written by the official editor are Latin-1 (`e9` = é). | HW |
| `20` | `20 slot` (0 = F00, 1…20 = U01…U20) | ACK after **~3.2 s** | Recall a preset. Afterwards, re-read the config (`27`×29) and send `12`. | HW |
| `26` | `26` + 14 bytes, space-padded | `01 01` + the 14 name bytes (an ACK that echoes the name) | Set the name for the next store | HW |
| `21` | `21 slot` | ACK after **~7.4 s** (flash write) | Store the current state. **Never use slot 0 (F00).** | HW |
| `27` | `27 n` (n = 0x00…0x1C) | `24 n` + 50 bytes (the last page has 48) | Read the live config page by page (§7); needs the init sequence | HW |
| `24`/`28` | `24 slot` then `28 n` | `28 n` + data | Read a stored preset without recalling it | SIB |

### 5.3 Parameters (write, ACK expected)

Every write below was sent to the 408 and answered with the ACK `01`; the config read that
followed shows the field changing at the offset given in §7 (HW). On a **linked** channel, the
408 applies the write to every member of the link group, whichever member it is sent to, except
the name (`3d`) and the matrix (`3a`).

| Op | Payload | Applies to | Conf. |
|---|---|---|---|
| `34` | `34 ch lo hi`: gain (§4); the two-segment encoding is exact from +12 to −50 dB | all | HW |
| `35` | `35 ch 00/01`: mute off/on | all | HW |
| `36` | `36 ch 00/01`: phase normal/inverted | all | HW |
| `3a` | `3a out mask`: matrix, full input mask each time | outputs | HW |
| `48` | `48 ch band val 00`: GEQ band (31 bands, ISO 1/3 octave 20 Hz–20 kHz; `val` = PEQ gain encoding) | inputs | HW |
| `33` | `33 ch band gain_lo gain_hi f_lo f_hi q type bypass`: PEQ band. Inputs have 8 bands, outputs 9. The bypass flag goes to a trailer mask (§7). | all | HW |
| `3c` | `3c ch 00/01`: bypass the whole PEQ of a channel | all | HW |
| `32` | `32 ch f_lo f_hi slope`: high-pass (slope 0 = bypass) | **all, inputs included** | HW |
| `31` | `31 ch f_lo f_hi slope`: low-pass | all | HW |
| `38` | `38 ch lo hi`: delay in samples at **96 kHz** (the editor shows 426 as 4.44 ms) | **all, inputs included** | HW |
| `30` | `30 ch ratio(2) atk(2) rel(2) knee(2) thr(2)`: compressor (206 layout) | outputs | HW |
| `3f` | `3f ch atk(2) rel(2) ?(2) thr(2)`: limiter | outputs | HW |
| `3e` | `3e ch atk(2) rel(2) hold(2) thr(2)`: noise gate | inputs | HW |
| `3d` | `3d ch` + 8 ASCII bytes (zero-padded): channel name | all | HW |
| `2a` | `2a master slave`: **copies every setting of the master onto the slave** (gain, delay, phase, mute, crossover, PEQ and its bypass, dynamics), **except the name and the routing**. Sent once per slave before linking. | all (same kind) | HW |
| `3b` | `3b ch mask` (1 byte): writes the channel's link mask as is (+138 inputs / +102 outputs). Master = bits of every member (bit n = input or output n), other members 0, unlinked = own bit. | all | HW |
| `39` | `39 mode freq_idx`: test generator (0 off, 1 pink, 2 white, 3 sine). **Out of scope: speaker safety** | global | SIB |
| `15` | `15 unit`: delay display unit (cosmetic) | global | SIB |

Matrix per-input level: the 408 config stores four LE16 values of 280 (0 dB) for each output,
one per input, which suggests that each matrix crosspoint has a gain. The opcode is **UNKNOWN**
(dsp-408-ui lists it as "in development").

---

## 6. Meters (`0x40` response)

DSP 408 response: `LEN = 0x27` (39), i.e. payload = `40` + **12 × 3 bytes** (In A–D, then Out 1–8) +
**2 tail bytes**. (HW)

**Levels (HW).** Each triplet `b0 b1 b2` is the top three bytes of a little-endian IEEE-754
**float32**: `value = float32(00 b2 b0 b1)` (b1 = sign + exponent, b0 and b2 = mantissa). The value
is **linear**: `dB = 20·log10(value / reference)`.

**Reference: dBu (HW, observed ±1 dB; unit confirmed by the owner).** The value is relative to
full scale, and **full scale = +20 dBu**. So `dBu = 20·log10(value) + 20`, i.e. `reference = 0.1`.
The compressor, limiter and gate thresholds are in **dBu** too, so levels and thresholds compare
directly. Observed
on 2026-11-09, read-only, with music on the live preset: Out 1/5 (compressor ratio "Limit",
threshold +1 dB) had the compressor-active bit set in 12 of 374 frames, at meter readings of
−5.9…+1.7 dB with this reference (median +1.0); never above +2.3. Out 2/6 (threshold −7 dB) peaked
at −5.8 and never set the bit. The earlier assumption "1.0 = 0 dBFS" put the meter 20 dB below the
thresholds. A steady-tone sweep of a threshold on a test preset would pin the +20 dBu more precisely.

How it was established: Out 4 was made transparent (filters, PEQ and dynamics off), fed from In A
only, and its gain was stepped from +12 to −50 dB while music played. The difference between the
Out 4 and In A meters moved by exactly 128 units of `b1:b0` per 6.02 dB (one octave), the
signature of a float's exponent; the mapping held over the whole 62 dB range.

- Levels are not clamped: with +24 dB of gain, Out 4 read 8.47 (+38.6 dBu).
  There is no clip flag: CLIP is derived from the level, from +12 dBu (the owner's choice, 8 dB
  below full scale).
- An unconnected but unmuted input reads about 5·10⁻⁶ (−86 dBu, the ADC noise floor); a muted
  channel reads about 10⁻³⁵ (zero).
- An input meter is measured after the input gain and **before** the input mute.
- Before the init sequence (§5.1) the 408 returns frozen values (or nothing).
- dsp-408-ui reads `b0 b1` as a float16. That is monotonic but wrong: it shows silence around
  −8 dB and compresses the scale by a factor of 8.

**Tail bytes (HW).** Byte 0 = per-output **compressor-active** mask (bit n = Out n+1), byte 1 =
per-output **limiter-active** mask. Shown by pulling Out 4's compressor threshold to −60 dB
(byte 0 gained `88`: Out 4 and its linked Out 8), then its limiter threshold (byte 1 gained `88`).

The tests use real frames from `tests/fixtures/meters/dsp408_u08.txt`.

---

## 7. Configuration blob (`0x27` pages)

29 pages: 28 × 50 bytes + 1 × 48 bytes = **1448 bytes**. This is a live dump of the active preset.

The record layout was first derived from a real dump (preset "Forest" from dsp-408-ui,
`tests/fixtures/config/forest_408.bin`), then **verified field by field on hardware** (HW): every
write of §5.3 was followed by a full read and a byte diff. The simulator reproduces all 40
recorded writes byte for byte (`tests/hardware/test_write_diffs.py`). A complete dump of the
owner's preset is in `tests/fixtures/config/dsp408_u08.bin`. Implemented in
`protocol/config_map.py`.

| Offset | Size | Content | Conf. |
|---|---|---|---|
| 0 | 2 | Marker: `ff ff` = modified user preset, `ff 00` = factory/empty | 408 |
| 2 | 14 | Active preset name, space-padded, Latin-1 | HW |
| 16 | 4 × 140 | Input records | HW |
| 576 | 8 × 104 | Output records | HW |
| 1408 | 40 | Trailer: masks (below) | HW (partly) |

**Input record (140 bytes):**

| Off | Field | Conf. |
|---|---|---|
| 0 | name (8 bytes, zero-padded) | HW |
| 8 | gate: attack, release, hold, threshold (4 × LE16; default `0, 99, 99, 0`) | HW |
| 16 | GEQ: 31 × LE16 (EQ gain encoding) | HW |
| 78 | PEQ: 8 bands × 6 bytes `[gain LE16][freq LE16][Q u8][type u8]` | HW |
| 126 | HPF freq LE16, LPF freq LE16, HPF slope u8, LPF slope u8 | HW |
| 132 | gain LE16 | HW |
| 134 | phase u8 (1 = inverted) | HW |
| 135 | unknown u8 (zero in every dump) | UNKNOWN |
| 136 | delay LE16, samples at 96 kHz | HW |
| 138 | link mask LE16 | HW |

**Output record (104 bytes):**

| Off | Field | Conf. |
|---|---|---|
| 0 | name (8 bytes) | HW |
| 8 | matrix input mask LE16 | HW |
| 10 | 4 × crosspoint gain LE16 (280 = 0 dB) | 408 (meaning SIB) |
| 18 | HPF freq, LPF freq, HPF slope, LPF slope (as inputs) | HW |
| 24 | PEQ: 9 bands × 6 bytes | HW |
| 78 | compressor: ratio, attack, release, knee, threshold (5 × LE16) | HW |
| 88 | limiter: attack, release, reserved, threshold (4 × LE16) | HW |
| 96 | gain LE16 | HW |
| 98 | phase u8 | HW |
| 99 | unknown u8 (zero in every dump) | UNKNOWN |
| 100 | delay LE16, samples at 96 kHz | HW |
| 102 | link mask LE16 | HW |

**Trailer (offsets from 1408):**

| Off | Field | Conf. |
|---|---|---|
| 0 | input mute mask (bit n = input n) | HW |
| 2 | output mute mask (bit n = Out n+1) | HW |
| 4 | PEQ band bypass: 12 × LE16, by protocol channel index (In A = 0 … Out 8 = 11); bit n = band n+1 | HW |
| 34 | input PEQ bypass mask | HW |
| 36 | output PEQ bypass mask | HW |
| 1, 3, 28–33, 35, 37–39 | unknown (zero everywhere; preserved) | UNKNOWN |

**Link masks (HW).** The first channel of a linked group holds the mask of all members (itself
included); the other members hold 0. On the owner's DSP: In A = `03` (A+B), Out 1 = `11`
(Out 1+5), Out 2 = `22`, Out 3 = `44`, Out 4 = `88`. An unlinked channel holds its own bit (In C =
`04`) or 0.

dsp-408-ui finds records by searching for the strings `"InA"` / `"Out1"`. That breaks as soon as
a user renames a channel. We use the fixed offsets above.

### 7.1 Preset files (`.prs`) of the official editor

Decoded from a file the official editor exported from the owner's DSP 408 (V0104P, 2026-11-11,
`tests/fixtures/presets/dsp408_editor.prs`, 1452 bytes). Implemented in
`protocol/preset_file.py`.

| Offset | Size | Content | Conf. |
|---|---|---|---|
| 0 | 16 | Header `***DSP408V010***`: `***`, the identity without its space cut to 10 characters, `***` | HW (one file; the rule for other firmware strings is a guess) |
| 16 | 1420 | The config blob of §7 from its byte 2 to byte 1435: preset name, the 12 records, the trailer's first 28 bytes (mute masks, PEQ band bypass masks) | HW (one file) |
| 1436 | 2 | `0d 0a` (CR LF) | HW (one file) |

Every byte of the records decodes to a coherent setup (the same 4-way system as
`dsp408_u08.bin`, with its own names, EQ, delays and links). The file leaves out the blob's marker
and its last 12 bytes: the whole-PEQ bypass masks (trailer 34 and 36) and the unknown trailer bytes.
So a channel's whole-PEQ bypass is not kept in a `.prs` file; on import it is set to off.
Whether the editor reads the final CR LF, and whether its 206 / 204 files follow the same rule
(`16 + blob[2 : trailer + 4 + 2 × channels] + CR LF`: 930 + 2 bytes on a 206), is **UNKNOWN**.

**Loading a file.** No known request writes a whole config (the editor's own upload is not
captured), so the app loads a file with the writes of §5.3, all hardware-verified: it reads the
live config, mutes every output, unlinks the link groups (`3b` own bit, `12`), writes every
parameter that differs, links again as the file says (`2a` + `3b` + `12`), unmutes the outputs
the file does not mute, sends `12`, then reads the config again and compares it with the file.
The matrix crosspoint gains cannot be written (Q7): they are kept and reported when they differ.
Channel names with non-ASCII characters are written in plain ASCII (`é` → `e`). The preset name
comes with a store (`26` + `21`).

**Verified on the owner's DSP 408 (HW, 2026-11-11, on U04, a copy of U01).** The live config
exported as `.prs` is byte for byte the file the editor exported from U01, except the preset
name; its 12 bytes left out of the file were the marker `ff ff` and zeros. Loading a different
preset (U08 as a `.prs`, In C + D unlinked instead of linked, a name `Médi`) took 81 writes and
about 12 s (outputs muted meanwhile); the config read afterwards matched the file in every field
but the transliterated name. Stored to U04 and recalled, it came back identical. Loading the
original file back (82 writes) and storing it restored U04 byte for byte.

---

## 8. Behaviour notes

- **Fader bursts:** the editor sends roughly one gain frame per 150 ms of fader movement, each
  ACKed, and polls only when the fader is idle. The backend must coalesce bursts (see [ARCHITECTURE.md §4](ARCHITECTURE.md), "Command pipeline").
- **Preset recall** takes ~3.2 s and **store** ~7.4 s before the ACK (HW). After a recall or a
  link change, re-read the whole config.
- **Linking (HW, 2026-11-10, on U04):** the editor's sequence works on the 408: `2a master slave`
  for each new member, then `3b ch mask` for each channel whose mask changes, then `12`. `2a`
  alone already copies the settings; `3b` alone only changes the mask; `12` changes nothing in
  the config. Unlinking is `3b ch own-bit` for each member, then `12`; the members keep their
  (copied) settings. Recorded in `tests/fixtures/hardware/link_diffs.json` (32 steps).
- **Linked channels:** a write to any member of a link group changes every member (HW), except
  names and matrix. The backend copies the change into its state for every member.
- After `12`, give the DSP a short grace period before polling again (4x4 Mini: back-to-back
  polls can time out).
- The front panel of the DSP can change values without notifying the client. Only a periodic
  config re-read detects that.
- No unsolicited frame was seen during the hardware session (HW).

---

## 9. Open questions

Until they are answered, every uncertain value is a field of the `ProtocolProfile` ([ARCHITECTURE.md §6](ARCHITECTURE.md)),
with the ▶ choice as default. The hardware session of 2026-11-08 (firmware V0104P) answered most of them.

| # | Question | Status |
|---|---|---|
| Q1 | Meter encoding and tail bytes | **Answered (HW)**: float32 top bytes, tail = comp / limit masks (§6) |
| Q2 | Frequency step count (300 vs 1000) and Q scale (100 vs 255) | **Mostly answered**: 300 steps from the blob (408); raw values are stored as sent (HW). Still to do: compare a few Hz / Q values with the editor's display |
| Q3 | Delay unit and maximum | **Answered (HW)**: samples at 96 kHz (426 = 4.44 ms in the editor). Maximum (680 ms) not tested |
| Q4 | Compressor `0x30` and limiter `0x3f` layouts | **Answered (HW)**: 206 layout |
| Q5 | Slope table on the 408 and bypass | **Partly**: slope 0 = bypass and raw slopes are stored as sent (HW); the names of the 21 entries are still to compare with the editor |
| Q6 | Gate, phase, names, link on the 408 | **Answered (HW)**, link included (2026-11-10): see `2a` / `3b` in §5.3 |
| Q7 | Matrix crosspoint gain opcode | **Partly (204)**: `41 ch input u16 level` on a DSP 204 (§10); not tried on a 408 |
| Q8 | `0x2c` and `0x10` responses; DSP PIN lock | **Answered (HW)** for the responses (§5.1); PIN lock not tested |
| Q9 | Write ACK format; unsolicited frames | **Answered (HW)**: ACK = `01` (the `26` ACK echoes the name); no unsolicited frames seen |
| Q10 | Second TCP client: refused, accepted, or kicks the first one? Idle timeout? | **Answered (HW)** (§1): one client; a second one waits until the first leaves. An idle connection stays open but stops answering reads after 5–7 s, until a handshake |
| Q11 | Remaining config-blob fields | **Answered (HW)** (§7), except a few trailer bytes and bytes 135 / 99 of the records |
| Q12 | Input HPF/LPF and input delay | **Answered (HW)**: both are accepted and stored |
| Q13 | Compressor ratio table (16 entries, index 15 = "Limit" from the 206) | Open: compare with the editor |

Capture method: Wireshark on the PC that runs the official editor (`tcp.port == 9761`), the
built-in `proxy` sub-command, or a write + `probe dump-config` + `probe diff-config` cycle on a
test preset (what the hardware session did).

---

## 10. Other models: DSP 206 and DSP 204

The simulator can play a DSP 206 or 204 (`tracks-dsp-sim --model 206|204`). Their protocol
profiles are `protocol/profiles/dsp206.toml` and `dsp204.toml`, layered on top of the 408's.

**DSP 206 (2 inputs, 6 outputs).** Everything below comes from the Wireshark captures published
by t.racks-DSP-control (official editor and a real 206, firmware V0104P), decoded with this
project's frame decoder (206). The fixtures are `tests/fixtures/config/dsp206_capture*.bin` and
`tests/fixtures/dsp206/frames.txt`; `tests/unit/test_dsp206.py` checks them.

| Item | DSP 206 | Same as the 408? |
|---|---|---|
| Device address | `02` (also answers on `01`); most likely the unit's front-panel ID (§2) | no: `01` |
| Checksum | full form of §2 | yes (same formula) |
| Identity (`13`) | `DSP206 V0104P` | no: `DSP408 V0104P` |
| Handshake (`10`) | `10 19` | no: `10 13` |
| `22` reply | `22` + 20 zero bytes | no: `22 ff ff` + 28 zero bytes |
| `2c` reply | `2c 00 27 0f 00 00 0x`, last byte = PIN lock (1 after the editor set a PIN with `2f`) | yes, with the lock flag seen set |
| `26` ACK | `01 00` + name | no: `01 01` + name |
| Presets | 20 (`29 00` … `29 13`) | yes |
| Channel indices | In A–B = `00`–`01`, Out 1–6 = `02`–`07` | outputs follow the inputs in both |
| Parameter writes | same opcodes and payloads (`30`, `31`, `32`, `33`, `34`, `35`, `36`, `38`, `3a`, `3b`, `3d`, `3e`, `3f`, `48`, `2a`), ACK `01` | yes |
| Config | 19 pages (18 × 50 + 28) = **928 bytes** | same records: 2 × 140-byte inputs, 6 × 100-byte outputs, 32-byte trailer |
| Meters (`40`) | `LEN = 0x27`: the 408's 12 slots; In A–B in slots 0–1, Out 1–6 in slots 4–9, the other slots zero | same frame |

The config blob is the 408 layout of §7 with fewer channels (`ConfigLayout` in
`protocol/config_map.py`): an output record holds one crosspoint gain per input (96 + 2 × inputs
bytes: 104 on the 408, 100 on the 206) and the trailer has one PEQ band bypass mask per channel
(16 + 2 × channels bytes: 40 on the 408, 32 on the 206). Checked on the captured blob: every
field decodes to the values the editor wrote just before (Out 1 renamed "TEST", −6 dB, 10 ms,
crossover, PEQ band 1, compressor, limiter, Out 1 + Out 2 linked), and the link `2a 02 04`
changes only Out 3's record, exactly as the 408 does. The trailer's PEQ bypass mask offsets are
inferred from the 408 (no captured write toggles them).

The captured meter frames read about −86 dBu on every channel (no signal), which is the 408's
float32 encoding at the ADC noise floor. t.racks-DSP-control reads them as float16, which would
show a constant −7.6 dBFS on an idle device.

**DSP 204 (2 inputs, 4 outputs).** From [Givou/BetterDSPControl](https://git.thiemoo.at/Givou/BetterDSPControl)
(MIT), a control app tested on a real DSP 204, firmware V0104P, over USB (whose HID reports carry
the same frames as TCP) (204). It agrees with everything we know of the 408 and the 206:

| Item | DSP 204 | Conf. |
|---|---|---|
| Device address | `01`, like the 408 (the 206 uses `02`) | 204 |
| Checksum | full form of §2 | 204 |
| Identity (`13`) | starts with `DSP204`; the full string `DSP204 V0104P` is our guess | 204 / HYP |
| Init sequence, presets | the 408's, 20 presets | 204 |
| Channel indices | In A–B = `00`–`01`, Out 1–4 = `02`–`05` | 204 |
| Config | chunks 0–14 = **724 bytes**: the 408 records with 2 inputs and 4 outputs, as computed by `ConfigLayout` | 204 |
| Meters | the 4 + 8 slot frame; the 204 fills slots 0–1 and 4–7; tail byte 1 = limiter-active mask (`00 03` while Out 1+2 limit, `00 0C` for Out 3+4) | 204 |
| Links | same masks and behaviour as the 408 (read on a 204: `3 0` on the inputs, `3 0 12 0` on the outputs for In A+B, Out 1+2, Out 3+4); a write to a member changes the group, except name, routing and mix levels | 204 |
| Handshake, `22` and `26` reply bytes | not documented; the simulator copies the 206's | HYP |

`tests/unit/test_dsp204.py` checks the 204 profile against these observations.

BetterDSPControl also documents, from the 204 (204, not verified on a 408 by this project):

- `41 ch input u16` sets a **mix level** (matrix crosspoint gain, Q7), `49 ch 0/1` bypasses an
  input's GEQ, `15 unit` sets the delay display unit, and the editor sends `11` after a new PIN.
- The config trailer's 6 unknown bytes after the band bypass masks are the test-signal source,
  the test-signal frequency index and one unknown u16; after the two PEQ bypass masks, the u16 at
  `14 + 2C` is the input GEQ bypass mask.
- `2c` reply: byte 0 and bytes 1–4 belong to a time-based lock, byte 5 is the PIN lock flag.
