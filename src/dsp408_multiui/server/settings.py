"""Server configuration (from the CLI / environment) and live settings."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_PIN = "0000"


@dataclass
class ServerConfig:
    dsp_host: str | None = None
    dsp_port: int = 9761
    host: str = "0.0.0.0"
    port: int = 8080
    pin: str = DEFAULT_PIN
    meter_rate_hz: float = 5.0
    lock_idle_timeout_s: float = 120.0
    resync_interval_s: float = 0.0  # 0 = off
    command_timeout_s: float | None = None
    experimental: bool = False
    simulator: bool = False
    scenario: str = "demo"

    def __post_init__(self) -> None:
        if not self.simulator and not self.dsp_host:
            raise ValueError("--dsp-host is required (or use --simulator)")
        if not self.pin:
            raise ValueError("the access code must not be empty")
        if self.lock_idle_timeout_s <= 0:
            raise ValueError("--lock-idle-timeout must be > 0")
        if self.resync_interval_s < 0:
            raise ValueError("--resync-interval must be >= 0")

    @property
    def allow_unverified(self) -> bool:
        """Unverified parameters are allowed against the simulator or with --experimental."""
        return self.simulator or self.experimental
