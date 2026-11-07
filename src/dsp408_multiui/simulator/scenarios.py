"""Named simulator setups (``dsp408-multiui simulate --scenario NAME``)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from dsp408_multiui.protocol import config_map as cm
from dsp408_multiui.protocol.codecs import freq_hz_to_raw, gain_db_to_raw, threshold_db_to_raw
from dsp408_multiui.simulator.device import SimulatedDevice
from dsp408_multiui.simulator.faults import Faults
from dsp408_multiui.simulator.meters import Shape, Source


def _three_way(name: str, device: SimulatedDevice) -> cm.RawConfig:
    """A stereo 3-way system: In A/B -> sub (Out1/2), low-mid (Out3/4), high (Out5/6)."""
    p = device.profile
    base = cm.default_config(name)
    bands = [("Sub", 25, 90, 8, 10), ("LoMid", 90, 1200, 10, 10), ("High", 1200, 20000, 10, 0)]
    outputs = list(base.outputs)
    for i, (label, hpf, lpf, hpf_slope, lpf_slope) in enumerate(bands):
        for side in (0, 1):
            idx = 2 * i + side
            outputs[idx] = replace(
                outputs[idx],
                name=f"{label}{'LR'[side]}"[:8],
                matrix=1 << side,
                crossover=cm.RawCrossover(
                    freq_hz_to_raw(hpf, p), freq_hz_to_raw(lpf, p), hpf_slope, lpf_slope
                ),
                limiter=replace(outputs[idx].limiter, threshold=threshold_db_to_raw(0.0)),
            )
    outputs[6] = replace(outputs[6], name="MonL", matrix=0b0100)
    outputs[7] = replace(outputs[7], name="MonR", matrix=0b1000, gain=gain_db_to_raw(-6.0))
    config = replace(base, marker=cm.MARKER_MODIFIED, outputs=tuple(outputs))
    return replace(config, image=cm.encode_config(config))


def demo(device: SimulatedDevice, faults: Faults) -> None:
    """Music-like signals, a few named user presets, U01 active."""
    device.set_preset(1, _three_way("Demo 3-way", device))
    mono = replace(cm.default_config("Mono Sub"), marker=cm.MARKER_MODIFIED)
    device.set_preset(2, replace(mono, image=cm.encode_config(mono)))
    device.load(1)
    device.meters.sources[2] = Source(Shape.STEADY, -30.0)
    device.meters.sources[3] = Source(Shape.SILENCE)


def silent(device: SimulatedDevice, faults: Faults) -> None:
    """Factory state, no signal."""
    for src in device.meters.sources:
        src.shape = Shape.SILENCE


def clipping(device: SimulatedDevice, faults: Faults) -> None:
    """Hot signal on In A: input clip, limiter active on the outputs it feeds."""
    demo(device, faults)
    device.meters.sources[0] = Source(Shape.STEADY, 8.0)


def stress(device: SimulatedDevice, faults: Faults) -> None:
    """Demo plus latency, dropped and corrupt responses, NaN meter frames."""
    demo(device, faults)
    faults.extra_latency_s = 0.02
    faults.drop_rate = 0.05
    faults.corrupt_rate = 0.02
    faults.nan_meter_rate = 0.05


SCENARIOS: dict[str, Callable[[SimulatedDevice, Faults], None]] = {
    "demo": demo,
    "silent": silent,
    "clipping": clipping,
    "stress": stress,
}


def apply_scenario(name: str, device: SimulatedDevice, faults: Faults) -> None:
    try:
        SCENARIOS[name](device, faults)
    except KeyError:
        raise ValueError(f"unknown scenario {name!r}; choose from {sorted(SCENARIOS)}") from None
