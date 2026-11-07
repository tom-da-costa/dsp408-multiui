"""Host → device requests (docs/PROTOCOL.md §5).

Requests carry **raw** protocol values; conversion from physical units lives in ``codecs``.
Each request can be encoded (backend side) and decoded (simulator side). Validation that
depends on the device topology needs a profile, so it runs in ``encode``/``decode``.

Deliberately absent: the test-tone generator (0x39) and the device-PIN setter (0x2f).
"""

from __future__ import annotations

import struct
from dataclasses import astuple, dataclass
from enum import IntEnum
from typing import ClassVar, Self

from dsp408_multiui.protocol.codecs import (
    CHANNEL_NAME_LENGTH,
    PRESET_NAME_LENGTH,
    decode_name,
    encode_name,
)
from dsp408_multiui.protocol.profile import CompressorLayout, ProtocolProfile


class Opcode(IntEnum):
    ACK = 0x01
    HANDSHAKE = 0x10
    ACTIVATE = 0x12
    DEVICE_INFO = 0x13
    ACTIVE_PRESET = 0x14
    RECALL_PRESET = 0x20
    STORE_PRESET = 0x21
    PRESET_HEADER = 0x22
    CONFIG_PAGE = 0x24  # response to READ_CONFIG_PAGE
    SET_PRESET_NAME = 0x26
    READ_CONFIG_PAGE = 0x27
    PRESET_NAME = 0x29
    STATUS = 0x2C
    SUBMIT_PIN = 0x2D
    COMPRESSOR = 0x30
    LOW_PASS = 0x31
    HIGH_PASS = 0x32
    PEQ_BAND = 0x33
    GAIN = 0x34
    MUTE = 0x35
    PHASE = 0x36
    DELAY = 0x38
    MATRIX = 0x3A
    PEQ_BYPASS = 0x3C
    CHANNEL_NAME = 0x3D
    GATE = 0x3E
    LIMITER = 0x3F
    METERS = 0x40
    GEQ_BAND = 0x48


class CommandError(ValueError):
    """Raised for an invalid request (bad value, wrong channel kind, malformed payload)."""


def _check_range(name: str, value: int, low: int, high: int) -> None:
    if not low <= value <= high:
        raise CommandError(f"{name}={value} outside {low}..{high}")


def _check_channel(profile: ProtocolProfile, channel: int, kind: str = "any") -> None:
    _check_range("channel", channel, 0, profile.channel_count - 1)
    if kind == "input" and not profile.is_input(channel):
        raise CommandError(f"channel {channel} is not an input")
    if kind == "output" and not profile.is_output(channel):
        raise CommandError(f"channel {channel} is not an output")


_REQUESTS: dict[int, type[Request]] = {}


@dataclass(frozen=True)
class Request:
    """Base class. Subclasses with a fixed layout only declare ``OPCODE`` and ``FORMAT``."""

    OPCODE: ClassVar[Opcode]
    FORMAT: ClassVar[str] = ""  # struct format (little-endian) of the data after the opcode
    SLOW: ClassVar[bool] = False  # needs the long timeout (preset recall/store)

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if "OPCODE" in cls.__dict__:
            _REQUESTS[cls.OPCODE] = cls

    def validate(self, profile: ProtocolProfile) -> None:
        """Raise ``CommandError`` if the request is invalid for ``profile``."""

    def _pack(self, profile: ProtocolProfile) -> bytes:
        try:
            return struct.pack("<" + self.FORMAT, *astuple(self))
        except struct.error as exc:
            raise CommandError(f"{type(self).__name__}: {exc}") from exc

    @classmethod
    def _unpack(cls, data: bytes, profile: ProtocolProfile) -> Self:
        try:
            return cls(*struct.unpack("<" + cls.FORMAT, data))
        except (struct.error, TypeError) as exc:
            raise CommandError(f"{cls.__name__}: malformed payload {data.hex(' ')}") from exc

    def encode(self, profile: ProtocolProfile) -> bytes:
        """Return the frame payload (opcode first)."""
        self.validate(profile)
        return bytes((self.OPCODE,)) + self._pack(profile)

    @classmethod
    def decode(cls, data: bytes, profile: ProtocolProfile) -> Self:
        request = cls._unpack(data, profile)
        request.validate(profile)
        return request

    @property
    def coalesce_key(self) -> tuple[int, ...] | None:
        """Requests with equal keys supersede each other (None: never coalesce)."""
        return None


