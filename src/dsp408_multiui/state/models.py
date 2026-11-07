"""Device state in physical units, as sent to clients (docs/SPEC.md §4.2).

Every parameter has a **path**: the dotted JSON location of the value in this model, e.g.
``outputs.2.gain_db``, ``inputs.0.peq.3`` (a whole band) or ``outputs.5.crossover.hpf``.
Clients write with these paths and apply patches with them, so client and server share one
addressing scheme.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")


class PeqBand(_Model):
    gain_db: float = Field(0.0, ge=-12.0, le=12.0)
    freq_hz: float = Field(1000.0, gt=0)
    q: float = Field(1.0, gt=0)
    type: int = Field(0, ge=0)
    bypass: bool = False


class Filter(_Model):
    """One crossover filter. ``slope`` is the remembered slope; ``enabled`` False = bypass."""

    freq_hz: float = Field(1000.0, gt=0)
    slope: int = Field(10, ge=1)  # index into profile.slopes (0 = "Off" is never stored here)
    enabled: bool = False


class Crossover(_Model):
    hpf: Filter = Field(default_factory=lambda: Filter(freq_hz=19.7))
    lpf: Filter = Field(default_factory=lambda: Filter(freq_hz=20160.0))


class Gate(_Model):
    attack_ms: float = Field(1.0, ge=1.0, le=999.0)
    release_ms: float = Field(100.0, ge=1.0, le=3000.0)
    hold_ms: float = Field(100.0, ge=10.0, le=999.0)
    threshold_db: float = Field(-90.0, ge=-90.0, le=0.0)


class Compressor(_Model):
    ratio: int = Field(0, ge=0, le=15)  # index into codecs.COMPRESSOR_RATIOS
    attack_ms: float = Field(50.0, ge=1.0, le=999.0)
    release_ms: float = Field(500.0, ge=10.0, le=3000.0)
    knee_db: int = Field(0, ge=0, le=12)
    threshold_db: float = Field(20.0, ge=-90.0, le=20.0)


class Limiter(_Model):
    attack_ms: float = Field(50.0, ge=1.0, le=999.0)
    release_ms: float = Field(500.0, ge=10.0, le=3000.0)
    threshold_db: float = Field(20.0, ge=-90.0, le=20.0)


class Channel(_Model):
    index: int  # protocol channel index (inputs 0-3, outputs 4-11)
    name: str
    gain_db: float = Field(0.0, ge=-60.0, le=12.0)
    mute: bool = False
    phase: bool = False
    peq: list[PeqBand]
    peq_bypass: bool = False
    crossover: Crossover = Field(default_factory=Crossover)


class InputChannel(Channel):
    geq: list[float]
    gate: Gate = Field(default_factory=Gate)


class OutputChannel(Channel):
    delay_ms: float = Field(0.0, ge=0.0)
    matrix: list[bool]  # one flag per input
    crosspoints_db: list[float]  # one gain per input (read-only for now)
    compressor: Compressor = Field(default_factory=Compressor)
    limiter: Limiter = Field(default_factory=Limiter)


class Preset(_Model):
    slot: int  # 1 = U01
    name: str


class DeviceInfo(_Model):
    identity: str = ""
    model: str = ""
    firmware: str = ""


class DeviceState(_Model):
    info: DeviceInfo = Field(default_factory=DeviceInfo)
    presets: list[Preset] = Field(default_factory=list)
    active_slot: int = 0  # 0 = F00
    preset_name: str = ""
    inputs: list[InputChannel] = Field(default_factory=list)
    outputs: list[OutputChannel] = Field(default_factory=list)
