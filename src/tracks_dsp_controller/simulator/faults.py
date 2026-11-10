"""Fault injection for the simulator server."""

from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass
class Faults:
    """Faults applied by the server to each request. All off by default.

    The attributes can be changed while the server runs (tests do this).
    """

    extra_latency_s: float = 0.0
    drop_rate: float = 0.0  # probability that a response is not sent
    corrupt_rate: float = 0.0  # probability that a response has a bad checksum
    nan_meter_rate: float = 0.0  # probability that a meter frame reports "no data"
    disconnect_after: int | None = None  # close the connection after N requests
    seed: int = 9761
    _rng: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        for name in ("drop_rate", "corrupt_rate", "nan_meter_rate"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be within 0..1")
        if self.extra_latency_s < 0:
            raise ValueError("extra_latency_s must be >= 0")
        self._rng = random.Random(self.seed)

    def roll(self, rate: float) -> bool:
        return rate > 0 and self._rng.random() < rate
