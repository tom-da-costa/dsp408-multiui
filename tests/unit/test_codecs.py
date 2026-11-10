import math

import pytest

from tracks_dsp_controller.protocol import codecs as c
from tracks_dsp_controller.protocol.profile import DEFAULT_PROFILE


# --- gain (two segments, verified on the 4x4 Mini and dsp-408-ui) ---------------------------
@pytest.mark.parametrize(
    ("raw", "db"),
    [(0, -60.0), (1, -59.5), (79, -20.5), (80, -20.0), (160, -12.0), (280, 0.0), (400, 12.0)],
)
def test_gain_table(raw: int, db: float) -> None:
    assert c.gain_raw_to_db(raw) == db
    assert c.gain_db_to_raw(db) == raw


def test_gain_roundtrip_every_raw_value() -> None:
    for raw in range(401):
        assert c.gain_db_to_raw(c.gain_raw_to_db(raw)) == raw


def test_gain_clamps_and_quantizes() -> None:
    assert c.gain_db_to_raw(-100) == 0
    assert c.gain_db_to_raw(30) == 400
    assert c.quantize_gain(-30.3) == -30.5
    assert c.quantize_gain(-3.24) == -3.2
    with pytest.raises(ValueError, match="finite"):
        c.gain_db_to_raw(math.nan)


# --- EQ gain -----------------------------------------------------------------------------------
@pytest.mark.parametrize(("raw", "db"), [(0, -12.0), (120, 0.0), (150, 3.0), (240, 12.0)])
def test_eq_gain(raw: int, db: float) -> None:
    assert c.eq_gain_raw_to_db(raw) == db
    assert c.eq_gain_db_to_raw(db) == raw


def test_eq_gain_clamps() -> None:
    assert c.eq_gain_db_to_raw(-40) == 0
    assert c.eq_gain_db_to_raw(40) == 240


# --- frequency (300 steps, 19.7 Hz .. 20.16 kHz) ------------------------------------------------
def test_frequency_endpoints_and_reference_point() -> None:
    assert c.freq_raw_to_hz(0) == pytest.approx(19.70)
    assert c.freq_raw_to_hz(300) == pytest.approx(20160.0)
    # 4x4 Mini capture: raw 128 = 379.1 Hz
    assert c.freq_raw_to_hz(128) == pytest.approx(379.1, abs=0.1)


def test_frequency_values_seen_in_the_408_dump_are_plausible() -> None:
    # "Forest" preset, Out1 subwoofer: HPF raw 11, LPF raw 61
    assert c.freq_raw_to_hz(11) == pytest.approx(25.4, abs=0.1)
    assert c.freq_raw_to_hz(61) == pytest.approx(80.6, abs=0.1)


def test_frequency_roundtrip_and_clamp() -> None:
    for raw in range(301):
        assert c.freq_hz_to_raw(c.freq_raw_to_hz(raw)) == raw
    assert c.freq_hz_to_raw(1) == 0
    assert c.freq_hz_to_raw(1e6) == 300


# --- Q -------------------------------------------------------------------------------------------
def test_q_scale() -> None:
    assert c.q_raw_to_q(0) == pytest.approx(0.4)
    assert c.q_raw_to_q(100) == pytest.approx(128.0)
    assert c.q_raw_to_q(25) == pytest.approx(1.69, abs=0.01)  # 4x4 Mini default
    for raw in range(101):
        assert c.q_to_raw(c.q_raw_to_q(raw)) == raw
    assert c.q_to_raw(0.01) == 0
    assert c.q_to_raw(1000) == 100


# --- dynamics --------------------------------------------------------------------------------
def test_threshold() -> None:
    assert c.threshold_raw_to_db(0) == -90.0
    assert c.threshold_raw_to_db(180) == 0.0
    assert c.threshold_raw_to_db(220) == 20.0
    assert c.threshold_db_to_raw(20.0) == 220
    assert c.threshold_db_to_raw(5.0, max_db=c.GATE_THRESHOLD_MAX_DB) == 180
    assert c.threshold_db_to_raw(-200) == 0


def test_times() -> None:
    assert c.time_ms_to_raw(50) == 49
    assert c.time_raw_to_ms(499) == 500.0
    assert c.time_ms_to_raw(0.2) == 0
    assert c.time_ms_to_raw(5000, *c.RELEASE_RANGE_MS) == 2999
    assert len(c.COMPRESSOR_RATIOS) == 16


# --- delay -------------------------------------------------------------------------------------
def test_delay_uses_profile_sample_rate() -> None:
    assert DEFAULT_PROFILE.delay_sample_rate_hz == 96000
    assert c.delay_ms_to_raw(1.0) == 96
    assert c.delay_raw_to_ms(96) == 1.0
    assert c.delay_ms_to_raw(10_000) == 65280  # clamped to 680 ms
    assert c.delay_ms_to_raw(-1) == 0
    assert c.delay_ms_to_m(10.0) == pytest.approx(3.43)


# --- names -------------------------------------------------------------------------------------
def test_names() -> None:
    assert c.encode_name("Out1", 8) == b"Out1\x00\x00\x00\x00"
    assert c.encode_name("Forest", 14, b" ") == b"Forest        "
    assert c.decode_name(b"Forest        ") == "Forest"
    assert c.decode_name(b"InA\x00\x00\xff\x00\x00") == "InA"
    assert c.decode_name(b"A\x01B") == "A?B"


@pytest.mark.parametrize("name", ["fifteen chars!!", "café", "tab\there"])
def test_invalid_preset_names_are_rejected(name: str) -> None:
    with pytest.raises(ValueError, match="name"):
        c.validate_name(name, c.PRESET_NAME_LENGTH)
