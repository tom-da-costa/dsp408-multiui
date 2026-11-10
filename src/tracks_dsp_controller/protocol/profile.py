"""Protocol profile: every uncertain protocol detail in one place (docs/ARCHITECTURE.md §6)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, fields, replace
from enum import StrEnum
from importlib import resources
from pathlib import Path
from typing import Any


class MeterFormat(StrEnum):
    FLOAT32 = "float32"  # DSP 408 (verified): top 3 bytes of a little-endian float32
    FLOAT16 = "float16"  # dsp-408-ui's reading; wrong on a real 408
    LEVEL24 = "level24"  # 4x4 Mini


class CompressorLayout(StrEnum):
    WIDE = "wide"  # 206: ratio(2) attack(2) release(2) knee(2) threshold(2)
    NARROW = "narrow"  # 4x4 Mini: ratio(1) knee(1) attack(2) release(2) threshold(2)


class ProfileError(ValueError):
    """Raised for an invalid or unknown profile setting."""


# TOML section -> field names, so that profile files stay readable.
_SECTIONS: dict[str, tuple[str, ...]] = {
    "frame": ("host_dst",),
    "topology": (
        "input_count",
        "output_count",
        "preset_count",
        "peq_bands_input",
        "peq_bands_output",
        "geq_bands",
    ),
    "config": ("page_count", "page_size", "last_page_size"),
    "codecs": (
        "freq_steps",
        "freq_min_hz",
        "freq_max_hz",
        "q_steps",
        "q_min",
        "q_max",
        "delay_sample_rate_hz",
        "delay_max_ms",
        "compressor_layout",
        "peq_types",
        "slopes",
    ),
    "meters": (
        "meter_format",
        "meter_tail_length",
        "meter_tail_limit_byte",
        "meter_tail_comp_byte",
        "meter_tail_clip_byte",
        "meter_reference",
        "meter_clip_db",
        "meter_floor_db",
    ),
    "timing": ("command_timeout_s", "slow_command_timeout_s"),
}
# Keys in the [meters] section drop the "meter_" prefix.
_PREFIXED_SECTIONS = {"meters": "meter_"}


@dataclass(frozen=True, slots=True)
class ProtocolProfile:
    name: str = "builtin"
    # frame
    host_dst: int = 0x01
    # topology
    input_count: int = 4
    output_count: int = 8
    preset_count: int = 20
    peq_bands_input: int = 8
    peq_bands_output: int = 9
    geq_bands: int = 31
    # config blob
    page_count: int = 29
    page_size: int = 50
    last_page_size: int = 48
    # codecs
    freq_steps: int = 300
    freq_min_hz: float = 19.70
    freq_max_hz: float = 20160.0
    q_steps: int = 100
    q_min: float = 0.4
    q_max: float = 128.0
    delay_sample_rate_hz: int = 96000
    delay_max_ms: float = 680.0
    compressor_layout: CompressorLayout = CompressorLayout.WIDE
    peq_types: tuple[str, ...] = ()
    slopes: tuple[str, ...] = ()
    # meters
    meter_format: MeterFormat = MeterFormat.FLOAT32
    meter_tail_length: int = 2
    meter_tail_limit_byte: int | None = 1
    meter_tail_comp_byte: int | None = 0
    meter_tail_clip_byte: int | None = None
    meter_reference: float = 0.1  # 0 dBu: full scale (1.0) = +20 dBu (PROTOCOL §6)
    meter_clip_db: float = 12.0  # CLIP indicator, 8 dB below full scale
    meter_floor_db: float = -90.0
    # timing
    command_timeout_s: float = 0.5
    slow_command_timeout_s: float = 10.0

    def __post_init__(self) -> None:
        positive = (
            "input_count",
            "output_count",
            "preset_count",
            "page_count",
            "page_size",
            "last_page_size",
            "freq_steps",
            "q_steps",
            "delay_sample_rate_hz",
        )
        for name in positive:
            if getattr(self, name) <= 0:
                raise ProfileError(f"{name} must be > 0")
        if not 0 <= self.host_dst <= 0xFF:
            raise ProfileError("host_dst must be a byte")
        if self.input_count > 8 or self.output_count > 8:
            raise ProfileError("bitmasks limit inputs and outputs to 8 each")
        if not self.freq_min_hz < self.freq_max_hz:
            raise ProfileError("freq_min_hz must be < freq_max_hz")
        if not 0 < self.q_min < self.q_max:
            raise ProfileError("q range is invalid")
        for name in ("meter_tail_limit_byte", "meter_tail_comp_byte", "meter_tail_clip_byte"):
            value = getattr(self, name)
            if value is not None and not 0 <= value < self.meter_tail_length:
                raise ProfileError(f"{name} is outside the meter tail")

    # --- derived values -----------------------------------------------------------------
    @property
    def channel_count(self) -> int:
        return self.input_count + self.output_count

    @property
    def config_size(self) -> int:
        return (self.page_count - 1) * self.page_size + self.last_page_size

    def page_length(self, page: int) -> int:
        if not 0 <= page < self.page_count:
            raise ValueError(f"config page out of range: {page}")
        return self.last_page_size if page == self.page_count - 1 else self.page_size

    def is_input(self, channel: int) -> bool:
        return 0 <= channel < self.input_count

    def is_output(self, channel: int) -> bool:
        return self.input_count <= channel < self.channel_count

    def peq_band_count(self, channel: int) -> int:
        return self.peq_bands_input if self.is_input(channel) else self.peq_bands_output

    # --- loading --------------------------------------------------------------------------
    def with_overrides(self, data: dict[str, Any]) -> ProtocolProfile:
        """Return a copy with values from a parsed profile TOML document applied."""
        return replace(self, **_flatten(data))


def _flatten(data: dict[str, Any]) -> dict[str, Any]:
    known = {f.name for f in fields(ProtocolProfile)}
    result: dict[str, Any] = {}
    for key, value in data.items():
        if key == "name":
            result["name"] = str(value)
            continue
        if key not in _SECTIONS or not isinstance(value, dict):
            raise ProfileError(f"unknown profile section or key: {key!r}")
        prefix = _PREFIXED_SECTIONS.get(key, "")
        for sub_key, sub_value in value.items():
            name = prefix + sub_key
            if name not in _SECTIONS[key] or name not in known:
                raise ProfileError(f"unknown profile key: [{key}] {sub_key}")
            result[name] = _coerce(name, sub_value)
    return result


def _coerce(name: str, value: Any) -> Any:
    if name in ("peq_types", "slopes"):
        return tuple(str(v) for v in value)
    if name == "meter_format":
        return MeterFormat(value)
    if name == "compressor_layout":
        return CompressorLayout(value)
    return value


def _read_default_document() -> dict[str, Any]:
    text = (
        resources.files("tracks_dsp_controller.protocol")
        .joinpath("profiles/default.toml")
        .read_text("utf-8")
    )
    return tomllib.loads(text)


def load_profile(path: str | Path | None = None) -> ProtocolProfile:
    """Load the built-in default profile, optionally overridden by a TOML file."""
    profile = ProtocolProfile().with_overrides(_read_default_document())
    if path is not None:
        with Path(path).open("rb") as handle:
            profile = profile.with_overrides(tomllib.load(handle))
    return profile


DEFAULT_PROFILE = load_profile()
