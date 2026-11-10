"""The simulator playing a DSP 206 or 204 (``tracks-dsp-sim --model``)."""

import asyncio
import contextlib
import socket
from pathlib import Path

import pytest

from tracks_dsp_controller.device.session import DeviceSession, DeviceStatus
from tracks_dsp_controller.protocol import commands as c
from tracks_dsp_controller.protocol import config_map as cm
from tracks_dsp_controller.protocol import responses as r
from tracks_dsp_controller.protocol.codecs import gain_db_to_raw
from tracks_dsp_controller.protocol.framing import FrameDecoder
from tracks_dsp_controller.protocol.meters import decode_meters, meter_data_length
from tracks_dsp_controller.protocol.profile import MODELS, ProtocolProfile, load_profile
from tracks_dsp_controller.simulator import Faults, SimulatedDevice, SimulatorServer, apply_scenario
from tracks_dsp_controller.simulator import cli as sim_cli
from tracks_dsp_controller.simulator.models import SIM_MODELS
from tracks_dsp_controller.simulator.scenarios import SCENARIOS
from tracks_dsp_controller.state.store import StateStore

FIXTURES = Path(__file__).parents[1] / "fixtures"
DSP206_DUMP = FIXTURES / "config" / "dsp206_capture.bin"
DSP408_DUMP = FIXTURES / "config" / "dsp408_u08.bin"


def device_for(model: str) -> SimulatedDevice:
    return SimulatedDevice(load_profile(model=model), model=SIM_MODELS[model], clock=lambda: 0.0)


def ask(device: SimulatedDevice, request: c.Request) -> r.Response | None:
    reply = device.handle(request.encode(device.profile))
    assert not reply.crash
    return None if reply.response is None else r.decode_response(reply.response.encode())


def read_config(device: SimulatedDevice) -> cm.RawConfig:
    p = device.profile
    pages = {}
    for page in range(p.page_count):
        reply = ask(device, c.ReadConfigPage(page))
        assert isinstance(reply, r.ConfigPage)
        pages[page] = reply.data
    return cm.decode_config(cm.join_pages(pages, p), cm.layout_for(p))


def test_every_profile_model_has_a_simulator_model() -> None:
    assert SIM_MODELS.keys() == MODELS.keys()
    assert not SIM_MODELS["204"].replies_observed
    assert SIM_MODELS["206"].replies_observed


@pytest.mark.parametrize(("model", "inputs", "outputs"), [("206", 2, 6), ("204", 2, 4)])
def test_init_sequence_and_config(model: str, inputs: int, outputs: int) -> None:
    device = device_for(model)
    assert ask(device, c.Handshake()) == r.HandshakeReply(b"\x19")
    info = ask(device, c.GetDeviceInfo())
    assert isinstance(info, r.DeviceInfo)
    assert info.model == f"DSP{model}"
    assert ask(device, c.GetPresetHeader()) == r.PresetHeader(bytes(20))
    config = read_config(device)
    assert (len(config.inputs), len(config.outputs)) == (inputs, outputs)
    assert config == device.live
    meters = ask(device, c.PollMeters())
    assert isinstance(meters, r.MeterFrame)
    assert len(meters.data) == meter_data_length(device.profile) == 38
    assert len(decode_meters(meters.data, device.profile).levels_db) == inputs + outputs


def test_206_writes_use_sequential_channel_indices() -> None:
    device = device_for("206")
    out1 = device.profile.input_count  # protocol index 2
    assert ask(device, c.SetGain(out1, gain_db_to_raw(-6.0))) == r.Ack()
    assert ask(device, c.SetMatrix(out1, 0b10)) == r.Ack()
    assert ask(device, c.PrepareLink(out1, out1 + 2)) == r.Ack()  # 2a 02 04: Out1 -> Out3
    live = device.live
    assert live.outputs[0].gain == gain_db_to_raw(-6.0)
    assert live.outputs[2].gain == gain_db_to_raw(-6.0)  # copied by the link
    assert live.outputs[2].matrix == 0b01  # routing is not copied
    with pytest.raises(c.CommandError):
        c.SetGain(8, 280).encode(device.profile)  # no channel 8 on a 206
    assert device.handle(bytes.fromhex("34 08 18 01")).response is None  # ignored
    name = ask(device, c.SetPresetName("Show"))
    assert name == r.Ack(b"\x00" + b"Show".ljust(14))  # the 206 echoes the name after 00


