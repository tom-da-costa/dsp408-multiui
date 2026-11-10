"""Conversions between physical values and raw protocol values (docs/PROTOCOL.md §4).

Every ``*_to_raw`` function **clamps** to the valid range and snaps to the device's step, so a
caller can never produce an out-of-range raw value. Use ``quantize_*`` to show users the value
that will actually be applied.
"""

from __future__ import annotations

import math

from tracks_dsp_controller.protocol.profile import DEFAULT_PROFILE, ProtocolProfile


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _check_finite(value: float) -> None:
    if not math.isfinite(value):
        raise ValueError(f"value must be finite, got {value!r}")


# --- channel gain (0x34): two segments ------------------------------------------------------
GAIN_MIN_DB = -60.0
GAIN_MAX_DB = 12.0
GAIN_RAW_MAX = 400
_GAIN_BREAK_DB = -20.0
_GAIN_BREAK_RAW = 80


def gain_db_to_raw(db: float) -> int:
    """-60..-20 dB in 0.5 dB steps (raw 0..80), -20..+12 dB in 0.1 dB steps (raw 80..400)."""
    _check_finite(db)
    db = _clamp(db, GAIN_MIN_DB, GAIN_MAX_DB)
    if db < _GAIN_BREAK_DB:
        raw = round((db - GAIN_MIN_DB) * 2)
    else:
        raw = round(_GAIN_BREAK_RAW + (db - _GAIN_BREAK_DB) * 10)
    return int(_clamp(raw, 0, GAIN_RAW_MAX))


def gain_raw_to_db(raw: int) -> float:
    raw = int(_clamp(raw, 0, GAIN_RAW_MAX))
    if raw < _GAIN_BREAK_RAW:
        return raw / 2 + GAIN_MIN_DB
    return round((raw - _GAIN_BREAK_RAW) / 10 + _GAIN_BREAK_DB, 1)


def quantize_gain(db: float) -> float:
    return gain_raw_to_db(gain_db_to_raw(db))


# --- EQ gain (PEQ / GEQ) --------------------------------------------------------------------
EQ_GAIN_MIN_DB = -12.0
EQ_GAIN_MAX_DB = 12.0
EQ_GAIN_RAW_MAX = 240
_EQ_GAIN_ZERO = 120


def eq_gain_db_to_raw(db: float) -> int:
    _check_finite(db)
    return int(_clamp(round(db * 10 + _EQ_GAIN_ZERO), 0, EQ_GAIN_RAW_MAX))


def eq_gain_raw_to_db(raw: int) -> float:
    return round((_clamp(raw, 0, EQ_GAIN_RAW_MAX) - _EQ_GAIN_ZERO) / 10, 1)


# --- frequency (PEQ, HPF, LPF): logarithmic --------------------------------------------------
def freq_hz_to_raw(hz: float, profile: ProtocolProfile = DEFAULT_PROFILE) -> int:
    _check_finite(hz)
    lo, hi, steps = profile.freq_min_hz, profile.freq_max_hz, profile.freq_steps
    hz = _clamp(hz, lo, hi)
    return int(_clamp(round(math.log(hz / lo) / math.log(hi / lo) * steps), 0, steps))


def freq_raw_to_hz(raw: int, profile: ProtocolProfile = DEFAULT_PROFILE) -> float:
    lo, hi, steps = profile.freq_min_hz, profile.freq_max_hz, profile.freq_steps
    raw = int(_clamp(raw, 0, steps))
    return float(lo * (hi / lo) ** (raw / steps))


# --- PEQ Q: logarithmic ----------------------------------------------------------------------
def q_to_raw(q: float, profile: ProtocolProfile = DEFAULT_PROFILE) -> int:
    _check_finite(q)
    lo, hi, steps = profile.q_min, profile.q_max, profile.q_steps
    q = _clamp(q, lo, hi)
    return int(_clamp(round(math.log(q / lo) / math.log(hi / lo) * steps), 0, steps))


def q_raw_to_q(raw: int, profile: ProtocolProfile = DEFAULT_PROFILE) -> float:
    lo, hi, steps = profile.q_min, profile.q_max, profile.q_steps
    raw = int(_clamp(raw, 0, steps))
    return float(lo * (hi / lo) ** (raw / steps))


