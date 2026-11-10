"""Frame encoding and incremental decoding.

Wire format (see docs/PROTOCOL.md §2)::

    10 02 | SRC | DST | LEN | PAYLOAD (LEN bytes) | 10 03 | CHK

``CHK`` is ``1 ^ SRC ^ DST ^ LEN`` XOR every payload byte. With the 408's addresses
(``SRC ^ DST == 1``) this reduces to ``LEN`` XOR the payload; the 206 talks on address 0x02,
where the full formula matters (verified on 8303 frames captured from a DSP 206).

There is no byte stuffing, so the decoder frames on ``LEN`` and never searches for ``10 03``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import reduce
from operator import xor

STX = b"\x10\x02"
ETX = b"\x10\x03"

HOST = 0x00
DEVICE = 0x01  # address of a DSP 408 (a DSP 206 uses 0x02 and also answers on 0x01)

HEADER_SIZE = 5  # STX(2) + SRC + DST + LEN
TRAILER_SIZE = 3  # ETX(2) + CHK
MAX_PAYLOAD = 0xFF


class FrameError(ValueError):
    """Raised when a frame cannot be built."""


def checksum(payload: bytes, src: int = HOST, dst: int = DEVICE) -> int:
    """Return ``1 ^ SRC ^ DST ^ LEN ^ payload[0] ^ ... ^ payload[-1]``."""
    return reduce(xor, payload, 1 ^ src ^ dst ^ (len(payload) & 0xFF))


@dataclass(frozen=True, slots=True)
class Frame:
    """A decoded frame."""

    src: int
    dst: int
    payload: bytes

    @property
    def opcode(self) -> int:
        return self.payload[0]

    @property
    def data(self) -> bytes:
        """Payload without its opcode byte."""
        return self.payload[1:]

    @property
    def from_device(self) -> bool:
        return self.src != HOST

    def encode(self) -> bytes:
        return encode_frame(self.payload, src=self.src, dst=self.dst)


def encode_frame(payload: bytes, *, src: int = HOST, dst: int = DEVICE) -> bytes:
    """Wrap ``payload`` (opcode first) into a complete frame."""
    if not payload:
        raise FrameError("payload must contain at least the opcode")
    if len(payload) > MAX_PAYLOAD:
        raise FrameError(f"payload too long: {len(payload)} > {MAX_PAYLOAD}")
    if not (0 <= src <= 0xFF and 0 <= dst <= 0xFF):
        raise FrameError("src/dst must be bytes")
    return (
        STX
        + bytes((src, dst, len(payload)))
        + bytes(payload)
        + ETX
        + bytes((checksum(payload, src, dst),))
    )


@dataclass(slots=True)
class FrameDecoder:
    """Incremental decoder for a byte stream (TCP).

    Feed it arbitrary chunks; it returns every complete, valid frame. Invalid data is skipped
    by resynchronising on the next ``10 02``. Counters help diagnose a noisy link.
    """

    _buffer: bytearray = field(default_factory=bytearray)
    skipped_bytes: int = 0
    bad_frames: int = 0

    def feed(self, data: bytes) -> list[Frame]:
        self._buffer.extend(data)
        frames: list[Frame] = []
        buf = self._buffer
        while True:
            start = buf.find(STX)
            if start < 0:
                # Keep a trailing 0x10: it may be the first half of the next STX.
                keep = 1 if buf.endswith(b"\x10") else 0
                self.skipped_bytes += len(buf) - keep
                del buf[: len(buf) - keep]
                break
            if start > 0:
                self.skipped_bytes += start
                del buf[:start]
            if len(buf) < HEADER_SIZE:
                break
            length = buf[4]
            total = HEADER_SIZE + length + TRAILER_SIZE
            if len(buf) < total:
                break
            payload = bytes(buf[HEADER_SIZE : HEADER_SIZE + length])
            trailer = buf[HEADER_SIZE + length : total]
            if length == 0 or trailer[:2] != ETX or trailer[2] != checksum(payload, buf[2], buf[3]):
                # Not a real frame start: drop the 0x10 and look for the next STX.
                self.bad_frames += 1
                self.skipped_bytes += 1
                del buf[:1]
                continue
            frames.append(Frame(src=buf[2], dst=buf[3], payload=payload))
            del buf[:total]
        return frames

    @property
    def pending(self) -> int:
        """Number of buffered bytes not yet decoded."""
        return len(self._buffer)

    def reset(self) -> None:
        self._buffer.clear()
