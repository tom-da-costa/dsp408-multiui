"""Synthetic meters that follow the simulated device's parameters.

Each input has a signal source (a level in dB relative to the meter reference, plus a shape).
Levels then go through the live config: input gain and mute, the routing matrix (power sum of
the routed inputs plus crosspoint gain), output gain and mute. Limiter and compressor activity
is raised when an output exceeds the corresponding threshold.
"""

from __future__ import annotations

import math
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from tracks_dsp_controller.protocol import config_map as cm
from tracks_dsp_controller.protocol.codecs import gain_raw_to_db, threshold_raw_to_db
from tracks_dsp_controller.protocol.meters import encode_meters
from tracks_dsp_controller.protocol.profile import ProtocolProfile


class Shape(StrEnum):
    SILENCE = "silence"
    STEADY = "steady"
    MUSIC = "music"  # slow sine modulation plus jitter
    NOISE = "noise"  # random level around the base


@dataclass(slots=True)
class Source:
    shape: Shape = Shape.MUSIC
    level_db: float = -18.0
    depth_db: float = 9.0  # modulation depth for MUSIC / NOISE
    period_s: float = 4.0


@dataclass
class MeterSimulator:
    profile: ProtocolProfile
    clock: Callable[[], float] | None = None
    seed: int = 408
    sources: list[Source] = field(init=False)
    nan_next: bool = field(init=False, default=False)  # next frame reports "no data"
    _rng: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.sources = [
            Source(period_s=3.0 + i, level_db=-18.0 - 2 * i)
            for i in range(self.profile.input_count)
        ]
        self._rng = random.Random(self.seed)

    def _now(self) -> float:
        return (self.clock or time.monotonic)()

    def source_level(self, index: int, now: float) -> float | None:
        src = self.sources[index]
        if src.shape is Shape.SILENCE:
            return None
        if src.shape is Shape.STEADY:
            return src.level_db
        if src.shape is Shape.MUSIC:
            phase = 2 * math.pi * now / src.period_s + index
            return src.level_db + src.depth_db * math.sin(phase) + self._rng.uniform(-1.5, 1.5)
        return src.level_db + self._rng.uniform(-src.depth_db, src.depth_db)

    def levels(self, config: cm.RawConfig) -> tuple[list[float | None], list[bool], list[bool]]:
        """Return (levels_db per channel, limiter active per output, compressor active per output).

        ``None`` here means silence; it is rendered at the meter floor.
        """
        now = self._now()
        inputs: list[float | None] = []
        for i, ch in enumerate(config.inputs):
            level = self.source_level(i, now)
            inputs.append(None if level is None or ch.mute else level + gain_raw_to_db(ch.gain))
        outputs: list[float | None] = []
        limit: list[bool] = []
        comp: list[bool] = []
        for out in config.outputs:
            power = 0.0
            for i, level in enumerate(inputs):
                if level is not None and out.matrix >> i & 1:
                    power += 10 ** ((level + gain_raw_to_db(out.crosspoints[i])) / 10)
            level_out = (
                None
                if power == 0.0 or out.mute
                else 10 * math.log10(power) + gain_raw_to_db(out.gain)
            )
            outputs.append(level_out)
            limit.append(
                level_out is not None and level_out > threshold_raw_to_db(out.limiter.threshold)
            )
            comp.append(
                level_out is not None
                and out.compressor.ratio > 0
                and level_out > threshold_raw_to_db(out.compressor.threshold)
            )
        return inputs + outputs, limit, comp

    def render(self, config: cm.RawConfig) -> bytes:
        """Meter frame data (without the opcode) for the live config."""
        levels, limit, comp = self.levels(config)
        floor = self.profile.meter_floor_db
        rendered: list[float | None] = [floor if lv is None else lv for lv in levels]
        if self.nan_next:
            self.nan_next = False
            rendered = [None] * len(rendered)
        return encode_meters(rendered, self.profile, limit=limit, comp=comp)
