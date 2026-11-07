"""Device session against the simulator over TCP."""

import asyncio
from collections.abc import AsyncIterator

import pytest

from dsp408_multiui.device.session import (
    DeviceSession,
    DeviceStatus,
    DeviceUnavailableError,
    clamp_meter_rate,
)
from dsp408_multiui.protocol.meters import MeterReading
from dsp408_multiui.protocol.profile import DEFAULT_PROFILE
from dsp408_multiui.simulator import Faults, SimulatedDevice, SimulatorServer, apply_scenario
from dsp408_multiui.state.registry import ParamError
from dsp408_multiui.state.store import Patch, Snapshot, StateStore

P = DEFAULT_PROFILE.with_overrides({"timing": {"command_timeout_s": 0.2}})


def make_device() -> SimulatedDevice:
    device = SimulatedDevice(P)
    device.timing.default_s = 0.0
    device.timing.recall_s = 0.02
    device.timing.store_s = 0.02
    apply_scenario("demo", device, Faults())
    return device


@pytest.fixture
async def sim() -> AsyncIterator[SimulatorServer]:
    async with SimulatorServer(make_device(), port=0) as server:
        yield server


@pytest.fixture
async def session(sim: SimulatorServer) -> AsyncIterator[DeviceSession]:
    s = DeviceSession(
        "127.0.0.1",
        sim.bound_port,
        P,
        StateStore(),
        meter_rate_hz=10,
        reconnect_min_s=0.05,
        reconnect_max_s=0.2,
    )
    await s.start()
    await s.wait_online(5)
    yield s
    await s.stop()


async def test_connects_and_mirrors_state(session: DeviceSession) -> None:
    state = session.store.state
    assert session.status is DeviceStatus.ONLINE
    assert session.info.model == "DSP408"
    assert state.preset_name == "Demo 3-way"
    assert state.active_slot == 1
    assert state.presets[1].name == "Mono Sub"
    assert state.outputs[0].name == "SubL"
    assert session.store.rev == 1


async def test_write_updates_device_and_store_after_ack(
    session: DeviceSession, sim: SimulatorServer
) -> None:
    events: list[Snapshot | Patch] = []
    session.store.subscribe(events.append)
    write = await session.write("outputs.0.gain_db", -6.04, "client-a")
    assert write.changes == (("outputs.0.gain_db", -6.0),)
    assert session.store.state.outputs[0].gain_db == -6.0
    assert sim.device.live.outputs[0].gain == 220
    assert isinstance(events[-1], Patch)
    assert events[-1].origin == "client-a"


async def test_concurrent_fader_writes_converge(
    session: DeviceSession, sim: SimulatorServer
) -> None:
    await asyncio.gather(
        *(session.write("outputs.1.gain_db", -float(i) / 10, f"c{i % 3}") for i in range(100))
    )
    assert session.store.state.outputs[1].gain_db == -9.9
    assert sim.device.live.outputs[1].gain == 181


async def test_invalid_write_is_rejected_before_sending(session: DeviceSession) -> None:
    with pytest.raises(ParamError):
        await session.write("outputs.0.gain_db", "x", "c")


async def test_meters_arrive(session: DeviceSession) -> None:
    readings: list[MeterReading | None] = []
    session.on_meters(readings.append)
    await asyncio.sleep(0.35)
    assert len(readings) >= 2
    reading = readings[-1]
    assert reading is not None
    assert len(reading.levels_db) == 12


async def test_meter_rate_is_clamped(session: DeviceSession) -> None:
    session.meter_rate_hz = 50
    assert session.meter_rate_hz == 10
    session.meter_rate_hz = 0.1
    assert session.meter_rate_hz == 1
    assert clamp_meter_rate(5) == 5


async def test_recall_rereads_state(session: DeviceSession) -> None:
    events: list[Snapshot | Patch] = []
    session.store.subscribe(events.append)
    await session.recall(2, "client-b")
    assert session.store.state.preset_name == "Mono Sub"
    assert session.store.state.active_slot == 2
    assert isinstance(events[-1], Snapshot)
    with pytest.raises(ParamError):
        await session.recall(21, "x")


async def test_store_preset(session: DeviceSession, sim: SimulatorServer) -> None:
    await session.write("outputs.2.mute", True, "c")
    await session.store_preset(5, "Gig 2026", "client-c")
    state = session.store.state
    assert state.presets[4].name == "Gig 2026"
    assert state.active_slot == 5
    assert sim.device.presets[5].preset_name == "Gig 2026"
    assert sim.device.presets[5].outputs[2].mute
    for bad_slot, bad_name in [(0, "x"), (21, "x"), (1, "fifteen chars!!"), (1, "café")]:
        with pytest.raises(ParamError):
            await session.store_preset(bad_slot, bad_name, "c")


async def test_resync_picks_up_front_panel_changes(
    session: DeviceSession, sim: SimulatorServer
) -> None:
    sim.device.handle(bytes.fromhex("35 07 01"))  # someone mutes Out4 on the device
    assert not session.store.state.outputs[3].mute
    await session.resync()
    assert session.store.state.outputs[3].mute


async def test_reconnects_after_disconnect(session: DeviceSession, sim: SimulatorServer) -> None:
    statuses: list[DeviceStatus] = []
    session.on_status(lambda status, error: statuses.append(status))
    went_offline = asyncio.Event()
    session.on_status(
        lambda status, error: went_offline.set() if status is DeviceStatus.OFFLINE else None
    )
    sim.faults.disconnect_after = 1
    await asyncio.wait_for(went_offline.wait(), 5)
    sim.faults.disconnect_after = None
    await session.wait_online(5)
    assert DeviceStatus.OFFLINE in statuses
    assert statuses[-1] is DeviceStatus.ONLINE
    await session.write("outputs.0.mute", True, "c")


async def test_offline_operations_raise(sim: SimulatorServer) -> None:
    s = DeviceSession("127.0.0.1", 1, P, StateStore(), reconnect_min_s=0.05)
    with pytest.raises(DeviceUnavailableError):
        await s.write("outputs.0.mute", True, "c")
    await s.start()
    await asyncio.sleep(0.1)
    assert s.status in (DeviceStatus.OFFLINE, DeviceStatus.CONNECTING)
    assert s.last_error is None or s.last_error
    with pytest.raises(DeviceUnavailableError):
        await s.recall(1, "c")
    with pytest.raises(DeviceUnavailableError):
        await s.resync()
    await s.stop()
    assert s.status is DeviceStatus.STOPPED


async def test_survives_a_stressed_link() -> None:
    device = make_device()
    faults = Faults(drop_rate=0.05, corrupt_rate=0.02, nan_meter_rate=0.1, seed=1)
    async with SimulatorServer(device, port=0, faults=faults) as server:
        s = DeviceSession("127.0.0.1", server.bound_port, P, StateStore(), reconnect_min_s=0.05)
        await s.start()
        await s.wait_online(10)
        ok = 0
        for i in range(30):
            try:
                await s.write("outputs.0.gain_db", -float(i), "c")
                ok += 1
            except (TimeoutError, DeviceUnavailableError, ConnectionError):
                await s.wait_online(10)
        assert ok >= 20
        await s.stop()
