import math
import struct
from pathlib import Path

import pytest

from dsp408_multiui.protocol.meters import (
    MeterError,
    decode_meters,
    encode_meters,
    meter_data_length,
)
from dsp408_multiui.protocol.profile import DEFAULT_PROFILE as P

FIXTURES = Path(__file__).parent.parent / "fixtures" / "meters"

# dsp-408-ui's reading (float16 + peak byte, limiter mask + "input clips" flag): wrong on a 408,
# kept as a profile option.
FLOAT16 = P.with_overrides(
    {
        "meters": {
            "format": "float16",
            "tail_limit_byte": 0,
            "tail_comp_byte": None,
            "tail_clip_byte": 1,
            "reference": 1.0,
            "clip_db": 6.0,
        }
    }
)

LEVEL24 = P.with_overrides(
    {
        "meters": {
            "format": "level24",
            "tail_length": 3,
            "tail_limit_byte": 0,
            "tail_comp_byte": None,
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


def hardware_frames() -> list[bytes]:
    lines = (FIXTURES / "dsp408_u08.txt").read_text().splitlines()
    return [bytes.fromhex(line) for line in lines if line and not line.startswith("#")]


def test_float32_hardware_frames() -> None:
    profile = P.with_overrides({"meters": {"floor_db": -120.0}})
    for data in hardware_frames():
        reading = decode_meters(data, profile)
        levels = [lv if lv is not None else math.nan for lv in reading.levels_db]
        in_a, in_b, in_c, in_d = levels[:4]
        assert -30 < in_a < 0  # music
        assert -30 < in_b < 0
        assert in_c == pytest.approx(-85.7, abs=0.5)  # ADC noise floor
        assert in_d == pytest.approx(-85.7, abs=0.5)
        assert all(-50 < lv < 20 for lv in levels[4:])
        assert reading.comp == (False,) * 8
        assert reading.limit == (False,) * 8
        assert reading.input_clip_flag is None
        assert not any(reading.clip)


def test_float32_scale() -> None:
    # On hardware, a 6 dB gain step moved the top 16 bits by 127.5 (128 per octave): a float.
    data = bytearray(meter_data_length(P))
    # Reference 0.1 = 0 dB (the threshold scale): full scale 1.0 = +20 dB.
    data[0:3] = bytes.fromhex("80 3f 00")  # float32 3f800000 = 1.0 -> +20 dB
    data[3:6] = bytes.fromhex("00 3f 00")  # 0.5 -> +13.98 dB
    data[6:9] = bytes.fromhex("00 41 00")  # 8.0 -> +38.06 dB (levels can exceed full scale)
    data[9:12] = bytes.fromhex("ad 05 50")  # a muted channel: ~1e-35 -> floor
    data[12:15] = bytes.fromhex("c0 7f 00")  # NaN -> no data
    data[36] = 0b0001_0001  # compressor active on Out 1 and Out 5
    data[37] = 0b0010_0010  # limiter active on Out 2 and Out 6
    reading = decode_meters(bytes(data), P)
    assert reading.levels_db[0] == pytest.approx(20.0)
    assert reading.levels_db[1] == pytest.approx(13.98, abs=0.01)
    assert reading.levels_db[2] == pytest.approx(38.06, abs=0.01)
    assert reading.levels_db[3] == P.meter_floor_db
    assert reading.levels_db[4] is None
    assert reading.clip[:3] == (True, False, True)  # clip from full scale (+20 dB)
    assert reading.comp == (True, False, False, False, True, False, False, False)
    assert reading.limit == (False, True, False, False, False, True, False, False)


def test_float16_decoding() -> None:
    P = FLOAT16  # noqa: N806
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


@pytest.mark.parametrize("profile", [P, FLOAT16, LEVEL24])
def test_encode_decode_roundtrip(profile: object) -> None:
    from dsp408_multiui.protocol.profile import ProtocolProfile

    assert isinstance(profile, ProtocolProfile)
    n = profile.channel_count
    levels: list[float | None] = [-20.0 + i for i in range(n)]
    levels[1] = None
    levels[2] = profile.meter_floor_db
    limit = [i % 2 == 0 for i in range(profile.output_count)]
    comp = [i % 3 == 0 for i in range(profile.output_count)]
    data = encode_meters(levels, profile, limit=limit, comp=comp)
    reading = decode_meters(data, profile)
    assert reading.levels_db[1] is None
    assert reading.levels_db[2] == profile.meter_floor_db
    for got, want in zip(reading.levels_db, levels, strict=True):
        if want is not None and want > profile.meter_floor_db:
            assert got == pytest.approx(want, abs=0.05)
    assert reading.limit == tuple(limit)
    if profile.meter_tail_comp_byte is not None:
        assert reading.comp == tuple(comp)


def test_encode_sets_input_clip_flag() -> None:
    levels: list[float | None] = [-10.0] * FLOAT16.channel_count
    assert decode_meters(encode_meters(levels, FLOAT16), FLOAT16).input_clip_flag is False
    levels[0] = 9.0
    assert decode_meters(encode_meters(levels, FLOAT16), FLOAT16).input_clip_flag is True


def test_wrong_lengths() -> None:
    with pytest.raises(MeterError):
        decode_meters(bytes(10), P)
    with pytest.raises(MeterError):
        encode_meters([0.0], P)