def test_preset_layout_must_match_the_model() -> None:
    device = device_for("206")
    with pytest.raises(ValueError, match="does not fit"):
        device.set_preset(1, cm.default_config("x"))  # a 4 x 8 config
    device.set_preset(1, cm.decode_config(DSP206_DUMP.read_bytes(), device.layout))


@pytest.mark.parametrize("model", ["206", "204"])
@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_scenarios_fit_every_model(model: str, scenario: str) -> None:
    device = device_for(model)
    apply_scenario(scenario, device, Faults())
    assert len(device.meters.render(device.live)) == 38
    if scenario == "demo":
        expected = "Demo 3-way" if model == "206" else "Demo 2-way"
        assert device.presets[1].preset_name == expected


def test_cli_model_option(monkeypatch: pytest.MonkeyPatch) -> None:
    args = sim_cli.build_parser().parse_args(["--model", "206", "--preset", f"3={DSP206_DUMP}"])
    device, _, _ = sim_cli.build_device(args, load_profile(model="206"))
    assert (device.model.key, device.identity) == ("206", "DSP206 V0104P")
    assert device.active_slot == 3
    assert device.live.outputs[0].name == "TEST"
    monkeypatch.setenv("TRACKS_DSP_SIM_MODEL", "204")
    assert sim_cli.build_parser().parse_args([]).model == "204"
    args = sim_cli.build_parser().parse_args(["--model", "206", "--preset", f"3={DSP408_DUMP}"])
    with pytest.raises(ValueError, match="expected 928"):
        sim_cli.build_device(args, load_profile(model="206"))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


async def test_server_answers_from_the_address_it_was_sent_to() -> None:
    device = device_for("206")
    server = SimulatorServer(device, host="127.0.0.1", port=0)
    await server.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", server.bound_port)
        decoder = FrameDecoder()
        for dst in (0x02, 0x01):
            writer.write(bytes.fromhex(f"10 02 00 {dst:02x} 01 13 10 03") + bytes([0x13 ^ dst]))
            await writer.drain()
            frames = []
            while not frames:
                frames = decoder.feed(await reader.read(4096))
            assert (frames[0].src, frames[0].dst) == (dst, 0x00)
            assert frames[0].payload[1:] == b"DSP206 V0104P"
        writer.close()
    finally:
        await server.stop()


@pytest.mark.parametrize("model", ["206", "204"])
async def test_backend_session_against_a_simulated_model(model: str) -> None:
    """The backend, given the model's profile, drives the simulated device over TCP."""
    profile: ProtocolProfile = load_profile(model=model)
    device = device_for(model)
    device.timing.recall_s = device.timing.store_s = 0.0
    server = SimulatorServer(device, host="127.0.0.1", port=free_port())
    await server.start()
    session = DeviceSession(
        "127.0.0.1",
        server.bound_port,
        profile,
        StateStore(),
        meter_rate_hz=10,
        reconnect_min_s=0.05,
        reconnect_max_s=0.2,
    )
    try:
        await session.start()
        await session.wait_online(5)
        assert session.status is DeviceStatus.ONLINE
        state = session.store.state
        assert (len(state.inputs), len(state.outputs)) == (2, profile.output_count)
        await session.write("outputs.0.gain_db", -3.0, "test")
        assert device.live.outputs[0].gain == gain_db_to_raw(-3.0)
    finally:
        await session.stop()
        with contextlib.suppress(Exception):
            await server.stop()
