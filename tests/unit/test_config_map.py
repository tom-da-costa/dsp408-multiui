"""Config blob layout, checked against a real DSP 408 dump (see the fixture's .meta.toml)."""

from dataclasses import replace
from pathlib import Path

import pytest

from dsp408_multiui.protocol import config_map as cm
from dsp408_multiui.protocol.profile import DEFAULT_PROFILE as P

FIXTURE = Path(__file__).parent.parent / "fixtures" / "config" / "forest_408.bin"


@pytest.fixture(scope="module")
def forest_blob() -> bytes:
    return FIXTURE.read_bytes()


@pytest.fixture(scope="module")
def forest(forest_blob: bytes) -> cm.RawConfig:
    return cm.decode_config(forest_blob)


def test_header(forest: cm.RawConfig) -> None:
    assert forest.marker == cm.MARKER_MODIFIED
    assert forest.preset_name == "Forest"


def test_channel_names_sit_at_fixed_offsets(forest: cm.RawConfig) -> None:
    assert [c.name for c in forest.inputs] == ["InA", "InB", "InC", "InD"]
    assert [c.name for c in forest.outputs] == [f"Out{i}" for i in range(1, 9)]


def test_input_fields(forest: cm.RawConfig) -> None:
    ina = forest.inputs[0]
    assert ina.gain == cm.UNITY_GAIN_RAW
    assert ina.gate == cm.RawGate(attack=0, release=99, hold=99, threshold=0)
    # GEQ band 20 (2 kHz) cut by 4.7 dB, all other bands flat
    assert ina.geq == (cm.EQ_FLAT_RAW,) * 20 + (73,) + (cm.EQ_FLAT_RAW,) * 10
    assert forest.inputs[2].geq[17:21] == (60, 60, 60, 90)
    assert ina.peq[0] == cm.RawPeqBand(gain=150, freq=188, q=0, type=0)  # +3 dB
    assert [b.freq for b in forest.inputs[1].peq] == list(cm.DEFAULT_INPUT_PEQ_FREQS)
    assert ina.crossover == cm.RawCrossover(hpf_freq=0, lpf_freq=300, hpf_slope=0, lpf_slope=0)
    assert [c.link for c in forest.inputs] == [1, 2, 4, 8]


def test_output_fields(forest: cm.RawConfig) -> None:
    out1, out2, out3 = forest.outputs[:3]
    assert [o.matrix for o in forest.outputs] == [15, 5, 5, 10, 10, 5, 10, 15]
    assert out1.crosspoints == (cm.UNITY_GAIN_RAW,) * 4
    # A real 3-way system: sub 25-80 Hz BW-24, low 80-161 Hz, mid 370 Hz-4.8 kHz LR-24
    assert out1.crossover == cm.RawCrossover(11, 61, 8, 8)
    assert out2.crossover == cm.RawCrossover(61, 91, 8, 3)
    assert out3.crossover == cm.RawCrossover(127, 238, 10, 3)
    assert out1.compressor == cm.RawCompressor(0, 49, 499, 0, 220)
    assert out1.limiter == cm.RawLimiter(49, 499, 0, 220)
    assert out3.peq[4] == cm.RawPeqBand(gain=160, freq=244, q=10, type=2)  # high shelf
    assert [b.freq for b in out1.peq] == list(cm.DEFAULT_OUTPUT_PEQ_FREQS)
    assert [o.link for o in forest.outputs] == [1 << i for i in range(8)]
    assert all(o.gain == cm.UNITY_GAIN_RAW for o in forest.outputs)


def test_roundtrip_is_byte_exact(forest_blob: bytes, forest: cm.RawConfig) -> None:
    assert cm.encode_config(forest) == forest_blob


