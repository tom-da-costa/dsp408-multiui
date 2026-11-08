from dataclasses import replace

import pytest

from dsp408_multiui.protocol import commands as c
from dsp408_multiui.protocol import config_map as cm
from dsp408_multiui.protocol import responses as r
from dsp408_multiui.protocol.meters import decode_meters
from dsp408_multiui.protocol.profile import DEFAULT_PROFILE as P
from dsp408_multiui.simulator import Faults, SimulatedDevice, apply_scenario
from dsp408_multiui.simulator.meters import Shape, Source


@pytest.fixture
def device() -> SimulatedDevice:
    return SimulatedDevice(P, clock=lambda: 0.0)


def ask(device: SimulatedDevice, request: c.Request) -> r.Response | None:
    reply = device.handle(request.encode(P))
    assert not reply.crash
    if reply.response is None:
        return None
    # Go through the wire format to check that the response encodes cleanly.
    return r.decode_response(reply.response.encode())


def read_config(device: SimulatedDevice) -> cm.RawConfig:
    pages = {}
    for page in range(P.page_count):
        reply = ask(device, c.ReadConfigPage(page))
        assert isinstance(reply, r.ConfigPage)
        assert reply.page == page
        pages[page] = reply.data
    return cm.decode_config(cm.join_pages(pages, P))


def test_init_sequence(device: SimulatedDevice) -> None:
    assert ask(device, c.Handshake()) == r.HandshakeReply(bytes((20,)))
    info = ask(device, c.GetDeviceInfo())
    assert isinstance(info, r.DeviceInfo)
    assert info.model == "DSP408"
    assert isinstance(ask(device, c.GetStatus()), r.Status)
    assert isinstance(ask(device, c.GetPresetHeader()), r.PresetHeader)
    assert ask(device, c.GetActivePreset()) == r.ActivePreset(0)
    names = [ask(device, c.GetPresetName(i)) for i in range(20)]
    assert names[0] == r.PresetName(0, "Default Preset")
    assert read_config(device).preset_name == "Default Preset"
    assert ask(device, c.Activate()) == r.Ack()


def test_every_request_gets_the_declared_response(device: SimulatedDevice) -> None:
    requests: list[c.Request] = [
        c.Handshake(),
        c.GetDeviceInfo(),
        c.GetStatus(),
        c.GetPresetHeader(),
        c.GetActivePreset(),
        c.Activate(),
        c.PollMeters(),
        c.GetPresetName(3),
        c.ReadConfigPage(5),
        c.SubmitPin("1234"),
        c.SetGain(0, 200),
        c.SetMute(1, True),
        c.SetPhase(4, True),
        c.SetPeqBypass(4, True),
        c.SetMatrix(4, 3),
        c.SetGeqBand(0, 5, 100),
        c.SetPeqBand(4, 2, 150, 100, 20, 1, True),
        c.SetHighPass(4, 60, 8),
        c.SetLowPass(4, 200, 10),
        c.SetDelay(5, 960),
        c.SetCompressor(5, 7, 10, 100, 2, 170),
        c.SetLimiter(5, 5, 50, 0, 180),
        c.SetGate(2, 1, 2, 30, 40),
        c.SetChannelName(6, "Sub"),
        c.SetPresetName("Test"),
    ]
    for request in requests:
        reply = ask(device, request)
        assert reply is not None
        assert reply.OPCODE == request.RESPONSE, request


