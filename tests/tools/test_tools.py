"""probe, proxy and the CLI, against the simulator."""

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from tracks_dsp_controller import cli
from tracks_dsp_controller.device.transport import DspConnection, TransportTimeoutError
from tracks_dsp_controller.framelog import FrameLog
from tracks_dsp_controller.protocol import commands as c
from tracks_dsp_controller.protocol import config_map as cm
from tracks_dsp_controller.protocol import preset_file as pf
from tracks_dsp_controller.protocol import responses as r
from tracks_dsp_controller.protocol.profile import DEFAULT_PROFILE as P
from tracks_dsp_controller.simulator import Faults, SimulatedDevice, SimulatorServer, apply_scenario
from tracks_dsp_controller.tools import probe
from tracks_dsp_controller.tools.proxy import ProxyServer


@pytest.fixture
async def sim() -> AsyncIterator[SimulatorServer]:
    device = SimulatedDevice(P)
    device.timing.default_s = 0.0
    apply_scenario("demo", device, Faults())
    async with SimulatorServer(device, port=0) as server:
        yield server


async def test_read_info(sim: SimulatorServer) -> None:
    async with DspConnection("127.0.0.1", sim.bound_port, P) as conn:
        summary = await probe.read_info(conn)
    assert summary.identity == "DSP408 V0104P"
    assert summary.active_slot == 1
    assert summary.preset_names[:2] == ["Demo 3-way", "Mono Sub"]
    text = probe.format_info(summary)
    assert "active     : U01" in text
    assert "U02 Mono Sub" in text


async def test_dump_config_matches_the_device(sim: SimulatorServer) -> None:
    quick = P.with_overrides({"timing": {"command_timeout_max_s": 0.5}})  # no long backoff
    async with DspConnection("127.0.0.1", sim.bound_port, quick) as conn:
        with pytest.raises(TransportTimeoutError):  # like the 408: nothing before the init
            await probe.read_config_blob(conn)
        await probe.read_info(conn)
        blob = await probe.read_config_blob(conn)
    assert blob == sim.device.config_blob
    assert cm.decode_config(blob).preset_name == "Demo 3-way"


async def test_meters_and_raw(sim: SimulatorServer) -> None:
    async with DspConnection("127.0.0.1", sim.bound_port, P) as conn:
        await probe.read_info(conn)
        data = await probe.read_meters(conn)
        text = probe.format_meters(data, P)
        assert text.splitlines()[0].startswith("chan")
        assert "Out8" in text
        assert "tail" in text
        assert (await probe.send_raw(conn, bytes.fromhex("34 04 c8 00"))).endswith("Ack()")
    assert sim.device.live.outputs[0].gain == 200
    assert "cannot decode" in probe.format_meters(b"\x00", P)


def test_format_diff() -> None:
    before = cm.default_config().image
    edited = bytearray(before)
    edited[cm.output_offset(1) + 8] = 0x0F
    assert probe.format_diff(before, before) == "no difference"
    assert "out1.matrix" in probe.format_diff(before, bytes(edited))


def test_expect_raises_on_wrong_reply() -> None:
    with pytest.raises(probe.ProbeError, match="expected"):
        probe._expect(r.Ack(), r.DeviceInfo)


async def test_proxy_forwards_and_logs(sim: SimulatorServer, tmp_path: Path) -> None:
    log_path = tmp_path / "frames.jsonl"
    frame_log = FrameLog(log_path, P)
    async with ProxyServer(
        "127.0.0.1", sim.bound_port, frame_log, listen_host="127.0.0.1", listen_port=0
    ) as proxy:
        async with DspConnection("127.0.0.1", proxy.bound_port, P) as conn:
            assert await conn.request(c.SetMute(5, True)) == r.Ack()
            info = await conn.request(c.GetDeviceInfo())
            assert isinstance(info, r.DeviceInfo)
        await asyncio.sleep(0.05)
    frame_log.close()
    records = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert [rec["dir"] for rec in records] == ["host->dsp", "dsp->host"] * 2
    assert "SetMute" in records[0]["decoded"]
    assert "DeviceInfo" in records[3]["decoded"]
    assert sim.device.live.outputs[1].mute


async def test_proxy_without_dsp(tmp_path: Path) -> None:
    frame_log = FrameLog(tmp_path / "f.jsonl", P)
    async with ProxyServer(
        "127.0.0.1", 1, frame_log, listen_host="127.0.0.1", listen_port=0
    ) as proxy:
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy.bound_port)
        assert await reader.read() == b""  # closed: the DSP is unreachable
        writer.close()
    frame_log.close()


def test_proxy_bound_port_requires_running() -> None:
    with pytest.raises(RuntimeError):
        _ = ProxyServer("h", 1, FrameLog(Path("/dev/null"), P)).bound_port


