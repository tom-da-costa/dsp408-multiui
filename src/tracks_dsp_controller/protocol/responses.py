"""Device → host responses (docs/PROTOCOL.md §5).

Responses are not tagged with a request id: the device answers one request at a time, so the
caller knows which response to expect. ``decode_response`` only dispatches on the opcode.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Self

from tracks_dsp_controller.protocol.codecs import (
    PRESET_NAME_LENGTH,
    decode_name,
    encode_stored_name,
)
from tracks_dsp_controller.protocol.commands import Opcode


class ResponseError(ValueError):
    """Raised for a malformed or unexpected response."""


_RESPONSES: dict[int, type[Response]] = {}


@dataclass(frozen=True)
class Response:
    OPCODE: ClassVar[Opcode]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if "OPCODE" in cls.__dict__:
            _RESPONSES[cls.OPCODE] = cls

    def _pack(self) -> bytes:
        return b""

    @classmethod
    def _unpack(cls, data: bytes) -> Self:
        if data:
            raise ResponseError(f"{cls.__name__}: unexpected data {data.hex(' ')}")
        return cls()

    def encode(self) -> bytes:
        """Return the frame payload (opcode first)."""
        return bytes((self.OPCODE,)) + self._pack()

    @classmethod
    def decode(cls, data: bytes) -> Self:
        return cls._unpack(data)


def decode_response(payload: bytes) -> Response:
    if not payload:
        raise ResponseError("empty payload")
    cls = _RESPONSES.get(payload[0])
    if cls is None:
        return Unknown(payload[0], payload[1:])
    return cls.decode(payload[1:])


@dataclass(frozen=True)
class Unknown(Response):
    """A response with an opcode we do not model (kept for logging)."""

    opcode: int
    data: bytes

    def encode(self) -> bytes:
        return bytes((self.opcode,)) + self.data


@dataclass(frozen=True)
class Ack(Response):
    """ACK. Usually empty; the 408 answers a preset-name set (0x26) with ``01`` + the name."""

    OPCODE = Opcode.ACK
    data: bytes = b""

    def _pack(self) -> bytes:
        return self.data

    @classmethod
    def _unpack(cls, data: bytes) -> Self:
        return cls(bytes(data))

    def __repr__(self) -> str:
        return f"Ack({self.data.hex(' ')})" if self.data else "Ack()"


@dataclass(frozen=True)
class _Opaque(Response):
    """Response whose data is kept raw because its meaning is not fully known."""

    data: bytes = b""

    def _pack(self) -> bytes:
        return self.data

    @classmethod
    def _unpack(cls, data: bytes) -> Self:
        return cls(bytes(data))


@dataclass(frozen=True)
class HandshakeReply(_Opaque):
    OPCODE = Opcode.HANDSHAKE


@dataclass(frozen=True)
class PresetHeader(_Opaque):
    OPCODE = Opcode.PRESET_HEADER


@dataclass(frozen=True)
class Status(_Opaque):
    """0x2c reply. On the 4x4 Mini, data[5] is the device-lock flag (unverified on the 408)."""

    OPCODE = Opcode.STATUS


@dataclass(frozen=True)
class DeviceInfo(Response):
    OPCODE = Opcode.DEVICE_INFO
    text: str

    def _pack(self) -> bytes:
        return self.text.encode("ascii", errors="replace")

    @classmethod
    def _unpack(cls, data: bytes) -> Self:
        return cls(data.decode("latin-1").strip("\x00 "))

    @property
    def model(self) -> str:
        parts = self.text.split()
        return parts[0] if parts else ""

    @property
    def firmware(self) -> str:
        parts = self.text.split()
        return parts[1] if len(parts) > 1 else ""


@dataclass(frozen=True)
class ActivePreset(Response):
    OPCODE = Opcode.ACTIVE_PRESET
    slot: int

    def _pack(self) -> bytes:
        return bytes((self.slot,))

    @classmethod
    def _unpack(cls, data: bytes) -> Self:
        if len(data) != 1:
            raise ResponseError("ActivePreset: expected 1 byte")
        return cls(data[0])


@dataclass(frozen=True)
class PresetName(Response):
    OPCODE = Opcode.PRESET_NAME
    index: int
    name: str

    def _pack(self) -> bytes:
        # A name the device already holds (Latin-1 on the 408, e.g. "Pas touché svp").
        return bytes((self.index,)) + encode_stored_name(self.name, PRESET_NAME_LENGTH, b" ")

    @classmethod
    def _unpack(cls, data: bytes) -> Self:
        if len(data) < 1:
            raise ResponseError("PresetName: missing index")
        return cls(data[0], decode_name(data[1 : 1 + PRESET_NAME_LENGTH]))


@dataclass(frozen=True)
class ConfigPage(Response):
    OPCODE = Opcode.CONFIG_PAGE
    page: int
    data: bytes

    def _pack(self) -> bytes:
        return bytes((self.page,)) + self.data

    @classmethod
    def _unpack(cls, data: bytes) -> Self:
        if len(data) < 1:
            raise ResponseError("ConfigPage: missing page index")
        return cls(data[0], bytes(data[1:]))


@dataclass(frozen=True)
class PinResult(Response):
    OPCODE = Opcode.SUBMIT_PIN
    accepted: bool

    def _pack(self) -> bytes:
        return bytes((0x00, 0x01 if self.accepted else 0x00))

    @classmethod
    def _unpack(cls, data: bytes) -> Self:
        if len(data) != 2:
            raise ResponseError("PinResult: expected 2 bytes")
        return cls(data[1] == 0x01)


@dataclass(frozen=True)
class MeterFrame(Response):
    """Raw meter data; decode it with ``meters.decode_meters``."""

    OPCODE = Opcode.METERS
    data: bytes

    def _pack(self) -> bytes:
        return self.data

    @classmethod
    def _unpack(cls, data: bytes) -> Self:
        return cls(bytes(data))
