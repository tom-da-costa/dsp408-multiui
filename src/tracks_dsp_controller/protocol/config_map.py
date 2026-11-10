"""DSP 408 configuration blob (29 × 0x24 pages = 1448 bytes) ↔ raw config model.

The layout was derived from a real DSP 408 dump (``tests/fixtures/config/forest_408.bin``) and
then verified field by field on a DSP 408 (firmware V0104P): every parameter write was followed
by a config read and a byte diff (``tests/fixtures/hardware/write_diffs.json``, PROTOCOL §7).

Encoding starts from the original image, so unknown bytes are preserved exactly.

Layout::

    0    u16  marker (ff ff = modified user preset, ff 00 = factory/empty)
    2    14   preset name (space padded, Latin-1 as written by the official editor)
    16   4 × 140  input records
    576  8 × 104  output records
    1408 40   trailer: masks (below)

Input record (140 bytes)::

    0   8      name                  8   4×u16  gate attack, release, hold, threshold
    16  31×u16 GEQ gains             78  8×6    PEQ bands
    126 u16    HPF freq              128 u16    LPF freq
    130 u8     HPF slope             131 u8     LPF slope
    132 u16    gain                  134 u8     phase (1 = inverted)
    135 u8     unknown (preserved)   136 u16    delay, samples at 96 kHz
    138 u16    link mask

Output record (104 bytes)::

    0   8      name                  8   u16    matrix input mask
    10  4×u16  crosspoint gains      18  6      crossover (as inputs)
    24  9×6    PEQ bands             78  5×u16  compressor ratio, attack, release, knee, threshold
    88  4×u16  limiter attack, release, reserved, threshold
    96  u16    gain                  98  u8     phase
    99  u8     unknown (preserved)   100 u16    delay, samples at 96 kHz
    102 u16    link mask

Trailer (offsets from 1408)::

    0   u8      input mute mask (bit n = input n)
    2   u8      output mute mask (bit n = output n)
    4   12×u16  PEQ band bypass mask per channel (protocol index 0-11; bit n = band n)
    34  u8      input PEQ bypass mask
    36  u8      output PEQ bypass mask
    other bytes unknown (preserved)

PEQ band (6 bytes): u16 gain, u16 freq, u8 Q, u8 type.

Link mask: the first channel of a linked group holds the mask of every member (itself
included), the other members hold 0; an unlinked channel holds its own bit or 0. The device
copies every write to the other members of the group, except the name and the matrix.
"""

from __future__ import annotations

import struct
from collections.abc import Sequence
from dataclasses import dataclass, field, replace

from tracks_dsp_controller.protocol.codecs import (
    CHANNEL_NAME_LENGTH,
    PRESET_NAME_LENGTH,
    decode_name,
    encode_stored_name,
)
from tracks_dsp_controller.protocol.profile import ProtocolProfile

CONFIG_SIZE = 1448
HEADER_SIZE = 16
INPUT_BASE = 16
INPUT_RECORD = 140
OUTPUT_BASE = 576
OUTPUT_RECORD = 104
TRAILER_BASE = 1408
INPUT_MUTE_MASK = TRAILER_BASE + 0
OUTPUT_MUTE_MASK = TRAILER_BASE + 2
BAND_BYPASS_BASE = TRAILER_BASE + 4  # 12 × u16, by protocol channel index
INPUT_PEQ_BYPASS_MASK = TRAILER_BASE + 34
OUTPUT_PEQ_BYPASS_MASK = TRAILER_BASE + 36
INPUT_COUNT = 4
OUTPUT_COUNT = 8
PEQ_BAND_SIZE = 6

MARKER_MODIFIED = 0xFFFF
MARKER_FACTORY = 0xFF00  # bytes ff 00

UNITY_GAIN_RAW = 280  # 0 dB
EQ_FLAT_RAW = 120  # 0 dB


class ConfigError(ValueError):
    """Raised when a blob does not match the DSP 408 layout."""


@dataclass(frozen=True, slots=True)
class RawPeqBand:
    gain: int = EQ_FLAT_RAW
    freq: int = 0
    q: int = 35
    type: int = 0
    bypass: bool = False  # stored in the trailer's band bypass mask


@dataclass(frozen=True, slots=True)
class RawCrossover:
    hpf_freq: int = 0
    lpf_freq: int = 300
    hpf_slope: int = 0  # 0 = bypass
    lpf_slope: int = 0