# --- CLI -------------------------------------------------------------------------------------
def test_cli_help_and_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([]) == 0
    assert "probe" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cli.main(["--version"])


def test_cli_diff_config(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    a, b = tmp_path / "a.bin", tmp_path / "b.bin"
    a.write_bytes(cm.default_config().image)
    edited = bytearray(cm.default_config().image)
    edited[cm.input_offset(0) + 132] = 0
    b.write_bytes(bytes(edited))
    assert cli.main(["probe", "diff-config", str(a), str(b)]) == 0
    assert "in0.gain" in capsys.readouterr().out


def test_cli_bad_profile(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.toml"
    bad.write_text("[nope]\nx = 1\n")
    assert cli.main(["--profile", str(bad), "probe", "info"]) == 2
    assert "cannot load profile" in capsys.readouterr().err


def test_cli_probe_unreachable(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["probe", "--dsp-port", "1", "info"]) == 1
    assert "error" in capsys.readouterr().err


async def run_cli_in_thread(argv: list[str]) -> int:
    return await asyncio.to_thread(cli.main, argv)


async def test_cli_probe_against_simulator(
    sim: SimulatorServer, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    port = str(sim.bound_port)
    out = tmp_path / "dump.bin"
    assert await run_cli_in_thread(["probe", "--dsp-port", port, "info"]) == 0
    assert await run_cli_in_thread(["probe", "--dsp-port", port, "meters"]) == 0
    assert (
        await run_cli_in_thread(
            ["probe", "--dsp-port", port, "meters", "--watch", "--count", "2", "--interval", "0"]
        )
        == 0
    )
    assert await run_cli_in_thread(["probe", "--dsp-port", port, "raw", "35", "04", "01"]) == 0
    dump = ["probe", "--dsp-port", port, "dump-config", "-o", str(out)]
    assert await run_cli_in_thread(dump) == 0
    text = capsys.readouterr().out
    assert "Demo 3-way" in text
    assert f"wrote {cm.CONFIG_SIZE} bytes" in text
    assert out.read_bytes() == sim.device.config_blob
    prs = tmp_path / "live.prs"
    export = ["probe", "--dsp-port", port, "export-preset", "-o", str(prs)]
    assert await run_cli_in_thread(export) == 0
    assert "wrote 'Demo 3-way' (1452 bytes)" in capsys.readouterr().out
    assert prs.read_bytes() == pf.encode_preset_file(
        out.read_bytes(), cm.LAYOUT_408, "DSP408 V0104P"
    )
    # A preset file compares with a dump: they differ in what the file leaves out only.
    assert await run_cli_in_thread(["probe", "diff-config", str(prs), str(out)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert all(line.endswith("marker") for line in lines) or lines == ["no difference"]


def test_serve_is_the_default_command() -> None:
    assert cli._with_default_command(["--demo"]) == ["serve", "--demo"]
    assert cli._with_default_command(["probe", "info"]) == ["probe", "info"]
    assert cli._with_default_command(["--version"]) == ["--version"]
    assert cli._with_default_command([]) == []
    args = cli.build_parser().parse_args(["serve", "--demo", "--log-level", "debug"])
    assert args.demo
    assert args.log_level == "debug"
    assert args.pin == "0000"


def test_serve_requires_a_dsp_host(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--port", "0"]) == 1
    assert "dsp-host" in capsys.readouterr().err


def test_options_read_tracks_dsp_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRACKS_DSP_HOST", "10.0.0.9")
    monkeypatch.setenv("TRACKS_DSP_PIN", "4321")
    monkeypatch.setenv("TRACKS_DSP_COMMAND_TIMEOUT", "0.8")
    args = cli.build_parser().parse_args(["serve"])
    assert (args.dsp_host, args.pin, args.command_timeout) == ("10.0.0.9", "4321", 0.8)
    # an option on the command line wins over its variable
    assert cli.build_parser().parse_args(["serve", "--pin", "1111"]).pin == "1111"


def test_legacy_dsp408_variables_still_work_with_a_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(cli, "_legacy_env", set())
    monkeypatch.setenv("DSP408_HOST", "10.0.0.8")
    monkeypatch.setenv("DSP408_PIN", "1234")
    monkeypatch.setenv("TRACKS_DSP_PIN", "4321")  # the new name wins
    args = cli.build_parser().parse_args(["serve"])
    assert (args.dsp_host, args.pin) == ("10.0.0.8", "4321")
    with caplog.at_level("WARNING"):
        cli._warn_legacy_env()
    assert "DSP408_HOST is deprecated: rename it to TRACKS_DSP_HOST" in caplog.text
    assert "DSP408_PIN" not in caplog.text
