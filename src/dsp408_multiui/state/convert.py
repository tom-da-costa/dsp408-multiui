"""Raw protocol config → physical-unit state."""

from __future__ import annotations

from dsp408_multiui.protocol import codecs as c
from dsp408_multiui.protocol import config_map as cm
from dsp408_multiui.protocol.profile import ProtocolProfile
from dsp408_multiui.state.models import (
    Compressor,
    Crossover,
    DeviceInfo,
    DeviceState,
    Filter,
    Gate,
    InputChannel,
    Limiter,
    OutputChannel,
    PeqBand,
    Preset,
)

DEFAULT_SLOPE = 10  # LR-24, the device default when a filter is bypassed


def peq_band(raw: cm.RawPeqBand, profile: ProtocolProfile) -> PeqBand:
    return PeqBand(
        gain_db=c.eq_gain_raw_to_db(raw.gain),
        freq_hz=round(c.freq_raw_to_hz(raw.freq, profile), 2),
        q=round(c.q_raw_to_q(raw.q, profile), 3),
        type=raw.type,
        bypass=raw.bypass,
    )


def linked(masks: list[int], index: int) -> list[int]:
    return [m for m in cm.link_group(masks, index) if m != index]


def filter_from_raw(
    freq: int, slope: int, profile: ProtocolProfile, previous: Filter | None
) -> Filter:
    """Raw slope 0 means bypass; keep the previously remembered slope in that case."""
    remembered = previous.slope if previous is not None else DEFAULT_SLOPE
    return Filter(
        freq_hz=round(c.freq_raw_to_hz(freq, profile), 2),
        slope=slope or remembered,
        enabled=slope != 0,
    )


def crossover(
    raw: cm.RawCrossover, profile: ProtocolProfile, previous: Crossover | None
) -> Crossover:
    return Crossover(
        hpf=filter_from_raw(
            raw.hpf_freq, raw.hpf_slope, profile, previous.hpf if previous else None
        ),
        lpf=filter_from_raw(
            raw.lpf_freq, raw.lpf_slope, profile, previous.lpf if previous else None
        ),
    )


def gate(raw: cm.RawGate) -> Gate:
    return Gate(
        attack_ms=c.time_raw_to_ms(raw.attack),
        release_ms=c.time_raw_to_ms(raw.release),
        hold_ms=max(c.HOLD_RANGE_MS[0], c.time_raw_to_ms(raw.hold)),
        threshold_db=min(c.GATE_THRESHOLD_MAX_DB, c.threshold_raw_to_db(raw.threshold)),
    )


def compressor(raw: cm.RawCompressor) -> Compressor:
    return Compressor(
        ratio=min(raw.ratio, 15),
        attack_ms=min(999.0, c.time_raw_to_ms(raw.attack)),
        release_ms=max(10.0, min(3000.0, c.time_raw_to_ms(raw.release))),
        knee_db=min(raw.knee, c.KNEE_MAX_DB),
        threshold_db=min(c.DYNAMICS_THRESHOLD_MAX_DB, c.threshold_raw_to_db(raw.threshold)),
    )


def limiter(raw: cm.RawLimiter) -> Limiter:
    return Limiter(
        attack_ms=min(999.0, c.time_raw_to_ms(raw.attack)),
        release_ms=max(10.0, min(3000.0, c.time_raw_to_ms(raw.release))),
        threshold_db=min(c.DYNAMICS_THRESHOLD_MAX_DB, c.threshold_raw_to_db(raw.threshold)),
    )


def build_state(
    raw: cm.RawConfig,
    profile: ProtocolProfile,
    *,
    info: DeviceInfo,
    preset_names: list[str],
    active_slot: int,
    previous: DeviceState | None = None,
) -> DeviceState:
    """Build the state from a config read.

    ``previous`` only provides the remembered slope of bypassed filters (the device stores
    slope 0 for a bypassed filter).
    """

    def prev_input(i: int) -> InputChannel | None:
        return previous.inputs[i] if previous and i < len(previous.inputs) else None

    def prev_output(i: int) -> OutputChannel | None:
        return previous.outputs[i] if previous and i < len(previous.outputs) else None

    input_links = [ch.link for ch in raw.inputs]
    output_links = [ch.link for ch in raw.outputs]
    inputs = []
    for i, raw_in in enumerate(raw.inputs):
        prev = prev_input(i)
        inputs.append(
            InputChannel(
                index=i,
                name=raw_in.name,
                gain_db=c.gain_raw_to_db(raw_in.gain),
                mute=raw_in.mute,
                phase=raw_in.phase,
                delay_ms=round(c.delay_raw_to_ms(raw_in.delay, profile), 3),
                peq=[peq_band(b, profile) for b in raw_in.peq],
                peq_bypass=raw_in.peq_bypass,
                crossover=crossover(raw_in.crossover, profile, prev.crossover if prev else None),
                linked=linked(input_links, i),
                geq=[c.eq_gain_raw_to_db(v) for v in raw_in.geq],
                gate=gate(raw_in.gate),
            )
        )
    outputs = []
    for i, raw_out in enumerate(raw.outputs):
        prev_out = prev_output(i)
        outputs.append(
            OutputChannel(
                index=profile.input_count + i,
                name=raw_out.name,
                gain_db=c.gain_raw_to_db(raw_out.gain),
                mute=raw_out.mute,
                phase=raw_out.phase,
                delay_ms=round(c.delay_raw_to_ms(raw_out.delay, profile), 3),
                matrix=[bool(raw_out.matrix >> n & 1) for n in range(profile.input_count)],
                crosspoints_db=[c.gain_raw_to_db(v) for v in raw_out.crosspoints],
                peq=[peq_band(b, profile) for b in raw_out.peq],
                peq_bypass=raw_out.peq_bypass,
                crossover=crossover(
                    raw_out.crossover, profile, prev_out.crossover if prev_out else None
                ),
                linked=linked(output_links, i),
                compressor=compressor(raw_out.compressor),
                limiter=limiter(raw_out.limiter),
            )
        )
    return DeviceState(
        info=info,
        presets=[Preset(slot=i + 1, name=name) for i, name in enumerate(preset_names)],
        active_slot=active_slot,
        preset_name=raw.preset_name,
        inputs=inputs,
        outputs=outputs,
    )