@dataclass(frozen=True, slots=True)
class RawGate:
    attack: int = 0
    release: int = 99
    hold: int = 99
    threshold: int = 0


@dataclass(frozen=True, slots=True)
class RawCompressor:
    ratio: int = 0
    attack: int = 49
    release: int = 499
    knee: int = 0
    threshold: int = 220


@dataclass(frozen=True, slots=True)
class RawLimiter:
    attack: int = 49
    release: int = 499
    reserved: int = 0
    threshold: int = 220


@dataclass(frozen=True, slots=True)
class RawInput:
    name: str
    gate: RawGate
    geq: tuple[int, ...]
    peq: tuple[RawPeqBand, ...]
    crossover: RawCrossover
    gain: int
    delay: int
    mute: bool
    phase: bool
    link: int
    peq_bypass: bool = False


@dataclass(frozen=True, slots=True)
class RawOutput:
    name: str
    matrix: int
    crosspoints: tuple[int, ...]
    crossover: RawCrossover
    peq: tuple[RawPeqBand, ...]
    compressor: RawCompressor
    limiter: RawLimiter
    gain: int
    delay: int
    mute: bool
    phase: bool
    link: int
    peq_bypass: bool = False


@dataclass(frozen=True, slots=True)
class RawConfig:
    marker: int
    preset_name: str
    inputs: tuple[RawInput, ...]
    outputs: tuple[RawOutput, ...]
    image: bytes = field(repr=False)  # original blob; unknown bytes are preserved from it


def link_group(masks: Sequence[int], index: int) -> tuple[int, ...]:
    """Members of the linked group of channel ``index`` (indices within inputs or outputs).

    ``masks`` are the link masks of the channels of one kind (4 inputs or 8 outputs).
    """
    for mask in masks:
        if mask >> index & 1 and mask & ~(1 << index):
            return tuple(i for i in range(len(masks)) if mask >> i & 1)
    return (index,)


def check_layout(profile: ProtocolProfile) -> None:
    """The fixed layout only fits the DSP 408 topology."""
    expected = (4, 8, 8, 9, 31, CONFIG_SIZE)
    actual = (
        profile.input_count,
        profile.output_count,
        profile.peq_bands_input,
        profile.peq_bands_output,
        profile.geq_bands,
        profile.config_size,
    )
    if actual != expected:
        raise ConfigError(f"profile topology {actual} does not match the DSP 408 layout")


def input_offset(index: int) -> int:
    return INPUT_BASE + index * INPUT_RECORD


def output_offset(index: int) -> int:
    return OUTPUT_BASE + index * OUTPUT_RECORD


# --- decoding -----------------------------------------------------------------------------
def _u16(blob: bytes | bytearray, offset: int) -> int:
    value: int = struct.unpack_from("<H", blob, offset)[0]
    return value


def _u16s(blob: bytes, offset: int, count: int) -> tuple[int, ...]:
    return struct.unpack_from(f"<{count}H", blob, offset)


def _peq(blob: bytes, offset: int, count: int, channel: int) -> tuple[RawPeqBand, ...]:
    bypass = _u16(blob, BAND_BYPASS_BASE + 2 * channel)
    bands = []
    for i in range(count):
        gain, freq, q, kind = struct.unpack_from("<HHBB", blob, offset + i * PEQ_BAND_SIZE)
        bands.append(RawPeqBand(gain, freq, q, kind, bool(bypass >> i & 1)))
    return tuple(bands)


def _bit(blob: bytes, offset: int, index: int) -> bool:
    return bool(blob[offset] >> index & 1)


def _crossover(blob: bytes, offset: int) -> RawCrossover:
    return RawCrossover(*struct.unpack_from("<HHBB", blob, offset))


def _decode_input(blob: bytes, index: int) -> RawInput:
    o = input_offset(index)
    return RawInput(
        name=decode_name(blob[o : o + CHANNEL_NAME_LENGTH]),
        gate=RawGate(*_u16s(blob, o + 8, 4)),
        geq=_u16s(blob, o + 16, 31),
        peq=_peq(blob, o + 78, 8, index),
        crossover=_crossover(blob, o + 126),
        gain=_u16(blob, o + 132),
        phase=bool(blob[o + 134]),
        delay=_u16(blob, o + 136),
        link=_u16(blob, o + 138),
        mute=_bit(blob, INPUT_MUTE_MASK, index),
        peq_bypass=_bit(blob, INPUT_PEQ_BYPASS_MASK, index),
    )


