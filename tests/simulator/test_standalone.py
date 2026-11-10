"""The standalone simulator program (``tracks-dsp-sim``): storage, console, CLI, end to end."""

import asyncio
import contextlib
import signal
import socket
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from tracks_dsp_controller.device.session import DeviceSession, DeviceStatus
from tracks_dsp_controller.device.transport import DspConnection
from tracks_dsp_controller.protocol import commands as c
from tracks_dsp_controller.protocol import config_map as cm
from tracks_dsp_controller.protocol import responses as r
from tracks_dsp_controller.protocol.profile import DEFAULT_PROFILE as P
from tracks_dsp_controller.simulator import Faults, SimulatedDevice, SimulatorServer, apply_scenario
from tracks_dsp_controller.simulator import cli as sim_cli
from tracks_dsp_controller.simulator.console import Console
from tracks_dsp_controller.simulator.meters import Shape
from tracks_dsp_controller.simulator.server import SecondClient
from tracks_dsp_controller.simulator.storage import PresetStore, preset_file
from tracks_dsp_controller.state.store import StateStore

FIXTURES = Path(__file__).parents[1] / "fixtures"
U08 = FIXTURES / "config" / "dsp408_u08.bin"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


def fast_device() -> SimulatedDevice:
    device = SimulatedDevice(P)
    device.timing.default_s = device.timing.recall_s = device.timing.store_s = 0.0
    apply_scenario("demo", device, Faults())
    return device


def parse(*argv: str) -> sim_cli.argparse.Namespace:
    return sim_cli.build_parser().parse_args(list(argv))


# --- device hook and storage ------------------------------------------------------------------
def test_recall_and_store_call_the_preset_hook() -> None:
    device = fast_device()
    calls: list[int] = []
    device.on_preset_change = lambda: calls.append(device.active_slot)
    device.handle(c.RecallPreset(2).encode(P))
    device.handle(c.StorePreset(5).encode(P))
    device.handle(c.SetGain(0, 200).encode(P))
    assert calls == [2, 5]


def test_store_round_trip(tmp_path: Path) -> None:
    device = fast_device()
    store = PresetStore(tmp_path / "state")
    device.handle(c.SetPresetName("Kept").encode(P))
    device.handle(c.SetGain(4, 222).encode(P))
    device.handle(c.StorePreset(7).encode(P))
    store.save(device)
    assert sorted(p.name for p in (tmp_path / "state").iterdir()) == [
        "U01.bin",
        "U02.bin",
        "U07.bin",
        "active",
    ]
    again = SimulatedDevice(P)
    assert PresetStore(tmp_path / "state").load_into(again) == 3
    assert again.active_slot == 7
    assert again.live.preset_name == "Kept"
    assert again.live.outputs[0].gain == 222
    assert again.presets[1].preset_name == "Demo 3-way"


def test_store_skips_unchanged_and_bad_files(tmp_path: Path) -> None:
    store = PresetStore(tmp_path)
    device = fast_device()
    store.save(device)
    mtime = preset_file(tmp_path, 1).stat().st_mtime_ns
    store.save(device)
    assert preset_file(tmp_path, 1).stat().st_mtime_ns == mtime
    preset_file(tmp_path, 3).write_bytes(b"short")
    (tmp_path / "active").write_text("nope")
    other = SimulatedDevice(P)
    assert PresetStore(tmp_path).load_into(other) == 2
    assert other.active_slot == 0


# --- console ------------------------------------------------------------------------------------
@pytest.fixture
async def server() -> AsyncIterator[SimulatorServer]:
    async with SimulatorServer(fast_device(), port=0) as srv:
        yield srv


async def test_console_commands(server: SimulatorServer) -> None:
    stopped: list[bool] = []
    console = Console(server, lambda: stopped.append(True))
    assert "offline SECONDS" in console.execute("help")
    assert console.execute("") == ""
    assert "unknown command" in console.execute("explode")
    assert "wrong arguments" in console.execute("latency")
    assert "error" in console.execute("latency -1")
    assert "error" in console.execute('signal "A')
    assert console.execute("latency 25") == "latency 25 ms"
    assert server.faults.extra_latency_s == 0.025
    assert console.execute("drop 0.5") == "drop rate 0.5"
    assert "error" in console.execute("drop 2")
    assert console.execute("corrupt 0.1") == "corrupt rate 0.1"
    assert console.execute("nan 0.2") == "nan meter rate 0.2"
    assert "after 3" in console.execute("disconnect-after 3")
    assert server.faults.disconnect_after == 3
    assert "error" in console.execute("disconnect-after 0")
    assert console.execute("disconnect-after off") == "disconnect-after off"
    assert console.execute("second-client refuse") == "second client: refuse"
    assert server.second_client is SecondClient.REFUSE
    assert console.execute("signal b steady -6") == "signal B: steady -6 dB"
    assert server.device.meters.sources[1].shape is Shape.STEADY
    assert server.device.meters.sources[1].level_db == -6.0
    assert console.execute("signal all silence") == "signal ALL: silence"
    assert "error" in console.execute("signal E music")
    assert "error" in console.execute("signal A loud")
    status = console.execute("status")
    assert "DSP408 V0104P" in status
    assert "U01 'Demo 3-way'" in status
    assert "latency 25 ms" in status
    assert "* U01  Demo 3-way" in console.execute("presets")
    assert "recalled U02 'Mono Sub'" in console.execute("recall 2")
    assert server.device.active_slot == 2
    assert "error" in console.execute("recall 21")
    assert console.execute("quit") == "stopping"
    assert stopped == [True]