def test_edit_changes_only_the_expected_bytes(forest_blob: bytes, forest: cm.RawConfig) -> None:
    outputs = list(forest.outputs)
    outputs[2] = replace(outputs[2], gain=200, mute=True, delay=960)
    edited = cm.encode_config(replace(forest, outputs=tuple(outputs)))
    changed = [i for i, (a, b) in enumerate(zip(forest_blob, edited, strict=True)) if a != b]
    base = cm.output_offset(2)
    # gain 280 -> 200 (both bytes), delay 0 -> 960 (both bytes), mute flag
    assert changed == [base + 96, base + 97, base + 98, base + 99, base + 100]
    assert cm.decode_config(edited).outputs[2].delay == 960


def test_unknown_bytes_are_preserved(forest_blob: bytes) -> None:
    blob = bytearray(forest_blob)
    blob[cm.TRAILER_BASE + 5] = 0xAB
    assert cm.encode_config(cm.decode_config(bytes(blob)))[cm.TRAILER_BASE + 5] == 0xAB


def test_pages(forest_blob: bytes) -> None:
    pages = cm.split_pages(forest_blob, P)
    assert len(pages) == 29
    assert [len(p) for p in pages] == [50] * 28 + [48]
    assert cm.join_pages(dict(enumerate(pages)), P) == forest_blob
    with pytest.raises(cm.ConfigError, match="missing"):
        cm.join_pages({0: pages[0]}, P)
    with pytest.raises(cm.ConfigError, match="bytes"):
        cm.join_pages({**dict(enumerate(pages)), 3: b"short"}, P)


def test_default_config_roundtrips() -> None:
    config = cm.default_config()
    assert config.marker == cm.MARKER_FACTORY
    assert config.image[:2] == b"\xff\x00"
    decoded = cm.decode_config(config.image)
    assert decoded == config
    assert [o.matrix for o in decoded.outputs] == [1, 2, 4, 8, 1, 2, 4, 8]


def test_layout_errors(forest: cm.RawConfig) -> None:
    with pytest.raises(cm.ConfigError):
        cm.decode_config(b"\x00" * 10)
    with pytest.raises(cm.ConfigError):
        cm.encode_config(replace(forest, inputs=forest.inputs[:3]))
    with pytest.raises(cm.ConfigError):
        cm.check_layout(P.with_overrides({"topology": {"output_count": 6}}))
    bad = replace(forest.outputs[0], peq=forest.outputs[0].peq[:2])
    with pytest.raises(cm.ConfigError, match="PEQ"):
        cm.encode_config(replace(forest, outputs=(bad, *forest.outputs[1:])))


@pytest.mark.parametrize(
    ("offset", "name"),
    [
        (0, "marker"),
        (5, "preset_name"),
        (16, "in0.name"),
        (16 + 16 + 40, "in0.geq[20]"),
        (16 + 78 + 6 + 4, "in0.peq[1].q"),
        (16 + 140 + 132, "in1.gain"),
        (cm.output_offset(0) + 8, "out0.matrix"),
        (cm.output_offset(0) + 13, "out0.crosspoints[1]"),
        (cm.output_offset(7) + 24 + 6 * 8 + 5, "out7.peq[8].type"),
        (cm.output_offset(2) + 86, "out2.compressor.threshold"),
        (cm.output_offset(2) + 100, "out2.mute (HYP)"),
        (cm.TRAILER_BASE + 3, "trailer[3]"),
    ],
)
def test_field_at(offset: int, name: str) -> None:
    assert cm.field_at(offset) == name


def test_every_offset_has_a_name() -> None:
    names = {cm.field_at(i) for i in range(cm.CONFIG_SIZE)}
    assert not any(".+" in n for n in names)
    with pytest.raises(ValueError, match="offset"):
        cm.field_at(cm.CONFIG_SIZE)


def test_diff_blobs(forest_blob: bytes) -> None:
    edited = bytearray(forest_blob)
    edited[cm.output_offset(0) + 96] = 0xC8
    assert cm.diff_blobs(forest_blob, bytes(edited)) == [
        (cm.output_offset(0) + 96, 0x18, 0xC8, "out0.gain")
    ]
    with pytest.raises(cm.ConfigError):
        cm.diff_blobs(b"", forest_blob)
