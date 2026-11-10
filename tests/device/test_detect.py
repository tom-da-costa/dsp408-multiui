"""Automatic detection of the DSP model (408, 206, 204) by the backend."""

import asyncio
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tracks_dsp_controller import cli
from tracks_dsp_controller.device import reader
from tracks_dsp_controller.device.session import DeviceSession, DeviceStatus
from tracks_dsp_controller.device.transport import TransportTimeoutError
from tracks_dsp_controller.protocol import commands as c
from tracks_dsp_controller.protocol import responses as r
from tracks_dsp_controller.protocol.profile import (
    DEFAULT_PROFILE,
    ProtocolProfile,
    detect_model,
    load_profile,
)
from tracks_dsp_controller.server.app import AppContext, create_app
from tracks_dsp_controller.server.settings import ServerConfig
from tracks_dsp_controller.simulator import SimulatedDevice, SimulatorServer
from tracks_dsp_controller.simulator.models import SIM_MODELS
from tracks_dsp_controller.state.store import StateStore


def test_detect_model() -> None:
    assert detect_model("DSP408 V0104P") == "408"
    assert detect_model("DSP206 V0104P") == "206"
    assert detect_model("DSP 204 V0104P") == "204"
    assert detect_model("FIR408 V0100") is None  # own config layout: not a DSP 408
    assert detect_model("") is None


async def simulated(model: str, identity: str = "") -> SimulatorServer:
    device = SimulatedDevice(load_profile(model=model), model=SIM_MODELS[model], identity=identity)
    device.timing.recall_s = device.timing.store_s = 0.0
    server = SimulatorServer(device, host="127.0.0.1", port=0)
    await server.start()
    return server


def session_for(server: SimulatorServer, model: str | None) -> DeviceSession:
    return DeviceSession(
        "127.0.0.1",
        server.bound_port,
        DEFAULT_PROFILE,
        StateStore(),
        meter_rate_hz=10,
        reconnect_min_s=0.05,
        reconnect_max_s=0.1,
        model=model,
    )


@pytest.fixture
async def stop_later() -> AsyncIterator[list[Any]]:
    things: list[Any] = []
    yield things
    for thing in reversed(things):
        await thing.stop()


@pytest.mark.parametrize(
    ("model", "inputs", "outputs"), [("408", 4, 8), ("206", 2, 6), ("204", 2, 4)]
)
async def test_auto_detects_every_model(
    model: str, inputs: int, outputs: int, stop_later: list[Any]
) -> None:
    server = await simulated(model)
    session = session_for(server, "auto")
    stop_later += [server, session]
    switched: list[ProtocolProfile] = []
    session.on_profile(switched.append)
    await session.start()
    await session.wait_online(5)
    assert session.model_key == model
    assert session.profile.host_dst == (2 if model == "206" else 1)
    state = session.store.state
    assert (len(state.inputs), len(state.outputs)) == (inputs, outputs)
    assert len(switched) == (0 if model == "408" else 1)  # the 408 profile is kept as given
    assert session.model_tested is (model == "408")
    await session.write(f"outputs.{outputs - 1}.gain_db", -4.0, "test")
    server_device = server.device
    assert server_device.live.outputs[outputs - 1].gain == 240


async def test_explicit_model_must_match(stop_later: list[Any]) -> None:
    server = await simulated("206")
    session = session_for(server, "408")
    stop_later += [server, session]
    await session.start()
    for _ in range(100):
        if session.last_error:
            break
        await asyncio.sleep(0.02)
    assert session.status is DeviceStatus.OFFLINE
    assert session.last_error is not None
    assert "not a DSP 408" in session.last_error


async def test_unknown_identity_is_refused_in_auto_but_not_with_a_model(
    stop_later: list[Any],
) -> None:
    server = await simulated("206", identity="XYZ999 V1")
    auto = session_for(server, "auto")
    stop_later += [server, auto]
    await auto.start()
    for _ in range(100):
        if auto.last_error:
            break
        await asyncio.sleep(0.02)
    assert auto.last_error is not None
    assert "unknown device 'XYZ999 V1'" in auto.last_error
    await auto.stop()
    forced = session_for(server, "206")  # the user says what it is
    stop_later.append(forced)
    await forced.start()
    await forced.wait_online(5)
    assert len(forced.store.state.outputs) == 6