# --- dynamics thresholds: 0.5 dB steps from -90 dB -------------------------------------------
THRESHOLD_MIN_DB = -90.0
GATE_THRESHOLD_MAX_DB = 0.0
DYNAMICS_THRESHOLD_MAX_DB = 20.0


def threshold_db_to_raw(db: float, max_db: float = DYNAMICS_THRESHOLD_MAX_DB) -> int:
    _check_finite(db)
    db = _clamp(db, THRESHOLD_MIN_DB, max_db)
    return round((db - THRESHOLD_MIN_DB) * 2)


def threshold_raw_to_db(raw: int) -> float:
    return max(0, raw) / 2 + THRESHOLD_MIN_DB


# --- attack / release / hold: ms = raw + 1 ---------------------------------------------------
def time_ms_to_raw(ms: float, min_ms: float = 1.0, max_ms: float = 3000.0) -> int:
    _check_finite(ms)
    return round(_clamp(ms, min_ms, max_ms)) - 1


def time_raw_to_ms(raw: int) -> float:
    return float(max(0, raw) + 1)


ATTACK_RANGE_MS = (1.0, 999.0)
RELEASE_RANGE_MS = (10.0, 3000.0)
HOLD_RANGE_MS = (10.0, 999.0)
GATE_RELEASE_RANGE_MS = (1.0, 3000.0)

KNEE_MAX_DB = 12

COMPRESSOR_RATIOS: tuple[str, ...] = (
    "1:1",
    "1:1.1",
    "1:1.3",
    "1:1.5",
    "1:1.7",
    "1:2",
    "1:2.5",
    "1:3",
    "1:3.5",
    "1:4",
    "1:5",
    "1:6",
    "1:8",
    "1:10",
    "1:20",
    "Limit",
)


# --- delay: samples ----------------------------------------------------------------------------
def delay_ms_to_raw(ms: float, profile: ProtocolProfile = DEFAULT_PROFILE) -> int:
    _check_finite(ms)
    ms = _clamp(ms, 0.0, profile.delay_max_ms)
    return int(_clamp(round(ms * profile.delay_sample_rate_hz / 1000), 0, 0xFFFF))


def delay_raw_to_ms(raw: int, profile: ProtocolProfile = DEFAULT_PROFILE) -> float:
    return max(0, raw) * 1000 / profile.delay_sample_rate_hz


SPEED_OF_SOUND_M_S = 343.0


def delay_ms_to_m(ms: float) -> float:
    """Distance equivalent of a delay, for display only."""
    return ms / 1000 * SPEED_OF_SOUND_M_S


# --- names ----------------------------------------------------------------------------------
CHANNEL_NAME_LENGTH = 8
PRESET_NAME_LENGTH = 14


def validate_name(name: str, max_length: int) -> str:
    """Return ``name`` if it is printable ASCII and short enough, else raise ``ValueError``.

    Never truncate silently: a preset name longer than 14 characters can crash the firmware,
    and the caller must know that the name was rejected.
    """
    if len(name) > max_length:
        raise ValueError(f"name longer than {max_length} characters: {name!r}")
    if not all(0x20 <= ord(c) < 0x7F for c in name):
        raise ValueError(f"name must be printable ASCII: {name!r}")
    return name


def encode_name(name: str, length: int, pad: bytes = b"\x00") -> bytes:
    validate_name(name, length)
    return name.encode("ascii").ljust(length, pad)


def decode_name(raw: bytes) -> str:
    """Decode a stored name. The official editor writes Latin-1 (e.g. ``e9`` = é)."""
    text = raw.split(b"\x00", 1)[0].decode("latin-1")
    return "".join(c if c.isprintable() else "?" for c in text).rstrip()


def encode_stored_name(name: str, length: int, pad: bytes = b"\x00") -> bytes:
    """Encode a name read from the device back into a config image (Latin-1, not validated).

    Only for round-tripping what the device already holds; names written by clients go
    through ``encode_name`` (printable ASCII only).
    """
    return name.encode("latin-1", errors="replace")[:length].ljust(length, pad)