def _decode_output(blob: bytes, index: int) -> RawOutput:
    o = output_offset(index)
    return RawOutput(
        name=decode_name(blob[o : o + CHANNEL_NAME_LENGTH]),
        matrix=_u16(blob, o + 8),
        crosspoints=_u16s(blob, o + 10, 4),
        crossover=_crossover(blob, o + 18),
        peq=_peq(blob, o + 24, 9, INPUT_COUNT + index),
        compressor=RawCompressor(*_u16s(blob, o + 78, 5)),
        limiter=RawLimiter(*_u16s(blob, o + 88, 4)),
        gain=_u16(blob, o + 96),
        phase=bool(blob[o + 98]),
        delay=_u16(blob, o + 100),
        link=_u16(blob, o + 102),
        mute=_bit(blob, OUTPUT_MUTE_MASK, index),
        peq_bypass=_bit(blob, OUTPUT_PEQ_BYPASS_MASK, index),
    )


def decode_config(blob: bytes) -> RawConfig:
    if len(blob) != CONFIG_SIZE:
        raise ConfigError(f"config blob is {len(blob)} bytes, expected {CONFIG_SIZE}")
    return RawConfig(
        marker=struct.unpack_from(">H", blob, 0)[0],
        preset_name=decode_name(blob[2:HEADER_SIZE]),
        inputs=tuple(_decode_input(blob, i) for i in range(INPUT_COUNT)),
        outputs=tuple(_decode_output(blob, i) for i in range(OUTPUT_COUNT)),
        image=bytes(blob),
    )


# --- encoding -----------------------------------------------------------------------------
def _put_name(buf: bytearray, offset: int, name: str) -> None:
    buf[offset : offset + CHANNEL_NAME_LENGTH] = encode_stored_name(name, CHANNEL_NAME_LENGTH)


def _put_bit(buf: bytearray, offset: int, index: int, on: bool) -> None:
    buf[offset] = buf[offset] | (1 << index) if on else buf[offset] & ~(1 << index)


def _put_peq(
    buf: bytearray, offset: int, bands: tuple[RawPeqBand, ...], count: int, channel: int
) -> None:
    if len(bands) != count:
        raise ConfigError(f"expected {count} PEQ bands, got {len(bands)}")
    mask_offset = BAND_BYPASS_BASE + 2 * channel
    mask = _u16(buf, mask_offset) & ~((1 << count) - 1)  # keep unknown high bits
    for i, b in enumerate(bands):
        struct.pack_into("<HHBB", buf, offset + i * PEQ_BAND_SIZE, b.gain, b.freq, b.q, b.type)
        mask |= int(b.bypass) << i
    struct.pack_into("<H", buf, mask_offset, mask)


def _put_crossover(buf: bytearray, offset: int, x: RawCrossover) -> None:
    struct.pack_into("<HHBB", buf, offset, x.hpf_freq, x.lpf_freq, x.hpf_slope, x.lpf_slope)


def _encode_input(buf: bytearray, index: int, ch: RawInput) -> None:
    o = input_offset(index)
    if len(ch.geq) != 31:
        raise ConfigError(f"expected 31 GEQ bands, got {len(ch.geq)}")
    _put_name(buf, o, ch.name)
    g = ch.gate
    struct.pack_into("<4H", buf, o + 8, g.attack, g.release, g.hold, g.threshold)
    struct.pack_into("<31H", buf, o + 16, *ch.geq)
    _put_peq(buf, o + 78, ch.peq, 8, index)
    _put_crossover(buf, o + 126, ch.crossover)
    struct.pack_into("<HB", buf, o + 132, ch.gain, ch.phase)
    struct.pack_into("<HH", buf, o + 136, ch.delay, ch.link)
    _put_bit(buf, INPUT_MUTE_MASK, index, ch.mute)
    _put_bit(buf, INPUT_PEQ_BYPASS_MASK, index, ch.peq_bypass)


