"""DSP 408 configuration blob (29 × 0x24 pages = 1448 bytes) ↔ raw config model.

The layout was derived from a real DSP 408 dump (``tests/fixtures/config/forest_408.bin``) and
matches the 206/4x4 Mini command layouts (docs/PROTOCOL.md §7). Fields marked ``HYP`` sit in
bytes that were zero in every dump we have; their meaning is a hypothesis to verify on hardware.

Encoding starts from the original image, so unknown bytes are preserved exactly.

Layout::

    0    u16  marker (ff ff = modified user preset, ff 00 = factory/empty)
    2    14   preset name (space padded)
    16   4 × 140  input records
    576  8 × 104  output records
    1408 40   trailer (unknown, preserved)

Input record (140 bytes)::

    0   8      name                  8   4×u16  gate attack, release, hold, threshold
    16  31×u16 GEQ gains             78  8×6    PEQ bands
    126 u16    HPF freq              128 u16    LPF freq
    130 u8     HPF slope             131 u8     LPF slope
    132 u16    gain                  134 u16    delay        (HYP)
    136 u8     mute (HYP)            137 u8     phase        (HYP)
    138 u16    link flags

Output record (104 bytes)::

    0   8      name                  8   u16    matrix input mask
    10  4×u16  crosspoint gains      18  6      crossover (as inputs)
    24  9×6    PEQ bands             78  5×u16  compressor ratio, attack, release, knee, threshold
    88  4×u16  limiter attack, release, reserved, threshold
    96  u16    gain                  98  u16    delay        (HYP)
    100 u8     mute (HYP)            101 u8     phase        (HYP)
    102 u16    link flags

PEQ band (6 bytes): u16 gain, u16 freq, u8 Q, u8 type. Band bypass is **not** stored in the band
and its location is unknown.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field, replace

from dsp408_multiui.protocol.codecs import (
    CHANNEL_NAME_LENGTH,
    PRESET_NAME_LENGTH,
    decode_name,
    encode_name,
)
from dsp408_multiui.protocol.profile import ProtocolProfile

CONFIG_SIZE = 1448
HEADER_SIZE = 16
INPUT_BASE = 16
INPUT_RECORD = 140
OUTPUT_BASE = 576
OUTPUT_RECORD = 104
TRAILER_BASE = 1408
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


@dataclass(frozen=True, slots=True)
class RawConfig:
    marker: int
    preset_name: str
    inputs: tuple[RawInput, ...]
    outputs: tuple[RawOutput, ...]
    image: bytes = field(repr=False)  # original blob; unknown bytes are preserved from it


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
def _u16(blob: bytes, offset: int) -> int:
    value: int = struct.unpack_from("<H", blob, offset)[0]
    return value


def _u16s(blob: bytes, offset: int, count: int) -> tuple[int, ...]:
    return struct.unpack_from(f"<{count}H", blob, offset)


def _peq(blob: bytes, offset: int, count: int) -> tuple[RawPeqBand, ...]:
    return tuple(
        RawPeqBand(*struct.unpack_from("<HHBB", blob, offset + i * PEQ_BAND_SIZE))
        for i in range(count)
    )


def _crossover(blob: bytes, offset: int) -> RawCrossover:
    return RawCrossover(*struct.unpack_from("<HHBB", blob, offset))


def _decode_input(blob: bytes, index: int) -> RawInput:
    o = input_offset(index)
    return RawInput(
        name=decode_name(blob[o : o + CHANNEL_NAME_LENGTH]),
        gate=RawGate(*_u16s(blob, o + 8, 4)),
        geq=_u16s(blob, o + 16, 31),
        peq=_peq(blob, o + 78, 8),
        crossover=_crossover(blob, o + 126),
        gain=_u16(blob, o + 132),
        delay=_u16(blob, o + 134),
        mute=bool(blob[o + 136]),
        phase=bool(blob[o + 137]),
        link=_u16(blob, o + 138),
    )


def _decode_output(blob: bytes, index: int) -> RawOutput:
    o = output_offset(index)
    return RawOutput(
        name=decode_name(blob[o : o + CHANNEL_NAME_LENGTH]),
        matrix=_u16(blob, o + 8),
        crosspoints=_u16s(blob, o + 10, 4),
        crossover=_crossover(blob, o + 18),
        peq=_peq(blob, o + 24, 9),
        compressor=RawCompressor(*_u16s(blob, o + 78, 5)),
        limiter=RawLimiter(*_u16s(blob, o + 88, 4)),
        gain=_u16(blob, o + 96),
        delay=_u16(blob, o + 98),
        mute=bool(blob[o + 100]),
        phase=bool(blob[o + 101]),
        link=_u16(blob, o + 102),
    )


def decode_config(blob: bytes) -> RawConfig:
    if len(blob) != CONFIG_SIZE:
        raise ConfigError(f"config blob is {len(blob)} bytes, expected {CONFIG_SIZE}")
    return RawConfig(
        marker=struct.unpack_from(">H", blob, 0)[0],
        preset_name=decode_name(blob[2:HEADER_SIZE]),
        inputs=tuple(_decode_input(blob, i) for i in range(4)),
        outputs=tuple(_decode_output(blob, i) for i in range(8)),
        image=bytes(blob),
    )


# --- encoding -----------------------------------------------------------------------------
def _put_name(buf: bytearray, offset: int, name: str) -> None:
    buf[offset : offset + CHANNEL_NAME_LENGTH] = encode_name(name, CHANNEL_NAME_LENGTH)


def _put_peq(buf: bytearray, offset: int, bands: tuple[RawPeqBand, ...], count: int) -> None:
    if len(bands) != count:
        raise ConfigError(f"expected {count} PEQ bands, got {len(bands)}")
    for i, b in enumerate(bands):
        struct.pack_into("<HHBB", buf, offset + i * PEQ_BAND_SIZE, b.gain, b.freq, b.q, b.type)


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
    _put_peq(buf, o + 78, ch.peq, 8)
    _put_crossover(buf, o + 126, ch.crossover)
    struct.pack_into("<HHBBH", buf, o + 132, ch.gain, ch.delay, ch.mute, ch.phase, ch.link)


def _encode_output(buf: bytearray, index: int, ch: RawOutput) -> None:
    o = output_offset(index)
    if len(ch.crosspoints) != 4:
        raise ConfigError(f"expected 4 crosspoint gains, got {len(ch.crosspoints)}")
    _put_name(buf, o, ch.name)
    struct.pack_into("<H4H", buf, o + 8, ch.matrix, *ch.crosspoints)
    _put_crossover(buf, o + 18, ch.crossover)
    _put_peq(buf, o + 24, ch.peq, 9)
    c = ch.compressor
    struct.pack_into("<5H", buf, o + 78, c.ratio, c.attack, c.release, c.knee, c.threshold)
    lim = ch.limiter
    struct.pack_into("<4H", buf, o + 88, lim.attack, lim.release, lim.reserved, lim.threshold)
    struct.pack_into("<HHBBH", buf, o + 96, ch.gain, ch.delay, ch.mute, ch.phase, ch.link)


def encode_config(config: RawConfig) -> bytes:
    if len(config.inputs) != 4 or len(config.outputs) != 8:
        raise ConfigError("the DSP 408 layout needs 4 inputs and 8 outputs")
    buf = bytearray(config.image)
    if len(buf) != CONFIG_SIZE:
        raise ConfigError("config image has the wrong size")
    struct.pack_into(">H", buf, 0, config.marker)
    buf[2:HEADER_SIZE] = encode_name(config.preset_name, PRESET_NAME_LENGTH, b" ")
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
