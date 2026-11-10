"""The protocol layer against frames and config reads captured from a real DSP 206.

Fixtures from FlexiFlizz/t.racks-DSP-control (GPL-3.0), see the README attribution table.
"""

from dataclasses import replace
from pathlib import Path

import pytest

from tracks_dsp_controller.protocol import commands as c
from tracks_dsp_controller.protocol import config_map as cm
from tracks_dsp_controller.protocol import responses as r
from tracks_dsp_controller.protocol.codecs import gain_raw_to_db
from tracks_dsp_controller.protocol.framing import Frame, FrameDecoder, checksum, encode_frame
from tracks_dsp_controller.protocol.meters import decode_meters, encode_meters, meter_data_length
from tracks_dsp_controller.protocol.profile import ProfileError, load_profile
from tracks_dsp_controller.tools import probe

FIXTURES = Path(__file__).parents[1] / "fixtures"
P206 = load_profile(model="206")
P204 = load_profile(model="204")
L206 = cm.layout_for(P206)
BLOB = (FIXTURES / "config" / "dsp206_capture.bin").read_bytes()
LINKED = (FIXTURES / "config" / "dsp206_capture_linked.bin").read_bytes()


def wire_frames() -> list[tuple[str, bytes]]:
    """(direction, frame) pairs of tests/fixtures/dsp206/frames.txt; '>' = host to device."""
    lines = (FIXTURES / "dsp206" / "frames.txt").read_text().splitlines()
    return [(line[0], bytes.fromhex(line[2:])) for line in lines if line[:1] in "<>"]


def test_model_profiles() -> None:
    assert (P206.model, P206.host_dst, P206.input_count, P206.output_count) == ("DSP206", 2, 2, 6)
    assert (P206.page_count, P206.config_size) == (19, 928)
    assert (P204.model, P204.input_count, P204.output_count, P204.config_size) == (
        "DSP204",
        2,
        4,
        724,
    )
    assert P206.meter_slot(0) == 0
    assert P206.meter_slot(1) == 1
    assert P206.meter_slot(2) == 4
    assert P206.meter_slot(7) == 9
    with pytest.raises(ValueError, match="channel"):
        P206.meter_slot(8)
    with pytest.raises(ProfileError, match="unknown model"):
        load_profile(model="306")
    with pytest.raises(ProfileError, match="slot"):
        replace(P206, meter_output_slots=4)


def test_layout_sizes_follow_the_channel_counts() -> None:
    assert cm.LAYOUT_408.size == cm.CONFIG_SIZE == 1448
    assert (cm.LAYOUT_408.output_record, cm.LAYOUT_408.trailer_base) == (104, 1408)
    assert (L206.size, L206.output_base, L206.output_record) == (928, 296, 100)
    assert L206.trailer_base == 896
    assert cm.layout_for(P204).size == 724
    assert cm.check_layout(P206) == L206
    with pytest.raises(cm.ConfigError, match="need 928"):
        cm.check_layout(replace(P206, last_page_size=48))
    with pytest.raises(cm.ConfigError, match="bands"):
        cm.check_layout(replace(P206, geq_bands=15))


def test_every_captured_frame_decodes_with_its_checksum() -> None:
    frames = wire_frames()
    decoder = FrameDecoder()
    decoded = decoder.feed(b"".join(frame for _, frame in frames))
    assert len(decoded) == len(frames)
    assert decoder.bad_frames == 0
    for (direction, wire), frame in zip(frames, decoded, strict=True):
        assert frame.from_device == (direction == "<")
        assert frame.encode() == wire  # SRC and DST are part of the checksum
    assert checksum(b"\x40", 0x00, 0x02) == 0x42  # 10 02 00 02 01 40 10 03 42
    assert encode_frame(b"\x40", dst=0x02) == bytes.fromhex("10 02 00 02 01 40 10 03 42")


def test_init_replies_parse() -> None:
    replies = [Frame(f[2], f[3], f[5:-3]) for d, f in wire_frames() if d == "<"]
    responses = [r.decode_response(frame.payload) for frame in replies]
    assert r.HandshakeReply(b"\x19") in responses
    assert r.DeviceInfo("DSP206 V0104P") in responses
    info = next(x for x in responses if isinstance(x, r.DeviceInfo))
    assert info.model == "DSP206"
    assert r.ActivePreset(0) in responses
    assert r.PresetName(0, "Default Preset") in responses


def test_requests_decode_with_the_206_profile() -> None:
    requests = [f[5:-3] for d, f in wire_frames() if d == ">"]
    decoded = [c.decode_request(payload, P206) for payload in requests]
    assert c.SetChannelName(2, "TEST") in decoded  # Out1 is protocol index 2 on a 206
    assert c.ReadConfigPage(0) in decoded
    peq = next(x for x in decoded if isinstance(x, c.SetPeqBand))
    assert (peq.channel, peq.band) == (2, 0)


