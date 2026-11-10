from pathlib import Path

import pytest

from tracks_dsp_controller.protocol.profile import (
    DEFAULT_PROFILE,
    CompressorLayout,
    MeterFormat,
    ProfileError,
    ProtocolProfile,
    load_profile,
)


def test_default_profile_values() -> None:
    p = DEFAULT_PROFILE
    assert p.name == "dsp408-default"
    assert (p.input_count, p.output_count, p.channel_count) == (4, 8, 12)
    assert p.preset_count == 20
    assert p.config_size == 1448
    assert p.freq_steps == 300
    assert p.q_steps == 100
    assert p.meter_format is MeterFormat.FLOAT32
    assert p.compressor_layout is CompressorLayout.WIDE
    assert len(p.peq_types) == 9
    assert len(p.slopes) == 21
    assert p.slopes[0] == "Off"
    assert p.slopes[10] == "LR-24"
    assert (p.meter_tail_comp_byte, p.meter_tail_limit_byte, p.meter_tail_clip_byte) == (0, 1, None)
    assert p.meter_clip_db == 12.0
    assert p.meter_reference == 0.1
    assert p.slow_command_timeout_s == 10.0


def test_channel_helpers() -> None:
    p = DEFAULT_PROFILE
    assert p.is_input(0)
    assert p.is_input(3)
    assert not p.is_input(4)
    assert p.is_output(4)
    assert p.is_output(11)
    assert not p.is_output(12)
    assert p.peq_band_count(0) == 8
    assert p.peq_band_count(4) == 9
    assert p.page_length(0) == 50
    assert p.page_length(28) == 48
    with pytest.raises(ValueError, match="page"):
        p.page_length(29)


def test_override_file(tmp_path: Path) -> None:
    path = tmp_path / "p.toml"
    path.write_text(
        'name = "mini-test"\n'
        "[codecs]\nfreq_steps = 1000\ncompressor_layout = 'narrow'\n"
        "[meters]\nformat = 'level24'\ntail_length = 3\ntail_comp_byte = 2\n"
    )
    p = load_profile(path)
    assert p.name == "mini-test"
    assert p.freq_steps == 1000
    assert p.compressor_layout is CompressorLayout.NARROW
    assert p.meter_format is MeterFormat.LEVEL24
    assert p.meter_tail_comp_byte == 2
    assert p.q_steps == 100  # untouched keys keep the default


@pytest.mark.parametrize(
    "document",
    [
        {"bogus": {}},
        {"codecs": {"bogus": 1}},
        {"codecs": {"meter_format": "float16"}},  # key in the wrong section
        {"meters": {"format": "mp3"}},
        {"topology": {"input_count": 0}},
        {"topology": {"output_count": 9}},
        {"meters": {"tail_limit_byte": 5}},
        {"codecs": {"freq_min_hz": 30000.0}},
        {"codecs": {"q_min": 0}},
        {"frame": {"host_dst": 300}},
    ],
)
def test_invalid_overrides(document: dict[str, object]) -> None:
    with pytest.raises((ProfileError, ValueError)):
        DEFAULT_PROFILE.with_overrides(document)  # type: ignore[arg-type]


def test_builtin_dataclass_defaults_are_valid() -> None:
    assert ProtocolProfile().channel_count == 12
