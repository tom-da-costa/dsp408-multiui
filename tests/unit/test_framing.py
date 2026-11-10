"""Frame encoding/decoding.

Reference frames come from Aeternitaas/dsp-408-ui (GPL-3.0, captured on a DSP 408) and
IMBArator/miniDSP-Linux (GPL-3.0). See the attribution table in README.md.
"""

import pytest

from dsp408_multiui.protocol.framing import (
    DEVICE,
    HOST,
    Frame,
    FrameDecoder,
    FrameError,
    checksum,
    encode_frame,
)

H = bytes.fromhex

# (payload, full frame) captured on a DSP 408 by dsp-408-ui
DSP408_FRAMES = [
    ("10", "10 02 00 01 01 10 10 03 11"),  # handshake
    ("13", "10 02 00 01 01 13 10 03 12"),  # device info
    ("2c", "10 02 00 01 01 2c 10 03 2d"),  # status
    ("22", "10 02 00 01 01 22 10 03 23"),
    ("14", "10 02 00 01 01 14 10 03 15"),
    ("12", "10 02 00 01 01 12 10 03 13"),  # activate
    ("40", "10 02 00 01 01 40 10 03 41"),  # meter poll
    ("29 00", "10 02 00 01 02 29 00 10 03 2b"),
    ("29 13", "10 02 00 01 02 29 13 10 03 38"),
    ("27 00", "10 02 00 01 02 27 00 10 03 25"),
    ("27 1c", "10 02 00 01 02 27 1c 10 03 39"),
    ("35 00 01", "10 02 00 01 03 35 00 01 10 03 37"),  # mute In A
    ("35 00 00", "10 02 00 01 03 35 00 00 10 03 36"),
    ("35 08 01", "10 02 00 01 03 35 08 01 10 03 3f"),  # mute Out 5
    ("35 0b 00", "10 02 00 01 03 35 0b 00 10 03 3d"),  # unmute Out 8
    # 4x4 Mini (same protocol family)
    ("34 00 00 00", "10 02 00 01 04 34 00 00 00 10 03 30"),
    ("34 00 c8 00", "10 02 00 01 04 34 00 c8 00 10 03 f8"),
    ("34 00 90 01", "10 02 00 01 04 34 00 90 01 10 03 a1"),
]


@pytest.mark.parametrize(("payload", "frame"), DSP408_FRAMES)
def test_encode_matches_captures(payload: str, frame: str) -> None:
    assert encode_frame(H(payload)) == H(frame)


@pytest.mark.parametrize(("payload", "frame"), DSP408_FRAMES)
def test_decode_captures(payload: str, frame: str) -> None:
    decoder = FrameDecoder()
    assert decoder.feed(H(frame)) == [Frame(HOST, DEVICE, H(payload))]
    assert decoder.pending == 0


def test_ack_from_device() -> None:
    frame = H("10 02 01 00 01 01 10 03 00")
    assert encode_frame(b"\x01", src=DEVICE, dst=HOST) == frame
    (decoded,) = FrameDecoder().feed(frame)
    assert decoded.from_device
    assert decoded.opcode == 0x01
    assert decoded.data == b""


def test_checksum_is_len_xor_payload() -> None:
    assert checksum(b"\x10") == 0x11
    assert checksum(bytes(range(1, 6))) == 5 ^ 1 ^ 2 ^ 3 ^ 4 ^ 5


@pytest.mark.parametrize("payload", [b"", bytes(256)])
def test_encode_rejects_bad_payload(payload: bytes) -> None:
    with pytest.raises(FrameError):
        encode_frame(payload)


def test_frame_roundtrip() -> None:
    frame = Frame(DEVICE, HOST, b"\x40" + bytes(range(38)))
    (decoded,) = FrameDecoder().feed(frame.encode())
    assert decoded == frame


def test_decoder_handles_byte_by_byte_and_concatenated_frames() -> None:
    stream = encode_frame(b"\x10") + encode_frame(b"\x34\x04\x18\x01") + encode_frame(b"\x40")
    decoder = FrameDecoder()
    frames = [f for byte in stream for f in decoder.feed(bytes((byte,)))]
    assert [f.payload for f in frames] == [b"\x10", b"\x34\x04\x18\x01", b"\x40"]
    assert FrameDecoder().feed(stream) == frames


def test_decoder_frames_on_len_even_if_payload_contains_etx() -> None:
    payload = b"\x24\x05" + b"\x10\x03\x10\x02" + bytes(10)
    (decoded,) = FrameDecoder().feed(encode_frame(payload, src=DEVICE, dst=HOST))
    assert decoded.payload == payload


def test_decoder_skips_garbage_and_bad_frames() -> None:
    good = encode_frame(b"\x40")
    corrupt = bytearray(encode_frame(b"\x35\x00\x01"))
    corrupt[-1] ^= 0xFF  # bad checksum
    decoder = FrameDecoder()
    frames = decoder.feed(b"\x00\xff\x10" + bytes(corrupt) + b"junk" + good)
    assert [f.payload for f in frames] == [b"\x40"]
    assert decoder.bad_frames >= 1
    assert decoder.skipped_bytes > 0
    assert decoder.pending == 0


def test_decoder_keeps_partial_stx() -> None:
    decoder = FrameDecoder()
    frame = encode_frame(b"\x40")
    assert decoder.feed(b"\xaa" + frame[:1]) == []
    assert decoder.pending == 1
    assert [f.payload for f in decoder.feed(frame[1:])] == [b"\x40"]


def test_decoder_rejects_zero_length_frame() -> None:
    decoder = FrameDecoder()
    assert decoder.feed(H("10 02 00 01 00 10 03 00") + encode_frame(b"\x12")) == [
        Frame(HOST, DEVICE, b"\x12")
    ]
    decoder.reset()
    assert decoder.pending == 0
