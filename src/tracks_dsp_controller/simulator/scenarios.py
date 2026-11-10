"""Named simulator setups (``tracks-dsp-sim --scenario NAME``, ``serve --demo-scenario NAME``)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from tracks_dsp_controller.protocol import config_map as cm
from tracks_dsp_controller.protocol.codecs import (
    freq_hz_to_raw,
    gain_db_to_raw,
    threshold_db_to_raw,
)
from tracks_dsp_controller.simulator.device import SimulatedDevice
from tracks_dsp_controller.simulator.faults import Faults
from tracks_dsp_controller.simulator.meters import Shape, Source

THREE_WAY = [("Sub", 25, 90, 8, 10), ("LoMid", 90, 1200, 10, 10), ("High", 1200, 20000, 10, 0)]
TWO_WAY = [("Sub", 25, 90, 8, 10), ("Top", 90, 20000, 10, 0)]


def _system_name(device: SimulatedDevice) -> str:
    return "Demo 3-way" if device.layout.outputs >= 6 else "Demo 2-way"


def _system(name: str, device: SimulatedDevice) -> cm.RawConfig:
    """A stereo system on In A/B: 3-way on Out1-6 (sub, low-mid, high), or 2-way on Out1-4 for a
    4-output model. On a 4 x 8 model, Out7/8 are monitors fed by In C/D."""
    p = device.profile
    base = cm.default_config(name, device.layout)
    bands = THREE_WAY if device.layout.outputs >= 6 else TWO_WAY
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
    if device.layout.outputs >= 8 and device.layout.inputs >= 4:
        outputs[6] = replace(outputs[6], name="MonL", matrix=0b0100)
        outputs[7] = replace(outputs[7], name="MonR", matrix=0b1000, gain=gain_db_to_raw(-6.0))
    config = replace(base, marker=cm.MARKER_MODIFIED, outputs=tuple(outputs))
    return replace(config, image=cm.encode_config(config))


def demo(device: SimulatedDevice, faults: Faults) -> None:
    """Music-like signals, a few named user presets, U01 active."""
    device.set_preset(1, _system(_system_name(device), device))
    mono = replace(cm.default_config("Mono Sub", device.layout), marker=cm.MARKER_MODIFIED)
    device.set_preset(2, replace(mono, image=cm.encode_config(mono)))
    device.load(1)
    if device.layout.inputs >= 4:
        device.meters.sources[2] = Source(Shape.STEADY, -30.0)
        device.meters.sources[3] = Source(Shape.SILENCE)


def silent(device: SimulatedDevice, faults: Faults) -> None:
    """Factory state, no signal."""
    for src in device.meters.sources:
        src.shape = Shape.SILENCE


def clipping(device: SimulatedDevice, faults: Faults) -> None:
    """Hot signal on In A: input clip, limiter active on the outputs it feeds."""
    demo(device, faults)
    device.meters.sources[0] = Source(Shape.STEADY, 24.0)  # above full scale (+20 dB)


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