async def test_console_kick_and_offline(server: SimulatorServer) -> None:
    console = Console(server, lambda: None)
    port = server.bound_port
    async with DspConnection("127.0.0.1", port, P) as conn:
        await conn.request(c.Handshake())
        assert len(server.peers()) == 1
        assert console.execute("kick") == "dropped 1 connection(s)"
        await asyncio.sleep(0.05)
        assert server.client_count == 0
    assert "error" in console.execute("offline 0")
    assert console.execute("offline 0.2") == "offline for 0.2 s"
    assert "already offline" in console.execute("offline 1")
    await asyncio.sleep(0.05)
    assert "OFFLINE" in console.execute("status")
    with pytest.raises(ConnectionRefusedError):
        await asyncio.open_connection("127.0.0.1", port)
    await asyncio.sleep(0.3)
    assert server.running
    assert server.bound_port == port
    async with DspConnection("127.0.0.1", port, P) as conn:
        assert isinstance(await conn.request(c.Handshake()), r.HandshakeReply)


# --- command line -------------------------------------------------------------------------------
def test_build_device_options(tmp_path: Path) -> None:
    args = parse("--fast", "--preset", f"U08={U08}", "--latency-ms", "10", "--scenario", "silent")
    device, faults, store = sim_cli.build_device(args, P)
    assert store is None
    assert device.timing.recall_s == device.timing.store_s == 0.0
    assert faults.extra_latency_s == 0.01
    assert device.active_slot == 8  # starts on the loaded dump
    assert device.live.preset_name == "Pas touché svp"
    args = parse("--preset", f"3={U08}", "--active", "0", "--state-dir", str(tmp_path))
    device, _, store = sim_cli.build_device(args, P)
    assert store is not None
    assert device.active_slot == 0
    assert device.timing.store_s == 7.4
    assert preset_file(tmp_path, 3).read_bytes() == U08.read_bytes()
    device.handle(c.RecallPreset(3).encode(P))  # the hook saves the active slot
    assert (tmp_path / "active").read_text() == "3\n"


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--preset", "0=x.bin"], "slot"),
        (["--preset", "5=missing.bin"], "cannot load"),
        (["--active", "21"], "--active"),
    ],
)
def test_build_device_errors(argv: list[str], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        sim_cli.build_device(parse(*argv), P)


def test_bad_preset_argument() -> None:
    with pytest.raises(SystemExit):
        parse("--preset", "eight.bin")


def test_main_reports_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert sim_cli.main(["--active", "99"]) == 1
    assert "--active" in capsys.readouterr().err
    bad = tmp_path / "bad.toml"
    bad.write_text("[nope]\nx = 1\n")
    assert sim_cli.main(["--profile", str(bad)]) == 2


async def test_backend_session_against_the_program(tmp_path: Path) -> None:
    """The backend's device session talks to ``tracks-dsp-sim`` like to a real DSP."""
    port = free_port()
    args = parse(
        "--host", "127.0.0.1", "--port", str(port), "--fast", "--console", "off",
        "--preset", f"8={U08}", "--state-dir", str(tmp_path),
    )  # fmt: skip
    task = asyncio.create_task(sim_cli.run(args, P))
    session = DeviceSession("127.0.0.1", port, P, StateStore(), meter_rate_hz=10,
                            reconnect_min_s=0.05, reconnect_max_s=0.2)  # fmt: skip
    try:
        await session.start()
        await session.wait_online(5)
        assert session.status is DeviceStatus.ONLINE
        assert session.store.state.preset_name == "Pas touché svp"
        assert session.store.state.outputs[0].linked == [4]
        await session.write("outputs.0.gain_db", -3.0, "test")
        await session.store_preset(4, "From backend", "test")
    finally:
        await session.stop()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    stored = cm.decode_config(preset_file(tmp_path, 4).read_bytes())
    assert stored.preset_name == "From backend"
    assert (tmp_path / "active").read_text() == "4\n"


def test_the_program_runs_and_stops_on_sigterm() -> None:
    port = free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "tracks_dsp_controller.simulator", "--host", "127.0.0.1", "--port",
         str(port), "--console", "off", "--fast"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )  # fmt: skip
    try:
        assert proc.stdout is not None
        banner = proc.stdout.readline()
        assert f"on 127.0.0.1:{port}" in banner
        assert "Demo 3-way" in banner

        async def query() -> r.Response:
            async with DspConnection("127.0.0.1", port, P) as conn:
                return await conn.request(c.GetDeviceInfo())

        assert asyncio.run(query()) == r.DeviceInfo("DSP408 V0104P")
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(timeout=10) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def test_the_program_console_on_stdin() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "tracks_dsp_controller.simulator", "--host", "127.0.0.1", "--port",
         str(free_port()), "--console", "on", "--log-level", "warning"],
        input="status\nlatency 5\nquit\n", capture_output=True, text=True, timeout=20,
    )  # fmt: skip
    assert proc.returncode == 0
    assert "model           DSP 408, identity DSP408 V0104P" in proc.stdout
    assert "latency 5 ms" in proc.stdout
    assert "stopping" in proc.stdout