def _encode_output(buf: bytearray, index: int, ch: RawOutput) -> None:
    o = output_offset(index)
    if len(ch.crosspoints) != 4:
        raise ConfigError(f"expected 4 crosspoint gains, got {len(ch.crosspoints)}")
    _put_name(buf, o, ch.name)
    struct.pack_into("<H4H", buf, o + 8, ch.matrix, *ch.crosspoints)
    _put_crossover(buf, o + 18, ch.crossover)
    _put_peq(buf, o + 24, ch.peq, 9, INPUT_COUNT + index)
    c = ch.compressor
    struct.pack_into("<5H", buf, o + 78, c.ratio, c.attack, c.release, c.knee, c.threshold)
    lim = ch.limiter
    struct.pack_into("<4H", buf, o + 88, lim.attack, lim.release, lim.reserved, lim.threshold)
    struct.pack_into("<HB", buf, o + 96, ch.gain, ch.phase)
    struct.pack_into("<HH", buf, o + 100, ch.delay, ch.link)
    _put_bit(buf, OUTPUT_MUTE_MASK, index, ch.mute)
    _put_bit(buf, OUTPUT_PEQ_BYPASS_MASK, index, ch.peq_bypass)


def encode_config(config: RawConfig) -> bytes:
    if len(config.inputs) != INPUT_COUNT or len(config.outputs) != OUTPUT_COUNT:
        raise ConfigError("the DSP 408 layout needs 4 inputs and 8 outputs")
    buf = bytearray(config.image)
    if len(buf) != CONFIG_SIZE:
        raise ConfigError("config image has the wrong size")
    struct.pack_into(">H", buf, 0, config.marker)
    buf[2:HEADER_SIZE] = encode_stored_name(config.preset_name, PRESET_NAME_LENGTH, b" ")
    for i, inp in enumerate(config.inputs):
        _encode_input(buf, i, inp)
    for i, out in enumerate(config.outputs):
        _encode_output(buf, i, out)
    return bytes(buf)


# --- pages ---------------------------------------------------------------------------------
def split_pages(blob: bytes, profile: ProtocolProfile) -> list[bytes]:
    """Cut a blob into the pages returned by 0x27 requests."""
    check_layout(profile)
    pages = []
    offset = 0
    for page in range(profile.page_count):
        length = profile.page_length(page)
        pages.append(blob[offset : offset + length])
        offset += length
    return pages


def join_pages(pages: dict[int, bytes], profile: ProtocolProfile) -> bytes:
    """Reassemble pages (keyed by page index) into a blob, checking every page's length."""
    check_layout(profile)
    missing = [p for p in range(profile.page_count) if p not in pages]
    if missing:
        raise ConfigError(f"missing config pages: {missing}")
    parts = []
    for page in range(profile.page_count):
        if len(pages[page]) != profile.page_length(page):
            raise ConfigError(f"page {page} has {len(pages[page])} bytes")
        parts.append(pages[page])
    return b"".join(parts)


# --- defaults ------------------------------------------------------------------------------
# Default PEQ centre frequencies seen in the DSP 408 dump (raw, 300-step scale).
DEFAULT_INPUT_PEQ_FREQS = (41, 71, 101, 140, 170, 200, 240, 270)
DEFAULT_OUTPUT_PEQ_FREQS = (31, 63, 95, 127, 158, 190, 222, 253, 285)


def default_config(preset_name: str = "Default Preset") -> RawConfig:
    """A flat, factory-like configuration (used by the simulator)."""
    inputs = tuple(
        RawInput(
            name=f"In{chr(ord('A') + i)}",
            gate=RawGate(),
            geq=(EQ_FLAT_RAW,) * 31,
            peq=tuple(RawPeqBand(freq=f) for f in DEFAULT_INPUT_PEQ_FREQS),
            crossover=RawCrossover(),
            gain=UNITY_GAIN_RAW,
            delay=0,
            mute=False,
            phase=False,
            link=1 << i,
        )
        for i in range(4)
    )
    outputs = tuple(
        RawOutput(
            name=f"Out{i + 1}",
            matrix=1 << (i % 4),
            crosspoints=(UNITY_GAIN_RAW,) * 4,
            crossover=RawCrossover(),
            peq=tuple(RawPeqBand(freq=f) for f in DEFAULT_OUTPUT_PEQ_FREQS),
            compressor=RawCompressor(),
            limiter=RawLimiter(),
            gain=UNITY_GAIN_RAW,
            delay=0,
            mute=False,
            phase=False,
            link=1 << i,
        )
        for i in range(8)
    )
    image = bytearray(CONFIG_SIZE)
    config = RawConfig(MARKER_FACTORY, preset_name, inputs, outputs, bytes(image))
    return replace(config, image=encode_config(config))