def test_writes_show_up_in_the_config(device: SimulatedDevice) -> None:
    for request in [
        c.SetGain(4, 200),
        c.SetMute(5, True),
        c.SetPhase(0, True),
        c.SetDelay(6, 960),
        c.SetMatrix(7, 0b1010),
        c.SetHighPass(4, 61, 8),
        c.SetLowPass(4, 91, 3),
        c.SetPeqBand(8, 3, 150, 120, 30, 2, False),
        c.SetGeqBand(1, 20, 73),
        c.SetCompressor(9, 5, 9, 99, 3, 170),
        c.SetLimiter(9, 4, 40, 0, 190),
        c.SetGate(3, 0, 50, 20, 60),
        c.SetChannelName(11, "MonR"),
    ]:
        assert ask(device, request) == r.Ack()
    config = read_config(device)
    assert config.marker == cm.MARKER_MODIFIED
    out = config.outputs
    assert out[0].gain == 200
    assert out[1].mute
    assert config.inputs[0].phase
    assert out[2].delay == 960
    assert out[3].matrix == 0b1010
    assert out[0].crossover == cm.RawCrossover(61, 91, 8, 3)
    assert out[4].peq[3] == cm.RawPeqBand(150, 120, 30, 2)
    assert config.inputs[1].geq[20] == 73
    assert out[5].compressor == cm.RawCompressor(5, 9, 99, 3, 170)
    assert out[5].limiter == cm.RawLimiter(4, 40, 0, 190)
    assert config.inputs[3].gate == cm.RawGate(0, 50, 20, 60)
    assert out[7].name == "MonR"


def test_bypass_and_mute_live_in_the_trailer_masks(device: SimulatedDevice) -> None:
    ask(device, c.SetPeqBand(4, 1, 120, 50, 35, 0, True))
    ask(device, c.SetPeqBypass(5, True))
    ask(device, c.SetMute(2, True))
    blob = device.config_blob
    assert blob[cm.BAND_BYPASS_BASE + 2 * 4] == 0b10
    assert blob[cm.OUTPUT_PEQ_BYPASS_MASK] == 0b10
    assert blob[cm.INPUT_MUTE_MASK] == 0b100
    config = read_config(device)
    assert config.outputs[0].peq[1].bypass
    assert config.outputs[1].peq_bypass
    assert config.inputs[2].mute


def test_linked_channels_follow_writes_like_the_408(device: SimulatedDevice) -> None:
    # Link Out1+Out5 the way the 408 stores it: mask on the first member, 0 on the other.
    outputs = list(device.live.outputs)
    outputs[0] = replace(outputs[0], link=0x11)
    outputs[4] = replace(outputs[4], link=0)
    device.live = replace(device.live, outputs=tuple(outputs))
    ask(device, c.SetGain(8, 200))  # written on the slave (Out5)
    ask(device, c.SetPeqBand(4, 2, 100, 50, 20, 1, True))
    ask(device, c.SetMute(4, True))
    ask(device, c.SetChannelName(4, "Solo"))  # names and matrix are not copied
    ask(device, c.SetMatrix(4, 0b1000))
    out1, out5 = read_config(device).outputs[0], read_config(device).outputs[4]
    assert (out1.gain, out5.gain) == (200, 200)
    assert out1.peq[2] == out5.peq[2] == cm.RawPeqBand(100, 50, 20, 1, True)
    assert (out1.mute, out5.mute) == (True, True)
    assert (out1.name, out5.name) == ("Solo", "Out5")
    assert (out1.matrix, out5.matrix) == (0b1000, 0b0001)
    assert read_config(device).outputs[1].gain == cm.UNITY_GAIN_RAW


def test_pages_and_meters_need_the_init_sequence(device: SimulatedDevice) -> None:
    device.on_connect()
    assert device.handle(c.PollMeters().encode(P)).response is None
    assert device.handle(c.ReadConfigPage(0).encode(P)).response is None
    assert isinstance(ask(device, c.SetGain(4, 200)), r.Ack)  # writes still work
    ask(device, c.Handshake())
    assert isinstance(ask(device, c.PollMeters()), r.MeterFrame)


def test_store_and_recall(device: SimulatedDevice) -> None:
    ask(device, c.SetGain(4, 123))
    # the 408 echoes the name in its ACK
    assert ask(device, c.SetPresetName("My Show")) == r.Ack(b"\x01My Show       ")
    reply = device.handle(c.StorePreset(3).encode(P))
    assert reply.response == r.Ack()
    assert reply.delay_s == device.timing.store_s
    assert ask(device, c.GetPresetName(2)) == r.PresetName(2, "My Show")
    assert ask(device, c.GetActivePreset()) == r.ActivePreset(3)

    reply = device.handle(c.RecallPreset(0).encode(P))
    assert reply.delay_s == device.timing.recall_s
    assert read_config(device).outputs[0].gain == cm.UNITY_GAIN_RAW
    ask(device, c.RecallPreset(3))
    config = read_config(device)
    assert config.outputs[0].gain == 123
    assert config.preset_name == "My Show"


