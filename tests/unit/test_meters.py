import math
import struct

import pytest

from dsp408_multiui.protocol.meters import (
    MeterError,
    decode_meters,
    encode_meters,
    meter_data_length,
)
from dsp408_multiui.protocol.profile import DEFAULT_PROFILE as P

LEVEL24 = P.with_overrides(
    {
        "meters": {
            "format": "level24",
            "tail_length": 3,
            "tail_limit_byte": 0,
            "tail_clip_byte": 2,
            "reference": 20872.3,
            "clip_db": 11.0,
        },
        "topology": {"input_count": 4, "output_count": 4},
    }
)


def test_dsp408_meter_frame_length_matches_capture() -> None:
    # dsp-408-ui: response LEN = 0x27 = opcode + 38 data bytes
    assert meter_data_length(P) == 0x27 - 1


def test_float16_decoding() -> None:
    data = bytearray(meter_data_length(P))
    struct.pack_into("<e", data, 0, 1.0)  # In A at the reference level -> 0 dB
    struct.pack_into("<e", data, 3, 2.0)  # In B +6 dB -> clip
    data[6:8] = b"\xff\xff"  # In C: NaN = no data
    data[36] = 0b1000_0001  # limiter active on Out 1 and Out 8
    data[37] = 1  # an input clips
    reading = decode_meters(bytes(data), P)
    assert reading.levels_db[0] == pytest.approx(0.0)
    assert reading.levels_db[1] == pytest.approx(6.02, abs=0.01)
    assert reading.levels_db[2] is None
    assert reading.levels_db[3] == P.meter_floor_db  # silence
    assert reading.clip[:4] == (False, True, False, False)
    assert reading.limit == (True, False, False, False, False, False, False, True)
    assert reading.comp is None
    assert reading.input_clip_flag is True


def test_level24_vectors_from_4x4_mini() -> None:
    # Triplets are [mid, high, low]; values from the miniDSP-Linux sine-sweep capture.
    triplets = ["000014", "01000c", "0700b7", "0b0009"]
    expected = [20, 268, 1975, 2825]
    data = bytes.fromhex("".join(triplets) + "ffffff" + "000000" * 3 + "080001")
    reading = decode_meters(data, LEVEL24)
    for level_db, raw in zip(reading.levels_db[:4], expected, strict=True):
        assert level_db == pytest.approx(20 * math.log10(raw / 20872.3))
    assert reading.levels_db[4] is None
    assert reading.limit == (False, False, False, True)
    assert reading.input_clip_flag is True


@pytest.mark.parametrize("profile", [P, LEVEL24])
def test_encode_decode_roundtrip(profile: object) -> None:
    from dsp408_multiui.protocol.profile import ProtocolProfile

    assert isinstance(profile, ProtocolProfile)
    n = profile.channel_count
    levels: list[float | None] = [-20.0 + i for i in range(n)]
    levels[1] = None
    levels[2] = profile.meter_floor_db
    limit = [i % 2 == 0 for i in range(profile.output_count)]
    data = encode_meters(levels, profile, limit=limit)
    reading = decode_meters(data, profile)
    assert reading.levels_db[1] is None
    assert reading.levels_db[2] == profile.meter_floor_db
    for got, want in zip(reading.levels_db, levels, strict=True):
        if want is not None and want > profile.meter_floor_db:
            assert got == pytest.approx(want, abs=0.05)
    assert reading.limit == tuple(limit)


def test_encode_sets_input_clip_flag() -> None:
    levels: list[float | None] = [-10.0] * P.channel_count
    assert decode_meters(encode_meters(levels, P), P).input_clip_flag is False
    levels[0] = 9.0
    assert decode_meters(encode_meters(levels, P), P).input_clip_flag is True


def test_wrong_lengths() -> None:
    with pytest.raises(MeterError):
        decode_meters(bytes(10), P)
    with pytest.raises(MeterError):
        encode_meters([0.0], P)
