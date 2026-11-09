"""Meter frames (0x40 response, docs/PROTOCOL.md §6).

Layout of the data after the opcode: one 3-byte triplet per channel (inputs first, then
outputs), then ``meter_tail_length`` tail bytes. How a triplet encodes the level is a profile
setting because the sources disagree:

* ``float32`` (DSP 408, verified on hardware): the triplet is the top three bytes of a
  little-endian IEEE-754 float32 (byte 2 = bits 8-15, byte 0 = bits 16-23, byte 1 = bits
  24-31), i.e. ``float32(00 b2 b0 b1)``. The value is linear, relative to full scale, and can
  exceed 1.0. Full scale is +20 dBu, so with the default reference (0.1 = 0 dBu) levels are in
  dBu, the unit of the dynamics thresholds: a compressor set to +1 dBu engages when the meter
  reads about +1 dBu.
  A muted channel reads about 1e-35; NaN/inf means "no data".
* ``float16``: bytes 0-1 read as a half float (dsp-408-ui). Wrong on a real 408 (it gives a
  compressed, offset scale); kept for comparison.
* ``level24``: ``level = b2 | b0 << 8 | b1 << 16`` (24-bit linear, 4x4 Mini).

Levels are reported in dB relative to ``meter_reference`` and floored at ``meter_floor_db``.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass

from dsp408_multiui.protocol.profile import MeterFormat, ProtocolProfile

TRIPLET = 3


class MeterError(ValueError):
    """Raised when a meter frame does not match the profile."""


@dataclass(frozen=True, slots=True)
class MeterReading:
    levels_db: tuple[float | None, ...]  # one per channel; None = no data
    clip: tuple[bool, ...]  # one per channel, derived from the level
    limit: tuple[bool, ...] | None  # one per output, None if the profile has no such field
    comp: tuple[bool, ...] | None
    input_clip_flag: bool | None  # device-wide "an input clips" flag, if the profile has it


def meter_data_length(profile: ProtocolProfile) -> int:
    return profile.channel_count * TRIPLET + profile.meter_tail_length


def _linear_to_db(linear: float, profile: ProtocolProfile) -> float:
    if linear <= 0:
        return profile.meter_floor_db
    return max(profile.meter_floor_db, 20 * math.log10(linear / profile.meter_reference))


def _db_to_linear(db: float, profile: ProtocolProfile) -> float:
    if db <= profile.meter_floor_db:
        return 0.0
    return profile.meter_reference * 10 ** (db / 20)


def _decode_triplet(triplet: bytes, profile: ProtocolProfile) -> float | None:
    if profile.meter_format is MeterFormat.FLOAT32:
        (value,) = struct.unpack("<f", bytes((0, triplet[2], triplet[0], triplet[1])))
        if not math.isfinite(value):
            return None
        return float(abs(value))
    if profile.meter_format is MeterFormat.FLOAT16:
        (linear,) = struct.unpack("<e", triplet[:2])
        if not math.isfinite(linear):
            return None
        return float(abs(linear))
    if triplet == b"\xff\xff\xff":
        return None
    return float(triplet[2] | triplet[0] << 8 | triplet[1] << 16)


def _encode_triplet(linear: float | None, profile: ProtocolProfile) -> bytes:
    if profile.meter_format is MeterFormat.FLOAT32:
        raw = struct.pack("<f", math.nan if linear is None else linear)
        return bytes((raw[2], raw[3], raw[1]))
    if profile.meter_format is MeterFormat.FLOAT16:
        if linear is None:
            return b"\xff\xff\x00"
        linear = min(linear, 65504.0)  # largest finite float16
        peak = min(255, round(linear * 64))
        return struct.pack("<e", linear) + bytes((peak,))
    if linear is None:
        return b"\xff\xff\xff"
    level = min(round(linear), 0xFFFFFE)
    return bytes(((level >> 8) & 0xFF, (level >> 16) & 0xFF, level & 0xFF))


def _bits(value: int, count: int) -> tuple[bool, ...]:
    return tuple(bool(value >> i & 1) for i in range(count))


def decode_meters(data: bytes, profile: ProtocolProfile) -> MeterReading:
    """Decode the data of a meter frame (payload without the 0x40 opcode)."""
    expected = meter_data_length(profile)
    if len(data) != expected:
        raise MeterError(f"meter data is {len(data)} bytes, profile expects {expected}")
    levels: list[float | None] = []
    for ch in range(profile.channel_count):
        linear = _decode_triplet(data[ch * TRIPLET : (ch + 1) * TRIPLET], profile)
        levels.append(None if linear is None else _linear_to_db(linear, profile))
    tail = data[profile.channel_count * TRIPLET :]
    outputs = profile.output_count

    def tail_bits(index: int | None) -> tuple[bool, ...] | None:
        return None if index is None else _bits(tail[index], outputs)

    clip_index = profile.meter_tail_clip_byte
    return MeterReading(
        levels_db=tuple(levels),
        clip=tuple(lv is not None and lv >= profile.meter_clip_db for lv in levels),
        limit=tail_bits(profile.meter_tail_limit_byte),
        comp=tail_bits(profile.meter_tail_comp_byte),
        input_clip_flag=None if clip_index is None else bool(tail[clip_index]),
    )


def encode_meters(
    levels_db: list[float | None],
    profile: ProtocolProfile,
    *,
    limit: list[bool] | None = None,
    comp: list[bool] | None = None,
) -> bytes:
    """Build the data of a meter frame (used by the simulator)."""
    if len(levels_db) != profile.channel_count:
        raise MeterError(f"need {profile.channel_count} levels, got {len(levels_db)}")
    body = b"".join(
        _encode_triplet(None if db is None else _db_to_linear(db, profile), profile)
        for db in levels_db
    )
    tail = bytearray(profile.meter_tail_length)

    def put_bits(index: int | None, flags: list[bool] | None) -> None:
        if index is not None and flags is not None:
            tail[index] = sum(1 << i for i, on in enumerate(flags[: profile.output_count]) if on)

    put_bits(profile.meter_tail_limit_byte, limit)
    put_bits(profile.meter_tail_comp_byte, comp)
    if profile.meter_tail_clip_byte is not None:
        inputs = levels_db[: profile.input_count]
        tail[profile.meter_tail_clip_byte] = int(
            any(db is not None and db >= profile.meter_clip_db for db in inputs)
        )
    return body + bytes(tail)