def test_config_blob_of_a_real_206() -> None:
    config = cm.decode_config(BLOB, L206)
    assert config.preset_name == "Default Preset"
    assert [ch.name for ch in config.inputs] == ["InA", "InB"]
    assert [ch.name for ch in config.outputs] == ["TEST", "Out2", "Out3", "Out4", "Out5", "Out6"]
    out1 = config.outputs[0]
    assert gain_raw_to_db(out1.gain) == -6.0
    assert out1.delay == 960  # 10 ms at 96 kHz
    assert (out1.crossover.hpf_freq, out1.crossover.lpf_freq) == (71, 230)
    assert (out1.crossover.hpf_slope, out1.crossover.lpf_slope) == (8, 8)
    assert (out1.peq[0].gain, out1.peq[0].freq, out1.peq[0].q) == (90, 140, 28)
    # The capture's "30 02 00 00 31 00 f3 01 00 00 a0 00" and "3f 02 31 00 f3 01 00 00 b4 00"
    assert out1.compressor == cm.RawCompressor(0, 49, 499, 0, 160)
    assert out1.limiter == cm.RawLimiter(49, 499, 0, 180)
    assert out1.matrix == 0b10
    assert out1.crosspoints == (280, 280)
    assert cm.link_group([o.link for o in config.outputs], 0) == (0, 1)  # Out1 + Out2
    assert [ch.link for ch in config.inputs] == [1, 2]
    assert cm.encode_config(config) == BLOB


def test_link_copy_changes_only_the_slave_record() -> None:
    """2a 02 04: Out3 takes Out1's settings except its name, routing and link mask."""
    changed = {name.split(".")[0] for _, _, _, name in cm.diff_blobs(BLOB, LINKED, L206)}
    assert changed == {"out2"}
    before, after = cm.decode_config(BLOB, L206), cm.decode_config(LINKED, L206)
    source, target = before.outputs[0], after.outputs[2]
    for name in ("crossover", "peq", "compressor", "limiter", "gain", "delay", "phase"):
        assert getattr(target, name) == getattr(source, name), name
    assert (target.name, target.matrix) == (before.outputs[2].name, before.outputs[2].matrix)
    assert cm.field_at(L206.output_offset(2) + L206.out_gain, L206) == "out2.gain"
    assert cm.field_at(L206.input_peq_bypass_mask, L206) == "inputs.peq_bypass_mask"
    assert cm.field_at(L206.band_bypass_base + 4, L206) == "out0.peq_band_bypass_mask"


def test_default_configs_of_every_model_round_trip() -> None:
    for profile in (P206, P204):
        layout = cm.layout_for(profile)
        config = cm.default_config("x", layout)
        assert len(config.image) == layout.size
        assert cm.decode_config(config.image, layout) == config
        assert len(cm.split_pages(config.image, profile)) == profile.page_count
    with pytest.raises(cm.ConfigError, match="expected 928"):
        cm.decode_config(bytes(1448), L206)


def test_meter_frame_of_a_real_206() -> None:
    reply = next(f for d, f in wire_frames() if d == "<" and f[5] == 0x40)
    data = reply[6:-3]
    assert len(data) == meter_data_length(P206) == 38  # same frame size as the 408
    reading = decode_meters(data, P206)
    assert len(reading.levels_db) == 8
    # No signal in the capture: read as float32 (like the 408), every channel sits at the noise
    # floor, about -86 dBu (-106 dBFS). The float16 reading of t.racks-DSP-control would give a
    # constant -7.6 dBFS on an idle device.
    assert all(level is not None and -90 <= level < -80 for level in reading.levels_db)
    assert reading.limit == (False,) * 6
    # Encoding puts the 8 channels in their slots and leaves In C-D and Out 7-8 at zero.
    frame = encode_meters([-10.0] * 8, P206)
    assert frame[6:12] == bytes(6)
    assert frame[30:36] == bytes(6)
    assert decode_meters(frame, P206).levels_db == pytest.approx([-10.0] * 8, abs=0.01)


def test_probe_shows_each_channel_at_its_meter_slot() -> None:
    frame = encode_meters([-10.0] * 2 + [None] * 6, P206, limit=[True] + [False] * 5)
    lines = probe.format_meters(frame, P206).splitlines()
    out1 = next(line for line in lines if line.startswith("Out1"))
    assert out1.split()[1:4] == list(frame[12:15].hex(" ").split())  # slot 4
    assert next(line for line in lines if line.startswith("tail")) == "tail    00 01"
    assert "limit   Out1" in lines
