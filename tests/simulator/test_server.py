"""Simulator server + minimal transport, over real TCP sockets on localhost."""

import asyncio
import io
import json
from collections.abc import AsyncIterator

import pytest

from dsp408_multiui.device.transport import DspConnection, TransportError, TransportTimeoutError
from dsp408_multiui.framelog import FrameLog
from dsp408_multiui.protocol import commands as c
from dsp408_multiui.protocol import responses as r
from dsp408_multiui.protocol.framing import encode_frame
from dsp408_multiui.protocol.profile import DEFAULT_PROFILE as P
from dsp408_multiui.simulator import Faults, SecondClient, SimulatedDevice, SimulatorServer


def fast_device() -> SimulatedDevice:
    device = SimulatedDevice(P)
    device.timing.recall_s = 0.01
    device.timing.store_s = 0.01
    device.timing.default_s = 0.0
    return device


@pytest.fixture
async def server() -> AsyncIterator[SimulatorServer]:
    async with SimulatorServer(fast_device(), port=0) as srv:
        yield srv


def connection(server: SimulatorServer, timeout: float = 0.5) -> DspConnection:
    profile = P.with_overrides({"timing": {"command_timeout_s": timeout}})
    return DspConnection("127.0.0.1", server.bound_port, profile)


async def test_request_response_roundtrip(server: SimulatorServer) -> None:
    async with connection(server) as conn:
        assert conn.connected
        info = await conn.request(c.GetDeviceInfo())
        assert isinstance(info, r.DeviceInfo)
        assert await conn.request(c.SetGain(4, 250)) == r.Ack()
        assert isinstance(await conn.request(c.SetPresetName("Over TCP")), r.Ack)
        assert await conn.request(c.StorePreset(1)) == r.Ack()
        assert await conn.request(c.GetPresetName(0)) == r.PresetName(0, "Over TCP")
    assert not conn.connected
    assert server.device.live.outputs[0].gain == 250


async def test_concurrent_requests_are_serialised(server: SimulatorServer) -> None:
    async with connection(server) as conn:
        replies = await asyncio.gather(*(conn.request(c.GetPresetName(i)) for i in range(20)))
    assert [reply.index for reply in replies if isinstance(reply, r.PresetName)] == list(range(20))


async def test_connect_failure() -> None:
    conn = DspConnection("127.0.0.1", 1, P, connect_timeout=1.0)
    with pytest.raises(TransportError):
        await conn.connect()
    with pytest.raises(TransportError, match="not connected"):
        await conn.request(c.Handshake())


async def test_dropped_response_times_out_then_recovers(server: SimulatorServer) -> None:
    async with connection(server, timeout=0.1) as conn:
        server.faults.drop_rate = 1.0
        with pytest.raises(TransportTimeoutError):
            await conn.request(c.GetActivePreset())
        server.faults.drop_rate = 0.0
        assert await conn.request(c.GetActivePreset()) == r.ActivePreset(0)


async def test_late_answer_is_skipped(server: SimulatorServer) -> None:
    async with connection(server, timeout=0.05) as conn:
        server.faults.extra_latency_s = 0.15
        with pytest.raises(TransportTimeoutError):
            await conn.request(c.GetDeviceInfo())
        server.faults.extra_latency_s = 0.0
        await asyncio.sleep(0.2)  # the late DeviceInfo frame arrives meanwhile
        assert await conn.request(c.GetActivePreset(), timeout=0.5) == r.ActivePreset(0)


async def test_corrupt_response_is_dropped(server: SimulatorServer) -> None:
    async with connection(server, timeout=0.1) as conn:
        server.faults.corrupt_rate = 1.0
        with pytest.raises(TransportTimeoutError):
            await conn.request(c.Handshake())
        server.faults.corrupt_rate = 0.0
        assert isinstance(await conn.request(c.Handshake()), r.HandshakeReply)


async def test_disconnect_after(server: SimulatorServer) -> None:
    server.faults.disconnect_after = 2
    async with connection(server) as conn:
        await conn.request(c.Handshake())
        await conn.request(c.Handshake())
        with pytest.raises(TransportError):
            await conn.request(c.Handshake())
        assert not conn.connected


async def test_firmware_crash_closes_the_connection(server: SimulatorServer) -> None:
    async with connection(server) as conn:
        with pytest.raises(TransportError):
            await conn.request_raw(bytes((0x26,)) + b"x" * 20)


async def test_second_client_refused() -> None:
    async with SimulatorServer(fast_device(), port=0, second_client=SecondClient.REFUSE) as srv:
        async with connection(srv) as first:
            await first.request(c.Handshake())
            async with connection(srv) as second:
                with pytest.raises(TransportError):
                    await second.request(c.Handshake())
            assert await first.request(c.GetActivePreset()) == r.ActivePreset(0)


async def test_second_client_kicks_the_first() -> None:
    async with SimulatorServer(fast_device(), port=0, second_client=SecondClient.KICK) as srv:
        async with connection(srv) as first:
            await first.request(c.Handshake())
            async with connection(srv) as second:
                await second.request(c.Handshake())
                with pytest.raises(TransportError):
                    await first.request(c.Handshake())
                assert srv.client_count == 1


async def test_second_client_accepted(server: SimulatorServer) -> None:
    async with connection(server) as first, connection(server) as second:
        await first.request(c.SetGain(0, 100))
        assert await second.request(c.Handshake()) == r.HandshakeReply(b"\x14")
        assert server.client_count == 2


async def test_second_client_does_not_reset_the_first(server: SimulatorServer) -> None:
    async with connection(server) as first:
        await first.request(c.Handshake())
        assert isinstance(await first.request(c.PollMeters()), r.MeterFrame)
        async with connection(server) as second:
            await second.request(c.GetDeviceInfo())
            assert isinstance(await first.request(c.PollMeters()), r.MeterFrame)
            with pytest.raises(TransportTimeoutError):  # not initialised on this connection
                await second.request(c.PollMeters(), timeout=0.1)


async def test_frame_log() -> None:
    buffer = io.StringIO()
    log = FrameLog(buffer, P)
    async with SimulatorServer(fast_device(), port=0, frame_log=log) as srv:
        async with connection(srv) as conn:
            await conn.request(c.SetMute(4, True))
    records = [json.loads(line) for line in buffer.getvalue().splitlines()]
    assert [rec["dir"] for rec in records] == ["host->dsp", "dsp->host"]
    assert records[0]["hex"] == encode_frame(bytes.fromhex("35 04 01")).hex(" ")
    assert "SetMute" in records[0]["decoded"]
    assert records[1]["decoded"] == "Ack()"


def test_bound_port_requires_running_server() -> None:
    with pytest.raises(RuntimeError):
        _ = SimulatorServer(fast_device(), port=0).bound_port


def test_faults_validation() -> None:
    with pytest.raises(ValueError, match="drop_rate"):
        Faults(drop_rate=2.0)
    with pytest.raises(ValueError, match="latency"):
        Faults(extra_latency_s=-1)