def decode_request(payload: bytes, profile: ProtocolProfile) -> Request:
    """Decode a host → device payload (used by the simulator and the proxy)."""
    if not payload:
        raise CommandError("empty payload")
    cls = _REQUESTS.get(payload[0])
    if cls is None:
        raise CommandError(f"unknown request opcode 0x{payload[0]:02x}")
    return cls.decode(payload[1:], profile)


# --- session and information ----------------------------------------------------------------
@dataclass(frozen=True)
class Handshake(Request):
    OPCODE = Opcode.HANDSHAKE


@dataclass(frozen=True)
class GetDeviceInfo(Request):
    OPCODE = Opcode.DEVICE_INFO


@dataclass(frozen=True)
class GetStatus(Request):
    OPCODE = Opcode.STATUS


@dataclass(frozen=True)
class GetPresetHeader(Request):
    OPCODE = Opcode.PRESET_HEADER


@dataclass(frozen=True)
class GetActivePreset(Request):
    OPCODE = Opcode.ACTIVE_PRESET


@dataclass(frozen=True)
class Activate(Request):
    OPCODE = Opcode.ACTIVATE


@dataclass(frozen=True)
class PollMeters(Request):
    OPCODE = Opcode.METERS


@dataclass(frozen=True)
class SubmitPin(Request):
    OPCODE = Opcode.SUBMIT_PIN
    pin: str

    def validate(self, profile: ProtocolProfile) -> None:
        if len(self.pin) != 4 or not self.pin.isdigit() or not self.pin.isascii():
            raise CommandError("device PIN must be 4 ASCII digits")

    def _pack(self, profile: ProtocolProfile) -> bytes:
        return b"\x00" + self.pin.encode("ascii")

    @classmethod
    def _unpack(cls, data: bytes, profile: ProtocolProfile) -> Self:
        if len(data) != 5:
            raise CommandError("SubmitPin: malformed payload")
        return cls(data[1:].decode("ascii", errors="replace"))


# --- presets ------------------------------------------------------------------------------
@dataclass(frozen=True)
class GetPresetName(Request):
    """Name of user preset ``index`` (0 = U01)."""

    OPCODE = Opcode.PRESET_NAME
    FORMAT = "B"
    index: int

    def validate(self, profile: ProtocolProfile) -> None:
        _check_range("index", self.index, 0, profile.preset_count - 1)


@dataclass(frozen=True)
class RecallPreset(Request):
    """Recall ``slot`` (0 = F00 factory, 1 = U01 …)."""

    OPCODE = Opcode.RECALL_PRESET
    FORMAT = "B"
    SLOW = True
    slot: int

    def validate(self, profile: ProtocolProfile) -> None:
        _check_range("slot", self.slot, 0, profile.preset_count)


@dataclass(frozen=True)
class SetPresetName(Request):
    """Name used by the next ``StorePreset``. At most 14 printable ASCII characters."""

    OPCODE = Opcode.SET_PRESET_NAME
    name: str

    def validate(self, profile: ProtocolProfile) -> None:
        try:
            encode_name(self.name, PRESET_NAME_LENGTH, b" ")
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

    def _pack(self, profile: ProtocolProfile) -> bytes:
        return encode_name(self.name, PRESET_NAME_LENGTH, b" ")

    @classmethod
    def _unpack(cls, data: bytes, profile: ProtocolProfile) -> Self:
        if len(data) != PRESET_NAME_LENGTH:
            raise CommandError(f"SetPresetName: expected 14 bytes, got {len(data)}")
        return cls(decode_name(data))


@dataclass(frozen=True)
class StorePreset(Request):
    """Store the live state into user slot 1..N. Slot 0 (F00) is refused by design."""

    OPCODE = Opcode.STORE_PRESET
    FORMAT = "B"
    SLOW = True
    slot: int

    def validate(self, profile: ProtocolProfile) -> None:
        if self.slot == 0:
            raise CommandError("storing to the factory preset F00 is forbidden")
        _check_range("slot", self.slot, 1, profile.preset_count)


@dataclass(frozen=True)
class ReadConfigPage(Request):
    OPCODE = Opcode.READ_CONFIG_PAGE
    FORMAT = "B"
    page: int

    def validate(self, profile: ProtocolProfile) -> None:
        _check_range("page", self.page, 0, profile.page_count - 1)