def test_store_to_f00_is_ignored(device: SimulatedDevice) -> None:
    payload = bytes((c.Opcode.STORE_PRESET, 0))
    reply = device.handle(payload)
    assert reply.response is None
    assert not reply.crash
    assert device.presets[0].preset_name == "Default Preset"


def test_long_preset_name_crashes_the_firmware(device: SimulatedDevice) -> None:
    payload = bytes((c.Opcode.SET_PRESET_NAME,)) + b"x" * 15
    assert device.handle(payload).crash


@pytest.mark.parametrize("payload", ["", "ff", "34 00", "39 03 11"])
def test_invalid_requests_get_no_answer(device: SimulatedDevice, payload: str) -> None:
    reply = device.handle(bytes.fromhex(payload))
    assert reply.response is None
    assert not reply.crash


def meters(device: SimulatedDevice) -> tuple[float | None, ...]:
    reply = ask(device, c.PollMeters())
    assert isinstance(reply, r.MeterFrame)
    return decode_meters(reply.data, P).levels_db


def test_meters_follow_parameters(device: SimulatedDevice) -> None:
    device.meters.sources = [Source(Shape.STEADY, -20.0) for _ in range(4)]
    levels = meters(device)
    assert levels[0] == pytest.approx(-20.0, abs=0.05)
    assert levels[4] == pytest.approx(-20.0, abs=0.05)  # Out1 <- In A (default matrix)

    ask(device, c.SetGain(0, 220))  # In A -6 dB
    ask(device, c.SetMatrix(4, 0b0011))  # Out1 <- In A + In B
    levels = meters(device)
    assert levels[0] == pytest.approx(-26.0, abs=0.05)
    # power sum of -26 and -20 dB
    assert levels[4] == pytest.approx(-19.03, abs=0.05)

    ask(device, c.SetMute(4, True))
    ask(device, c.SetMute(1, True))
    levels = meters(device)
    assert levels[4] == P.meter_floor_db
    assert levels[1] == P.meter_floor_db


def test_limiter_flag_follows_threshold(device: SimulatedDevice) -> None:
    device.meters.sources[0] = Source(Shape.STEADY, -3.0)
    reply = ask(device, c.PollMeters())
    assert isinstance(reply, r.MeterFrame)
    assert decode_meters(reply.data, P).limit == (False,) * 8
    ask(device, c.SetLimiter(4, 0, 0, 0, 170))  # Out1 limiter at -5 dB
    reply = ask(device, c.PollMeters())
    assert isinstance(reply, r.MeterFrame)
    assert decode_meters(reply.data, P).limit == (True,) + (False,) * 7


def test_nan_meter_frame(device: SimulatedDevice) -> None:
    device.meters.nan_next = True
    assert all(level is None for level in meters(device))
    assert all(level is not None for level in meters(device))


@pytest.mark.parametrize("name", ["demo", "silent", "clipping", "stress"])
def test_scenarios(name: str) -> None:
    device = SimulatedDevice(P, clock=lambda: 1.0)
    faults = Faults()
    apply_scenario(name, device, faults)
    levels = meters(device)
    assert len(levels) == 12
    if name == "silent":
        assert all(level == P.meter_floor_db for level in levels)
    if name == "clipping":
        reply = ask(device, c.PollMeters())
        assert isinstance(reply, r.MeterFrame)
        assert any(decode_meters(reply.data, P).clip[:4])
    if name == "stress":
        assert faults.drop_rate > 0
    if name == "demo":
        assert device.active_slot == 1
        assert read_config(device).preset_name == "Demo 3-way"


def test_unknown_scenario() -> None:
    with pytest.raises(ValueError, match="unknown scenario"):
        apply_scenario("nope", SimulatedDevice(P), Faults())


def test_set_preset_bounds(device: SimulatedDevice) -> None:
    with pytest.raises(ValueError, match="slot"):
        device.set_preset(21, cm.default_config())
