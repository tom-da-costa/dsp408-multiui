"""Configuration blob (0x24 pages) ↔ raw config model, for the DSP 408 and its siblings.

The layout was derived from a real DSP 408 dump (``tests/fixtures/config/forest_408.bin``) and
then verified field by field on a DSP 408 (firmware V0104P): every parameter write was followed
by a config read and a byte diff (``tests/fixtures/hardware/write_diffs.json``, PROTOCOL §7).
The DSP 206 uses the same records with 2 inputs and 6 outputs (a config read captured from a real
206, ``tests/fixtures/config/dsp206_capture.bin``); only the sizes that depend on the channel
counts change. ``ConfigLayout`` computes them; the module constants are the DSP 408 values.

Encoding starts from the original image, so unknown bytes are preserved exactly.

Layout (I inputs, O outputs; 408: I = 4, O = 8, 1448 bytes; 206: I = 2, O = 6, 928 bytes)::

    0    u16  marker (ff ff = modified user preset, ff 00 = factory/empty)
    2    14   preset name (space padded, Latin-1 as written by the official editor)
    16   I × 140        input records
         O × (96 + 2I)  output records (408: 104 bytes, 206: 100)
         16 + 2(I + O)  trailer: masks (below)

Input record (140 bytes)::

    0   8      name                  8   4×u16  gate attack, release, hold, threshold
    16  31×u16 GEQ gains             78  8×6    PEQ bands
    126 u16    HPF freq              128 u16    LPF freq
    130 u8     HPF slope             131 u8     LPF slope
    132 u16    gain                  134 u8     phase (1 = inverted)
    135 u8     unknown (preserved)   136 u16    delay, samples at 96 kHz
    138 u16    link mask

Output record (offsets for the 408; from the crossover on, subtract 2 per missing input)::

    0   8      name                  8   u16    matrix input mask
    10  I×u16  crosspoint gains      18  6      crossover (as inputs)
    24  9×6    PEQ bands             78  5×u16  compressor ratio, attack, release, knee, threshold
    88  4×u16  limiter attack, release, reserved, threshold
    96  u16    gain                  98  u8     phase
    99  u8     unknown (preserved)   100 u16    delay, samples at 96 kHz
    102 u16    link mask

Trailer (C = I + O channels; 408 offsets from 1408)::

    0       u8      input mute mask (bit n = input n)
    2       u8      output mute mask (bit n = output n)
    4       C×u16   PEQ band bypass mask per channel (protocol index; bit n = band n)
    10 + 2C u8      input PEQ bypass mask (408: 34)
    12 + 2C u8      output PEQ bypass mask (408: 36)
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

HEADER_SIZE = 16
INPUT_RECORD = 140
PEQ_BAND_SIZE = 6
INPUT_PEQ_BANDS = 8
OUTPUT_PEQ_BANDS = 9
GEQ_BANDS = 31


@dataclass(frozen=True, slots=True)
class ConfigLayout:
    """Offsets of the config blob for a model with ``inputs`` inputs and ``outputs`` outputs."""

    inputs: int = 4
    outputs: int = 8

    @property
    def channels(self) -> int:
        return self.inputs + self.outputs

    @property
    def output_record(self) -> int:
        return 96 + 2 * self.inputs

    @property
    def output_base(self) -> int:
        return HEADER_SIZE + self.inputs * INPUT_RECORD

    @property
    def trailer_base(self) -> int:
        return self.output_base + self.outputs * self.output_record

    @property
    def size(self) -> int:
        return self.trailer_base + 16 + 2 * self.channels

    @property
    def input_mute_mask(self) -> int:
        return self.trailer_base

    @property
    def output_mute_mask(self) -> int:
        return self.trailer_base + 2

    @property
    def band_bypass_base(self) -> int:
        return self.trailer_base + 4

    @property
    def input_peq_bypass_mask(self) -> int:
        return self.trailer_base + 10 + 2 * self.channels

    @property
    def output_peq_bypass_mask(self) -> int:
        return self.trailer_base + 12 + 2 * self.channels

    # Offsets inside an output record, after the crosspoint gains (one u16 per input).
    @property
    def out_crossover(self) -> int:
        return 10 + 2 * self.inputs

    @property
    def out_peq(self) -> int:
        return self.out_crossover + 6

    @property
    def out_compressor(self) -> int:
        return self.out_peq + OUTPUT_PEQ_BANDS * PEQ_BAND_SIZE

    @property
    def out_limiter(self) -> int:
        return self.out_compressor + 10

    @property
    def out_gain(self) -> int:
        return self.out_limiter + 8

    def input_offset(self, index: int) -> int:
        return HEADER_SIZE + index * INPUT_RECORD

    def output_offset(self, index: int) -> int:
        return self.output_base + index * self.output_record


LAYOUT_408 = ConfigLayout(4, 8)


def layout_for(profile: ProtocolProfile) -> ConfigLayout:
    return ConfigLayout(profile.input_count, profile.output_count)


# DSP 408 values, kept as constants for tools and tests.
CONFIG_SIZE = LAYOUT_408.size  # 1448
INPUT_BASE = HEADER_SIZE
OUTPUT_BASE = LAYOUT_408.output_base  # 576
OUTPUT_RECORD = LAYOUT_408.output_record  # 104
TRAILER_BASE = LAYOUT_408.trailer_base  # 1408
INPUT_MUTE_MASK = LAYOUT_408.input_mute_mask
OUTPUT_MUTE_MASK = LAYOUT_408.output_mute_mask
BAND_BYPASS_BASE = LAYOUT_408.band_bypass_base  # 12 × u16, by protocol channel index
INPUT_PEQ_BYPASS_MASK = LAYOUT_408.input_peq_bypass_mask  # trailer + 34
OUTPUT_PEQ_BYPASS_MASK = LAYOUT_408.output_peq_bypass_mask  # trailer + 36
INPUT_COUNT = LAYOUT_408.inputs
OUTPUT_COUNT = LAYOUT_408.outputs

MARKER_MODIFIED = 0xFFFF
MARKER_FACTORY = 0xFF00  # bytes ff 00

UNITY_GAIN_RAW = 280  # 0 dB
EQ_FLAT_RAW = 120  # 0 dB


class ConfigError(ValueError):
    """Raised when a blob or a profile does not match the config layout."""


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


def check_layout(profile: ProtocolProfile) -> ConfigLayout:
    """Check that ``profile`` fits the record formats and return its layout."""
    layout = layout_for(profile)
    bands = (profile.peq_bands_input, profile.peq_bands_output, profile.geq_bands)
    if bands != (INPUT_PEQ_BANDS, OUTPUT_PEQ_BANDS, GEQ_BANDS):
        raise ConfigError(f"profile bands {bands} do not match the config records")
    if profile.config_size != layout.size:
        raise ConfigError(
            f"profile pages hold {profile.config_size} bytes, but {profile.input_count} inputs "
            f"and {profile.output_count} outputs need {layout.size}"
        )
    return layout


def input_offset(index: int, layout: ConfigLayout = LAYOUT_408) -> int:
    return layout.input_offset(index)


def output_offset(index: int, layout: ConfigLayout = LAYOUT_408) -> int:
    return layout.output_offset(index)


# --- decoding -----------------------------------------------------------------------------
def _u16(blob: bytes | bytearray, offset: int) -> int:
    value: int = struct.unpack_from("<H", blob, offset)[0]
    return value


def _u16s(blob: bytes, offset: int, count: int) -> tuple[int, ...]:
    return struct.unpack_from(f"<{count}H", blob, offset)


def _peq(
    blob: bytes, offset: int, count: int, channel: int, layout: ConfigLayout
) -> tuple[RawPeqBand, ...]:
    bypass = _u16(blob, layout.band_bypass_base + 2 * channel)
    bands = []
    for i in range(count):
        gain, freq, q, kind = struct.unpack_from("<HHBB", blob, offset + i * PEQ_BAND_SIZE)
        bands.append(RawPeqBand(gain, freq, q, kind, bool(bypass >> i & 1)))
    return tuple(bands)


def _bit(blob: bytes, offset: int, index: int) -> bool:
    return bool(blob[offset] >> index & 1)


def _crossover(blob: bytes, offset: int) -> RawCrossover:
    return RawCrossover(*struct.unpack_from("<HHBB", blob, offset))


def _decode_input(blob: bytes, index: int, layout: ConfigLayout) -> RawInput:
    o = layout.input_offset(index)
    return RawInput(
        name=decode_name(blob[o : o + CHANNEL_NAME_LENGTH]),
        gate=RawGate(*_u16s(blob, o + 8, 4)),
        geq=_u16s(blob, o + 16, GEQ_BANDS),
        peq=_peq(blob, o + 78, INPUT_PEQ_BANDS, index, layout),
        crossover=_crossover(blob, o + 126),
        gain=_u16(blob, o + 132),
        phase=bool(blob[o + 134]),
        delay=_u16(blob, o + 136),
        link=_u16(blob, o + 138),
        mute=_bit(blob, layout.input_mute_mask, index),
        peq_bypass=_bit(blob, layout.input_peq_bypass_mask, index),
    )


def _decode_output(blob: bytes, index: int, layout: ConfigLayout) -> RawOutput:
    o = layout.output_offset(index)
    g = o + layout.out_gain
    return RawOutput(
        name=decode_name(blob[o : o + CHANNEL_NAME_LENGTH]),
        matrix=_u16(blob, o + 8),
        crosspoints=_u16s(blob, o + 10, layout.inputs),
        crossover=_crossover(blob, o + layout.out_crossover),
        peq=_peq(blob, o + layout.out_peq, OUTPUT_PEQ_BANDS, layout.inputs + index, layout),
        compressor=RawCompressor(*_u16s(blob, o + layout.out_compressor, 5)),
        limiter=RawLimiter(*_u16s(blob, o + layout.out_limiter, 4)),
        gain=_u16(blob, g),
        phase=bool(blob[g + 2]),
        delay=_u16(blob, g + 4),
        link=_u16(blob, g + 6),
        mute=_bit(blob, layout.output_mute_mask, index),
        peq_bypass=_bit(blob, layout.output_peq_bypass_mask, index),
    )


def decode_config(blob: bytes, layout: ConfigLayout = LAYOUT_408) -> RawConfig:
    if len(blob) != layout.size:
        raise ConfigError(f"config blob is {len(blob)} bytes, expected {layout.size}")
    return RawConfig(
        marker=struct.unpack_from(">H", blob, 0)[0],
        preset_name=decode_name(blob[2:HEADER_SIZE]),
        inputs=tuple(_decode_input(blob, i, layout) for i in range(layout.inputs)),
        outputs=tuple(_decode_output(blob, i, layout) for i in range(layout.outputs)),
        image=bytes(blob),
    )


def config_layout(config: RawConfig) -> ConfigLayout:
    """Layout of a decoded config (from its channel counts)."""
    return ConfigLayout(len(config.inputs), len(config.outputs))


# --- encoding -----------------------------------------------------------------------------
def _put_name(buf: bytearray, offset: int, name: str) -> None:
    buf[offset : offset + CHANNEL_NAME_LENGTH] = encode_stored_name(name, CHANNEL_NAME_LENGTH)


def _put_bit(buf: bytearray, offset: int, index: int, on: bool) -> None:
    buf[offset] = buf[offset] | (1 << index) if on else buf[offset] & ~(1 << index)


def _put_peq(
    buf: bytearray,
    offset: int,
    bands: tuple[RawPeqBand, ...],
    count: int,
    channel: int,
    layout: ConfigLayout,
) -> None:
    if len(bands) != count:
        raise ConfigError(f"expected {count} PEQ bands, got {len(bands)}")
    mask_offset = layout.band_bypass_base + 2 * channel
    mask = _u16(buf, mask_offset) & ~((1 << count) - 1)  # keep unknown high bits
    for i, b in enumerate(bands):
        struct.pack_into("<HHBB", buf, offset + i * PEQ_BAND_SIZE, b.gain, b.freq, b.q, b.type)
        mask |= int(b.bypass) << i
    struct.pack_into("<H", buf, mask_offset, mask)


def _put_crossover(buf: bytearray, offset: int, x: RawCrossover) -> None:
    struct.pack_into("<HHBB", buf, offset, x.hpf_freq, x.lpf_freq, x.hpf_slope, x.lpf_slope)


def _encode_input(buf: bytearray, index: int, ch: RawInput, layout: ConfigLayout) -> None:
    o = layout.input_offset(index)
    if len(ch.geq) != GEQ_BANDS:
        raise ConfigError(f"expected {GEQ_BANDS} GEQ bands, got {len(ch.geq)}")
    _put_name(buf, o, ch.name)
    g = ch.gate
    struct.pack_into("<4H", buf, o + 8, g.attack, g.release, g.hold, g.threshold)
    struct.pack_into(f"<{GEQ_BANDS}H", buf, o + 16, *ch.geq)
    _put_peq(buf, o + 78, ch.peq, INPUT_PEQ_BANDS, index, layout)
    _put_crossover(buf, o + 126, ch.crossover)
    struct.pack_into("<HB", buf, o + 132, ch.gain, ch.phase)
    struct.pack_into("<HH", buf, o + 136, ch.delay, ch.link)
    _put_bit(buf, layout.input_mute_mask, index, ch.mute)
    _put_bit(buf, layout.input_peq_bypass_mask, index, ch.peq_bypass)


def _encode_output(buf: bytearray, index: int, ch: RawOutput, layout: ConfigLayout) -> None:
    o = layout.output_offset(index)
    if len(ch.crosspoints) != layout.inputs:
        raise ConfigError(f"expected {layout.inputs} crosspoint gains, got {len(ch.crosspoints)}")
    _put_name(buf, o, ch.name)
    struct.pack_into(f"<H{layout.inputs}H", buf, o + 8, ch.matrix, *ch.crosspoints)
    _put_crossover(buf, o + layout.out_crossover, ch.crossover)
    _put_peq(buf, o + layout.out_peq, ch.peq, OUTPUT_PEQ_BANDS, layout.inputs + index, layout)
    c = ch.compressor
    struct.pack_into(
        "<5H", buf, o + layout.out_compressor, c.ratio, c.attack, c.release, c.knee, c.threshold
    )
    lim = ch.limiter
    struct.pack_into(
        "<4H", buf, o + layout.out_limiter, lim.attack, lim.release, lim.reserved, lim.threshold
    )
    g = o + layout.out_gain
    struct.pack_into("<HB", buf, g, ch.gain, ch.phase)
    struct.pack_into("<HH", buf, g + 4, ch.delay, ch.link)
    _put_bit(buf, layout.output_mute_mask, index, ch.mute)
    _put_bit(buf, layout.output_peq_bypass_mask, index, ch.peq_bypass)


def encode_config(config: RawConfig) -> bytes:
    """Encode ``config`` into its image; the layout follows its channel counts."""
    layout = config_layout(config)
    if not 1 <= layout.inputs <= 8 or not 1 <= layout.outputs <= 8:
        raise ConfigError("a config needs 1 to 8 inputs and 1 to 8 outputs")
    buf = bytearray(config.image)
    if len(buf) != layout.size:
        raise ConfigError(
            f"config image is {len(buf)} bytes, {layout.inputs} inputs and "
            f"{layout.outputs} outputs need {layout.size}"
        )
    struct.pack_into(">H", buf, 0, config.marker)
    buf[2:HEADER_SIZE] = encode_stored_name(config.preset_name, PRESET_NAME_LENGTH, b" ")
    for i, inp in enumerate(config.inputs):
        _encode_input(buf, i, inp, layout)
    for i, out in enumerate(config.outputs):
        _encode_output(buf, i, out, layout)
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
# Default PEQ centre frequencies seen in the DSP 408 dump (raw, 300-step scale); the DSP 206
# capture has the same output values.
DEFAULT_INPUT_PEQ_FREQS = (41, 71, 101, 140, 170, 200, 240, 270)
DEFAULT_OUTPUT_PEQ_FREQS = (31, 63, 95, 127, 158, 190, 222, 253, 285)


def default_config(
    preset_name: str = "Default Preset", layout: ConfigLayout = LAYOUT_408
) -> RawConfig:
    """A flat, factory-like configuration (used by the simulator)."""
    inputs = tuple(
        RawInput(
            name=f"In{chr(ord('A') + i)}",
            gate=RawGate(),
            geq=(EQ_FLAT_RAW,) * GEQ_BANDS,
            peq=tuple(RawPeqBand(freq=f) for f in DEFAULT_INPUT_PEQ_FREQS),
            crossover=RawCrossover(),
            gain=UNITY_GAIN_RAW,
            delay=0,
            mute=False,
            phase=False,
            link=1 << i,
        )
        for i in range(layout.inputs)
    )
    outputs = tuple(
        RawOutput(
            name=f"Out{i + 1}",
            matrix=1 << (i % layout.inputs),
            crosspoints=(UNITY_GAIN_RAW,) * layout.inputs,
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
        for i in range(layout.outputs)
    )
    image = bytearray(layout.size)
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


def _output_fields(layout: ConfigLayout) -> tuple[tuple[int, int, str], ...]:
    x, c, lim, g = layout.out_crossover, layout.out_compressor, layout.out_limiter, layout.out_gain
    return (
        (0, 8, "name"),
        (8, 2, "matrix"),
        (x, 2, "crossover.hpf_freq"),
        (x + 2, 2, "crossover.lpf_freq"),
        (x + 4, 1, "crossover.hpf_slope"),
        (x + 5, 1, "crossover.lpf_slope"),
        (c, 2, "compressor.ratio"),
        (c + 2, 2, "compressor.attack"),
        (c + 4, 2, "compressor.release"),
        (c + 6, 2, "compressor.knee"),
        (c + 8, 2, "compressor.threshold"),
        (lim, 2, "limiter.attack"),
        (lim + 2, 2, "limiter.release"),
        (lim + 4, 2, "limiter.reserved"),
        (lim + 6, 2, "limiter.threshold"),
        (g, 2, "gain"),
        (g + 2, 1, "phase"),
        (g + 3, 1, "unknown"),
        (g + 4, 2, "delay"),
        (g + 6, 2, "link"),
    )


_PEQ_FIELDS = ("gain", "gain", "freq", "freq", "q", "type")


def _channel_name(channel: int, layout: ConfigLayout) -> str:
    return f"in{channel}" if channel < layout.inputs else f"out{channel - layout.inputs}"


def _trailer_field(offset: int, layout: ConfigLayout) -> str:
    named = {
        layout.input_mute_mask: "inputs.mute_mask",
        layout.output_mute_mask: "outputs.mute_mask",
        layout.input_peq_bypass_mask: "inputs.peq_bypass_mask",
        layout.output_peq_bypass_mask: "outputs.peq_bypass_mask",
    }
    if offset in named:
        return named[offset]
    base = layout.band_bypass_base
    if base <= offset < base + 2 * layout.channels:
        channel = (offset - base) // 2
        return f"{_channel_name(channel, layout)}.peq_band_bypass_mask"
    return f"trailer[{offset - layout.trailer_base}]"


def field_at(offset: int, layout: ConfigLayout = LAYOUT_408) -> str:
    """Human-readable name of the field that contains byte ``offset`` of the blob."""
    if not 0 <= offset < layout.size:
        raise ValueError(f"offset outside the config blob: {offset}")
    if offset < 2:
        return "marker"
    if offset < HEADER_SIZE:
        return "preset_name"
    if offset >= layout.trailer_base:
        return _trailer_field(offset, layout)
    if offset < layout.output_base:
        index, rel = divmod(offset - HEADER_SIZE, INPUT_RECORD)
        prefix = f"in{index}"
        if 16 <= rel < 78:
            return f"{prefix}.geq[{(rel - 16) // 2}]"
        if 78 <= rel < 126:
            band, pos = divmod(rel - 78, PEQ_BAND_SIZE)
            return f"{prefix}.peq[{band}].{_PEQ_FIELDS[pos]}"
        table = _INPUT_FIELDS
    else:
        index, rel = divmod(offset - layout.output_base, layout.output_record)
        prefix = f"out{index}"
        if 10 <= rel < layout.out_crossover:
            return f"{prefix}.crosspoints[{(rel - 10) // 2}]"
        if layout.out_peq <= rel < layout.out_compressor:
            band, pos = divmod(rel - layout.out_peq, PEQ_BAND_SIZE)
            return f"{prefix}.peq[{band}].{_PEQ_FIELDS[pos]}"
        table = _output_fields(layout)
    for start, size, name in table:
        if start <= rel < start + size:
            return f"{prefix}.{name}"
    return f"{prefix}.+{rel}"  # pragma: no cover - every record byte is mapped


def diff_blobs(
    before: bytes, after: bytes, layout: ConfigLayout = LAYOUT_408
) -> list[tuple[int, int, int, str]]:
    """Changed bytes as ``(offset, old, new, field)`` tuples."""
    if len(before) != layout.size or len(after) != layout.size:
        raise ConfigError("both blobs must be full config images")
    return [
        (i, a, b, field_at(i, layout))
        for i, (a, b) in enumerate(zip(before, after, strict=True))
        if a != b
    ]