# --- parameters ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SetGain(Request):
    OPCODE = Opcode.GAIN
    FORMAT = "BH"
    channel: int
    raw: int

    def validate(self, profile: ProtocolProfile) -> None:
        _check_channel(profile, self.channel)
        _check_range("gain", self.raw, 0, 400)

    @property
    def coalesce_key(self) -> tuple[int, ...]:
        return (self.OPCODE, self.channel)


@dataclass(frozen=True)
class _ChannelFlag(Request):
    FORMAT = "BB"
    channel: int
    on: bool

    def validate(self, profile: ProtocolProfile) -> None:
        _check_channel(profile, self.channel)

    def _pack(self, profile: ProtocolProfile) -> bytes:
        return bytes((self.channel, 1 if self.on else 0))

    @classmethod
    def _unpack(cls, data: bytes, profile: ProtocolProfile) -> Self:
        if len(data) != 2 or data[1] > 1:
            raise CommandError(f"{cls.__name__}: malformed payload {data.hex(' ')}")
        return cls(data[0], bool(data[1]))

    @property
    def coalesce_key(self) -> tuple[int, ...]:
        return (self.OPCODE, self.channel)


@dataclass(frozen=True)
class SetMute(_ChannelFlag):
    OPCODE = Opcode.MUTE


@dataclass(frozen=True)
class SetPhase(_ChannelFlag):
    OPCODE = Opcode.PHASE


@dataclass(frozen=True)
class SetPeqBypass(_ChannelFlag):
    OPCODE = Opcode.PEQ_BYPASS


@dataclass(frozen=True)
class SetMatrix(Request):
    """Full input bitmask for one output (bit 0 = In A)."""

    OPCODE = Opcode.MATRIX
    FORMAT = "BB"
    channel: int
    mask: int

    def validate(self, profile: ProtocolProfile) -> None:
        _check_channel(profile, self.channel, "output")
        _check_range("mask", self.mask, 0, (1 << profile.input_count) - 1)

    @property
    def coalesce_key(self) -> tuple[int, ...]:
        return (self.OPCODE, self.channel)


@dataclass(frozen=True)
class SetGeqBand(Request):
    OPCODE = Opcode.GEQ_BAND
    FORMAT = "BBH"
    channel: int
    band: int
    raw: int

    def validate(self, profile: ProtocolProfile) -> None:
        _check_channel(profile, self.channel, "input")
        _check_range("band", self.band, 0, profile.geq_bands - 1)
        _check_range("gain", self.raw, 0, 240)

    @property
    def coalesce_key(self) -> tuple[int, ...]:
        return (self.OPCODE, self.channel, self.band)


@dataclass(frozen=True)
class SetPeqBand(Request):
    OPCODE = Opcode.PEQ_BAND
    FORMAT = "BBHHBB?"
    channel: int
    band: int
    gain: int
    freq: int
    q: int
    type: int
    bypass: bool

    def validate(self, profile: ProtocolProfile) -> None:
        _check_channel(profile, self.channel)
        _check_range("band", self.band, 0, profile.peq_band_count(self.channel) - 1)
        _check_range("gain", self.gain, 0, 240)
        _check_range("freq", self.freq, 0, profile.freq_steps)
        _check_range("q", self.q, 0, profile.q_steps)
        _check_range("type", self.type, 0, max(len(profile.peq_types), 1) - 1)

    @property
    def coalesce_key(self) -> tuple[int, ...]:
        return (self.OPCODE, self.channel, self.band)


@dataclass(frozen=True)
class _Crossover(Request):
    FORMAT = "BHB"
    channel: int
    freq: int
    slope: int  # 0 = bypass

    def validate(self, profile: ProtocolProfile) -> None:
        _check_channel(profile, self.channel)
        _check_range("freq", self.freq, 0, profile.freq_steps)
        _check_range("slope", self.slope, 0, max(len(profile.slopes), 1) - 1)

    @property
    def coalesce_key(self) -> tuple[int, ...]:
        return (self.OPCODE, self.channel)


@dataclass(frozen=True)
class SetHighPass(_Crossover):
    OPCODE = Opcode.HIGH_PASS