def test_unknown_model_key() -> None:
    with pytest.raises(ValueError, match="unknown model"):
        DeviceSession("h", 1, DEFAULT_PROFILE, StateStore(), model="306")


class OnlyOnAddress2:
    """A device that ignores frames sent to address 0x01."""

    def __init__(self) -> None:
        self.profile = DEFAULT_PROFILE
        self.tried: list[int] = []

    async def request(self, request: c.Request, timeout: float | None = None) -> r.Response:
        self.tried.append(self.profile.host_dst)
        if self.profile.host_dst != 0x02:
            raise TransportTimeoutError("no answer")
        if isinstance(request, c.Handshake):
            return r.HandshakeReply(b"\x19")
        return r.DeviceInfo("DSP206 V0104P")


async def test_identity_falls_back_to_the_other_address() -> None:
    conn = OnlyOnAddress2()
    assert await reader.read_identity(conn) == "DSP206 V0104P"
    assert conn.tried[0] == 0x01
    assert conn.profile.host_dst == 0x02


async def test_identity_gives_up_after_every_address() -> None:
    conn = OnlyOnAddress2()
    conn.profile = load_profile(model="204").with_overrides({"frame": {"host_dst": 0x05}})

    async def silent(request: c.Request, timeout: float | None = None) -> r.Response:
        raise TransportTimeoutError("no answer")

    conn.request = silent  # type: ignore[method-assign]
    with pytest.raises(TransportTimeoutError):
        await reader.read_identity(conn)
    assert conn.profile.host_dst == 0x05  # restored


def wait_online(app: Any) -> AppContext:
    ctx: AppContext = app.state.ctx
    deadline = time.monotonic() + 5
    while ctx.session.status.value != "online" and time.monotonic() < deadline:
        time.sleep(0.02)
    return ctx


def test_demo_of_a_206_serves_its_profile(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html><title>UI</title>")
    config = ServerConfig(demo=True, pin="4321", model="206")
    app = create_app(config, DEFAULT_PROFILE, web_dir=tmp_path)
    with TestClient(app) as client:
        ctx = wait_online(app)
        assert ctx.session.model_key == "206"
        assert client.post("/api/login", json={"pin": "4321"}).status_code == 200
        with client.websocket_connect("/ws") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "hello"
            assert (hello["profile"]["input_count"], hello["profile"]["output_count"]) == (2, 6)
            messages = [ws.receive_json() for _ in range(3)]
            snapshot = next(m for m in messages if m["type"] == "snapshot")
            assert len(snapshot["state"]["outputs"]) == 6
            device = next(m for m in messages if m["type"] == "device")
            assert device["model"] == "DSP206"
            assert device["model_tested"] is False


def test_server_config_model() -> None:
    assert ServerConfig(demo=True).model == "auto"
    with pytest.raises(ValueError, match="--model"):
        ServerConfig(demo=True, model="306")


async def test_probe_detects_the_model(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], stop_later: list[Any]
) -> None:
    server = await simulated("204")
    stop_later.append(server)
    port = str(server.bound_port)
    dump = tmp_path / "u.bin"
    base = ["probe", "--dsp-host", "127.0.0.1", "--dsp-port", port]
    assert await asyncio.to_thread(cli.main, [*base, "dump-config", "-o", str(dump)]) == 0
    assert dump.stat().st_size == 724
    assert await asyncio.to_thread(cli.main, [*base, "meters"]) == 0
    assert "Out4" in capsys.readouterr().out
    diff = ["probe", "diff-config", str(dump), str(dump)]
    assert await asyncio.to_thread(cli.main, diff) == 0  # the size tells a DSP 204
    assert "no difference" in capsys.readouterr().out
