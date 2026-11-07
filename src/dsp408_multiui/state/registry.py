"""Parameter registry: path + physical value → validated, quantised device write.

``resolve`` never trusts the client: it validates the path and the value type, clamps and
quantises through the codecs, and returns the request to send plus the state changes to apply
once the device has acknowledged it (with the values the device will actually use).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from dsp408_multiui.protocol import codecs as c
from dsp408_multiui.protocol import commands as cmd
from dsp408_multiui.protocol.profile import ProtocolProfile
from dsp408_multiui.state.models import (
    Channel,
    Compressor,
    DeviceState,
    Filter,
    Gate,
    InputChannel,
    Limiter,
    OutputChannel,
    PeqBand,
)

# Parameter kinds whose encoding has been seen working on a real DSP 408 (dsp-408-ui).
HARDWARE_VERIFIED = frozenset({"gain_db", "mute", "matrix", "geq"})


class ParamError(ValueError):
    """Invalid path or value."""


@dataclass(frozen=True, slots=True)
class Write:
    request: cmd.Request
    changes: tuple[tuple[str, Any], ...]  # (path, JSON value) to apply after the ACK
    kind: str

    @property
    def hardware_verified(self) -> bool:
        return self.kind in HARDWARE_VERIFIED


def _index(segment: str, size: int, what: str) -> int:
    if not segment.isdigit() or int(segment) >= size:
        raise ParamError(f"{what} index out of range: {segment!r}")
    return int(segment)


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ParamError(f"expected a number, got {value!r}")
    if not math.isfinite(value):
        raise ParamError(f"value must be finite, got {value!r}")
    return float(value)


def _bool(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ParamError(f"expected true/false, got {value!r}")
    return value


def _merge[M: BaseModel](current: M, value: Any) -> M:
    """Merge a partial dict into a model and validate the result."""
    if not isinstance(value, dict):
        raise ParamError(f"expected an object, got {value!r}")
    try:
        return type(current).model_validate({**current.model_dump(), **value})
    except ValidationError as exc:
        raise ParamError(exc.errors()[0]["msg"]) from exc


def _check_choice(value: int, choices: tuple[str, ...], what: str, *, first: int = 0) -> None:
    if not first <= value < len(choices):
        raise ParamError(f"{what} must be in {first}..{len(choices) - 1}")


def resolve(path: str, value: Any, state: DeviceState, profile: ProtocolProfile) -> Write:
    parts = path.split(".")
    if len(parts) < 3 or parts[0] not in ("inputs", "outputs"):
        raise ParamError(f"unknown parameter path: {path!r}")
    group = state.inputs if parts[0] == "inputs" else state.outputs
    channel: Channel = group[_index(parts[1], len(group), "channel")]
    ch = channel.index
    field, rest = parts[2], parts[3:]

    def done(request: cmd.Request, new_value: Any, kind: str | None = None) -> Write:
        return Write(request, ((path, new_value),), kind or field)

    if rest and field not in ("peq", "geq", "crossover"):
        raise ParamError(f"unknown parameter path: {path!r}")

    match field:
        case "gain_db":
            raw = c.gain_db_to_raw(_number(value))
            return done(cmd.SetGain(ch, raw), c.gain_raw_to_db(raw))
        case "mute":
            return done(cmd.SetMute(ch, _bool(value)), value)
        case "phase":
            return done(cmd.SetPhase(ch, _bool(value)), value)
        case "peq_bypass":
            return done(cmd.SetPeqBypass(ch, _bool(value)), value)
        case "name":
            if not isinstance(value, str):
                raise ParamError("name must be a string")
            try:
                c.validate_name(value, c.CHANNEL_NAME_LENGTH)
            except ValueError as exc:
                raise ParamError(str(exc)) from exc
            return done(cmd.SetChannelName(ch, value), value)
        case "delay_ms" if isinstance(channel, OutputChannel):
            raw = c.delay_ms_to_raw(_number(value), profile)
            return done(cmd.SetDelay(ch, raw), round(c.delay_raw_to_ms(raw, profile), 3))
        case "matrix" if isinstance(channel, OutputChannel):
            if (
                not isinstance(value, list)
                or len(value) != profile.input_count
                or not all(isinstance(v, bool) for v in value)
            ):
                raise ParamError(f"matrix must be a list of {profile.input_count} booleans")
            mask = sum(1 << i for i, on in enumerate(value) if on)
            return done(cmd.SetMatrix(ch, mask), list(value))
        case "peq" if len(rest) == 1:
            n = _index(rest[0], len(channel.peq), "PEQ band")
            band = _merge(channel.peq[n], value)
            _check_choice(band.type, profile.peq_types, "PEQ type")
            gain = c.eq_gain_db_to_raw(band.gain_db)
            freq = c.freq_hz_to_raw(band.freq_hz, profile)
            q = c.q_to_raw(band.q, profile)
            quantised = PeqBand(
                gain_db=c.eq_gain_raw_to_db(gain),
                freq_hz=round(c.freq_raw_to_hz(freq, profile), 2),
                q=round(c.q_raw_to_q(q, profile), 3),
                type=band.type,
                bypass=band.bypass,
            )
            request = cmd.SetPeqBand(ch, n, gain, freq, q, band.type, band.bypass)
            return done(request, quantised.model_dump(), "peq")
        case "crossover" if len(rest) == 1 and rest[0] in ("hpf", "lpf"):
            current: Filter = getattr(channel.crossover, rest[0])
            flt = _merge(current, value)
            _check_choice(flt.slope, profile.slopes, "slope", first=1)
            freq = c.freq_hz_to_raw(flt.freq_hz, profile)
            slope = flt.slope if flt.enabled else 0
            kind = cmd.SetHighPass if rest[0] == "hpf" else cmd.SetLowPass
            quantised_filter = Filter(
                freq_hz=round(c.freq_raw_to_hz(freq, profile), 2),
                slope=flt.slope,
                enabled=flt.enabled,
            )
            return done(kind(ch, freq, slope), quantised_filter.model_dump(), "crossover")
        case "geq" if isinstance(channel, InputChannel) and len(rest) == 1:
            n = _index(rest[0], len(channel.geq), "GEQ band")
            raw = c.eq_gain_db_to_raw(_number(value))
            return done(cmd.SetGeqBand(ch, n, raw), c.eq_gain_raw_to_db(raw))
        case "gate" if isinstance(channel, InputChannel):
            g = _merge(channel.gate, value)
            request_gate = cmd.SetGate(
                ch,
                c.time_ms_to_raw(g.attack_ms, *c.ATTACK_RANGE_MS),
                c.time_ms_to_raw(g.release_ms, *c.GATE_RELEASE_RANGE_MS),
                c.time_ms_to_raw(g.hold_ms, *c.HOLD_RANGE_MS),
                c.threshold_db_to_raw(g.threshold_db, c.GATE_THRESHOLD_MAX_DB),
            )
            quantised_gate = Gate(
                attack_ms=c.time_raw_to_ms(request_gate.attack),
                release_ms=c.time_raw_to_ms(request_gate.release),
                hold_ms=c.time_raw_to_ms(request_gate.hold),
                threshold_db=c.threshold_raw_to_db(request_gate.threshold),
            )
            return done(request_gate, quantised_gate.model_dump())
        case "compressor" if isinstance(channel, OutputChannel):
            k = _merge(channel.compressor, value)
            request_comp = cmd.SetCompressor(
                ch,
                k.ratio,
                c.time_ms_to_raw(k.attack_ms, *c.ATTACK_RANGE_MS),
                c.time_ms_to_raw(k.release_ms, *c.RELEASE_RANGE_MS),
                k.knee_db,
                c.threshold_db_to_raw(k.threshold_db),
            )
            quantised_comp = Compressor(
                ratio=k.ratio,
                attack_ms=c.time_raw_to_ms(request_comp.attack),
                release_ms=c.time_raw_to_ms(request_comp.release),
                knee_db=k.knee_db,
                threshold_db=c.threshold_raw_to_db(request_comp.threshold),
            )
            return done(request_comp, quantised_comp.model_dump())
        case "limiter" if isinstance(channel, OutputChannel):
            lim = _merge(channel.limiter, value)
            request_lim = cmd.SetLimiter(
                ch,
                c.time_ms_to_raw(lim.attack_ms, *c.ATTACK_RANGE_MS),
                c.time_ms_to_raw(lim.release_ms, *c.RELEASE_RANGE_MS),
                0,
                c.threshold_db_to_raw(lim.threshold_db),
            )
            quantised_lim = Limiter(
                attack_ms=c.time_raw_to_ms(request_lim.attack),
                release_ms=c.time_raw_to_ms(request_lim.release),
                threshold_db=c.threshold_raw_to_db(request_lim.threshold),
            )
            return done(request_lim, quantised_lim.model_dump())
    raise ParamError(f"unknown parameter path: {path!r}")