# --- offset annotation (for diff tools) ------------------------------------------------------
_INPUT_FIELDS: tuple[tuple[int, int, str], ...] = (
    (0, 8, "name"),
    (8, 2, "gate.attack"),
    (10, 2, "gate.release"),
    (12, 2, "gate.hold"),
    (14, 2, "gate.threshold"),
    (126, 2, "crossover.hpf_freq"),
    (128, 2, "crossover.lpf_freq"),
    (130, 1, "crossover.hpf_slope"),
    (131, 1, "crossover.lpf_slope"),
    (132, 2, "gain"),
    (134, 1, "phase"),
    (135, 1, "unknown"),
    (136, 2, "delay"),
    (138, 2, "link"),
)
_OUTPUT_FIELDS: tuple[tuple[int, int, str], ...] = (
    (0, 8, "name"),
    (8, 2, "matrix"),
    (18, 2, "crossover.hpf_freq"),
    (20, 2, "crossover.lpf_freq"),
    (22, 1, "crossover.hpf_slope"),
    (23, 1, "crossover.lpf_slope"),
    (78, 2, "compressor.ratio"),
    (80, 2, "compressor.attack"),
    (82, 2, "compressor.release"),
    (84, 2, "compressor.knee"),
    (86, 2, "compressor.threshold"),
    (88, 2, "limiter.attack"),
    (90, 2, "limiter.release"),
    (92, 2, "limiter.reserved"),
    (94, 2, "limiter.threshold"),
    (96, 2, "gain"),
    (98, 1, "phase"),
    (99, 1, "unknown"),
    (100, 2, "delay"),
    (102, 2, "link"),
)
_PEQ_FIELDS = ("gain", "gain", "freq", "freq", "q", "type")


def _channel_name(channel: int) -> str:
    return f"in{channel}" if channel < INPUT_COUNT else f"out{channel - INPUT_COUNT}"


def _trailer_field(offset: int) -> str:
    named = {
        INPUT_MUTE_MASK: "inputs.mute_mask",
        OUTPUT_MUTE_MASK: "outputs.mute_mask",
        INPUT_PEQ_BYPASS_MASK: "inputs.peq_bypass_mask",
        OUTPUT_PEQ_BYPASS_MASK: "outputs.peq_bypass_mask",
    }
    if offset in named:
        return named[offset]
    if BAND_BYPASS_BASE <= offset < BAND_BYPASS_BASE + 24:
        channel = (offset - BAND_BYPASS_BASE) // 2
        return f"{_channel_name(channel)}.peq_band_bypass_mask"
    return f"trailer[{offset - TRAILER_BASE}]"


def field_at(offset: int) -> str:
    """Human-readable name of the field that contains byte ``offset`` of the blob."""
    if not 0 <= offset < CONFIG_SIZE:
        raise ValueError(f"offset outside the config blob: {offset}")
    if offset < 2:
        return "marker"
    if offset < HEADER_SIZE:
        return "preset_name"
    if offset >= TRAILER_BASE:
        return _trailer_field(offset)
    if offset < OUTPUT_BASE:
        index, rel = divmod(offset - INPUT_BASE, INPUT_RECORD)
        prefix = f"in{index}"
        if 16 <= rel < 78:
            return f"{prefix}.geq[{(rel - 16) // 2}]"
        if 78 <= rel < 126:
            band, pos = divmod(rel - 78, PEQ_BAND_SIZE)
            return f"{prefix}.peq[{band}].{_PEQ_FIELDS[pos]}"
        table = _INPUT_FIELDS
    else:
        index, rel = divmod(offset - OUTPUT_BASE, OUTPUT_RECORD)
        prefix = f"out{index}"
        if 10 <= rel < 18:
            return f"{prefix}.crosspoints[{(rel - 10) // 2}]"
        if 24 <= rel < 78:
            band, pos = divmod(rel - 24, PEQ_BAND_SIZE)
            return f"{prefix}.peq[{band}].{_PEQ_FIELDS[pos]}"
        table = _OUTPUT_FIELDS
    for start, size, name in table:
        if start <= rel < start + size:
            return f"{prefix}.{name}"
    return f"{prefix}.+{rel}"  # pragma: no cover - every record byte is mapped


def diff_blobs(before: bytes, after: bytes) -> list[tuple[int, int, int, str]]:
    """Changed bytes as ``(offset, old, new, field)`` tuples."""
    if len(before) != CONFIG_SIZE or len(after) != CONFIG_SIZE:
        raise ConfigError("both blobs must be full config images")
    return [
        (i, a, b, field_at(i)) for i, (a, b) in enumerate(zip(before, after, strict=True)) if a != b
    ]