@dataclass(frozen=True)
class SetLowPass(_Crossover):
    OPCODE = Opcode.LOW_PASS


@dataclass(frozen=True)
class SetDelay(Request):
    OPCODE = Opcode.DELAY
    FORMAT = "BH"
    channel: int
    raw: int  # samples

    def validate(self, profile: ProtocolProfile) -> None:
        _check_channel(profile, self.channel)
        max_raw = round(profile.delay_max_ms * profile.delay_sample_rate_hz / 1000)
        _check_range("delay", self.raw, 0, min(max_raw, 0xFFFF))

    @property
    def coalesce_key(self) -> tuple[int, ...]:
        return (self.OPCODE, self.channel)


@dataclass(frozen=True)
class SetCompressor(Request):
    OPCODE = Opcode.COMPRESSOR
    channel: int
    ratio: int  # index into codecs.COMPRESSOR_RATIOS
    attack: int
    release: int
    knee: int
    threshold: int

    def validate(self, profile: ProtocolProfile) -> None:
        _check_channel(profile, self.channel, "output")
        _check_range("ratio", self.ratio, 0, 15)
        _check_range("knee", self.knee, 0, 12)
        _check_range("attack", self.attack, 0, 0xFFFF)
        _check_range("release", self.release, 0, 0xFFFF)
        _check_range("threshold", self.threshold, 0, 220)

    def _pack(self, profile: ProtocolProfile) -> bytes:
        c = self
        if profile.compressor_layout is CompressorLayout.WIDE:
            return struct.pack(
                "<BHHHHH", c.channel, c.ratio, c.attack, c.release, c.knee, c.threshold
            )
        return struct.pack("<BBBHHH", c.channel, c.ratio, c.knee, c.attack, c.release, c.threshold)

    @classmethod
    def _unpack(cls, data: bytes, profile: ProtocolProfile) -> Self:
        try:
            if profile.compressor_layout is CompressorLayout.WIDE:
                ch, ratio, attack, release, knee, thr = struct.unpack("<BHHHHH", data)
            else:
                ch, ratio, knee, attack, release, thr = struct.unpack("<BBBHHH", data)
        except struct.error as exc:
            raise CommandError(f"SetCompressor: malformed payload {data.hex(' ')}") from exc
        return cls(ch, ratio, attack, release, knee, thr)

    @property
    def coalesce_key(self) -> tuple[int, ...]:
        return (self.OPCODE, self.channel)


@dataclass(frozen=True)
class SetLimiter(Request):
    OPCODE = Opcode.LIMITER
    FORMAT = "BHHHH"
    channel: int
    attack: int
    release: int
    reserved: int  # unknown field, always 0 so far
    threshold: int

    def validate(self, profile: ProtocolProfile) -> None:
        _check_channel(profile, self.channel, "output")
        _check_range("threshold", self.threshold, 0, 220)

    @property
    def coalesce_key(self) -> tuple[int, ...]:
        return (self.OPCODE, self.channel)


@dataclass(frozen=True)
class SetGate(Request):
    OPCODE = Opcode.GATE
    FORMAT = "BHHHH"
    channel: int
    attack: int
    release: int
    hold: int
    threshold: int

    def validate(self, profile: ProtocolProfile) -> None:
        _check_channel(profile, self.channel, "input")
        _check_range("threshold", self.threshold, 0, 180)

    @property
    def coalesce_key(self) -> tuple[int, ...]:
        return (self.OPCODE, self.channel)


@dataclass(frozen=True)
class SetChannelName(Request):
    OPCODE = Opcode.CHANNEL_NAME
    channel: int
    name: str

    def validate(self, profile: ProtocolProfile) -> None:
        _check_channel(profile, self.channel)
        try:
            encode_name(self.name, CHANNEL_NAME_LENGTH)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

    def _pack(self, profile: ProtocolProfile) -> bytes:
        return bytes((self.channel,)) + encode_name(self.name, CHANNEL_NAME_LENGTH)

    @classmethod
    def _unpack(cls, data: bytes, profile: ProtocolProfile) -> Self:
        if len(data) != 1 + CHANNEL_NAME_LENGTH:
            raise CommandError("SetChannelName: malformed payload")
        return cls(data[0], decode_name(data[1:]))

    @property
    def coalesce_key(self) -> tuple[int, ...]:
        return (self.OPCODE, self.channel)
