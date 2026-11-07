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


def peq_band(raw: cm.RawPeqBand, bypass: bool, profile: ProtocolProfile) -> PeqBand:
    return PeqBand(
        gain_db=c.eq_gain_raw_to_db(raw.gain),
        freq_hz=round(c.freq_raw_to_hz(raw.freq, profile), 2),
        q=round(c.q_raw_to_q(raw.q, profile), 3),
        type=raw.type,
        bypass=bypass,
    )


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
    peq_band_bypass: dict[tuple[int, int], bool] | None = None,
    peq_channel_bypass: dict[int, bool] | None = None,
) -> DeviceState:
    """Build the state from a config read.

    Band/channel PEQ bypass is not part of the blob; it comes from ``previous`` (what we last
    wrote) unless given explicitly.
    """
    band_bypass = dict(peq_band_bypass or {})
    chan_bypass = dict(peq_channel_bypass or {})
    if previous is not None:
        for prev_ch in [*previous.inputs, *previous.outputs]:
            chan_bypass.setdefault(prev_ch.index, prev_ch.peq_bypass)
            for b, band in enumerate(prev_ch.peq):
                band_bypass.setdefault((prev_ch.index, b), band.bypass)

    def prev_input(i: int) -> InputChannel | None:
        return previous.inputs[i] if previous and i < len(previous.inputs) else None

    def prev_output(i: int) -> OutputChannel | None:
        return previous.outputs[i] if previous and i < len(previous.outputs) else None

    inputs = []
    for i, raw_in in enumerate(raw.inputs):
        idx = i
        prev = prev_input(i)
        inputs.append(
            InputChannel(
                index=idx,
                name=raw_in.name,
                gain_db=c.gain_raw_to_db(raw_in.gain),
                mute=raw_in.mute,
                phase=raw_in.phase,
                peq=[
                    peq_band(b, band_bypass.get((idx, n), False), profile)
                    for n, b in enumerate(raw_in.peq)
                ],
                peq_bypass=chan_bypass.get(idx, False),
                crossover=crossover(raw_in.crossover, profile, prev.crossover if prev else None),
                geq=[c.eq_gain_raw_to_db(v) for v in raw_in.geq],
                gate=gate(raw_in.gate),
            )
        )
    outputs = []
    for i, raw_out in enumerate(raw.outputs):
        idx = profile.input_count + i
        prev_out = prev_output(i)
        outputs.append(
            OutputChannel(
                index=idx,
                name=raw_out.name,
                gain_db=c.gain_raw_to_db(raw_out.gain),
                mute=raw_out.mute,
                phase=raw_out.phase,
                delay_ms=round(c.delay_raw_to_ms(raw_out.delay, profile), 3),
                matrix=[bool(raw_out.matrix >> n & 1) for n in range(profile.input_count)],
                crosspoints_db=[c.gain_raw_to_db(v) for v in raw_out.crosspoints],
                peq=[
                    peq_band(b, band_bypass.get((idx, n), False), profile)
                    for n, b in enumerate(raw_out.peq)
                ],
                peq_bypass=chan_bypass.get(idx, False),
                crossover=crossover(
                    raw_out.crossover, profile, prev_out.crossover if prev_out else None
                ),
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
