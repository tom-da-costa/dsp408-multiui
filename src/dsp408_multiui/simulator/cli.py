"""``dsp408-sim``: a simulated DSP 408 on the network, as a program of its own.

It listens on TCP port 9761 like the real device. Point ``dsp408-multiui --dsp-host``, the probe
tools or the official editor at it. Every option can also come from a ``DSP408_SIM_<NAME>``
environment variable.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
import signal
import sys
from collections.abc import Sequence
from pathlib import Path

from dsp408_multiui import __version__
from dsp408_multiui.protocol import config_map as cm
from dsp408_multiui.protocol.profile import ProtocolProfile, load_profile
from dsp408_multiui.simulator.console import Console
from dsp408_multiui.simulator.device import DEFAULT_IDENTITY, SimulatedDevice
from dsp408_multiui.simulator.faults import Faults
from dsp408_multiui.simulator.scenarios import SCENARIOS, apply_scenario
from dsp408_multiui.simulator.server import DEFAULT_PORT, SecondClient, SimulatorServer
from dsp408_multiui.simulator.storage import PresetStore, read_config


def _env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(f"DSP408_SIM_{name}", default)


def _env_float(name: str, default: float) -> float:
    value = _env(name)
    return float(value) if value else default


def _env_flag(name: str) -> bool:
    return (_env(name) or "").lower() in ("1", "true", "yes", "on")


def _preset_arg(value: str) -> tuple[int, Path]:
    slot, sep, path = value.partition("=")
    if not sep or not slot.strip().upper().lstrip("U").isdigit():
        raise argparse.ArgumentTypeError(f"expected SLOT=FILE, e.g. 8=u08.bin, got {value!r}")
    return int(slot.strip().upper().lstrip("U")), Path(path)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dsp408-sim",
        description="Simulated t.racks DSP 408 on TCP, for testing dsp408-multiui without a "
        "device.",
        epilog="Example: dsp408-sim --state-dir sim-state   then   "
        "dsp408-multiui --dsp-host 127.0.0.1",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument(
        "--host",
        default=_env("HOST", "0.0.0.0"),
        help="listen address (default 0.0.0.0: reachable from the network like a real DSP)",
    )
    p.add_argument("--port", type=int, default=int(_env("PORT") or DEFAULT_PORT))
    p.add_argument(
        "--scenario",
        default=_env("SCENARIO", "demo"),
        choices=sorted(SCENARIOS),
        help="initial presets and input signals (default demo)",
    )
    p.add_argument(
        "--preset",
        type=_preset_arg,
        action="append",
        default=[],
        metavar="SLOT=FILE",
        help="load a config dump (probe dump-config) into user preset SLOT (1-20); repeatable",
    )
    p.add_argument("--active", type=int, help="active preset at start-up (0 = F00)")
    p.add_argument(
        "--state-dir",
        type=Path,
        default=_env("STATE_DIR"),
        help="keep stored presets and the active slot in this directory across restarts",
    )
    p.add_argument("--identity", default=_env("IDENTITY", DEFAULT_IDENTITY))
    p.add_argument(
        "--fast",
        action="store_true",
        default=_env_flag("FAST"),
        help="answer recall and store at once (the DSP 408 takes 3.2 s and 7.4 s)",
    )
    faults = p.add_argument_group("fault injection (also adjustable from the console)")
    faults.add_argument("--latency-ms", type=float, default=_env_float("LATENCY_MS", 0.0))
    faults.add_argument("--drop-rate", type=float, default=_env_float("DROP_RATE", 0.0))
    faults.add_argument("--corrupt-rate", type=float, default=_env_float("CORRUPT_RATE", 0.0))
    faults.add_argument("--nan-rate", type=float, default=_env_float("NAN_RATE", 0.0))
    faults.add_argument(
        "--second-client",
        choices=[m.value for m in SecondClient],
        default=_env("SECOND_CLIENT", SecondClient.ACCEPT.value),
        help="what happens when a second client connects (default accept)",
    )
    p.add_argument("--frame-log", type=Path, help="append every frame to this JSONL file")
    p.add_argument(
        "--console",
        choices=["auto", "on", "off"],
        default=_env("CONSOLE", "auto"),
        help="interactive console on stdin (auto: when stdin is a terminal)",
    )
    p.add_argument(
        "--log-level",
        default=_env("LOG_LEVEL", "info"),
        choices=["debug", "info", "warning", "error"],
    )
    p.add_argument("--profile", type=Path, default=_env("PROFILE"), help="protocol profile TOML")
    return p


def build_device(
    args: argparse.Namespace, profile: ProtocolProfile
) -> tuple[SimulatedDevice, Faults, PresetStore | None]:
    device = SimulatedDevice(profile, identity=args.identity)
    if args.fast:
        device.timing.recall_s = device.timing.store_s = 0.0
    faults = Faults(
        extra_latency_s=args.latency_ms / 1000,
        drop_rate=args.drop_rate,
        corrupt_rate=args.corrupt_rate,
        nan_meter_rate=args.nan_rate,
    )
    apply_scenario(args.scenario, device, faults)
    store = None
    if args.state_dir is not None:
        store = PresetStore(args.state_dir)
        count = store.load_into(device)
        logging.getLogger(__name__).info("loaded %d preset(s) from %s", count, args.state_dir)
    for slot, path in args.preset:
        if not 1 <= slot <= profile.preset_count:
            raise ValueError(f"--preset slot must be within 1..{profile.preset_count}")
        try:
            device.set_preset(slot, read_config(path))
        except (OSError, cm.ConfigError) as exc:
            raise ValueError(f"cannot load {path}: {exc}") from exc
    if args.active is not None:
        if not 0 <= args.active <= profile.preset_count:
            raise ValueError(f"--active must be within 0..{profile.preset_count}")
        device.load(args.active)
    elif args.preset:
        device.load(args.preset[-1][0])  # start on the loaded dump
    if store is not None:
        device.on_preset_change = lambda: store.save(device)
        store.save(device)
    return device, faults, store


async def run(args: argparse.Namespace, profile: ProtocolProfile) -> int:
    from dsp408_multiui.framelog import FrameLog

    device, faults, _ = build_device(args, profile)
    frame_log = FrameLog(args.frame_log, profile) if args.frame_log else None
    server = SimulatorServer(
        device,
        host=args.host,
        port=args.port,
        faults=faults,
        second_client=SecondClient(args.second_client),
        frame_log=frame_log,
    )
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError, RuntimeError):  # Windows
            loop.add_signal_handler(sig, stopped.set)
    await server.start()
    slot = "F00" if device.active_slot == 0 else f"U{device.active_slot:02d}"
    print(
        f"dsp408-sim {__version__}: simulated DSP 408 '{device.identity}' on "
        f"{args.host}:{server.bound_port}, preset {slot} {device.live.preset_name!r}",
        flush=True,
    )
    console_task = None
    if args.console == "on" or (args.console == "auto" and sys.stdin.isatty()):
        console_task = asyncio.create_task(Console(server, stopped.set).run())
    try:
        await stopped.wait()
    finally:
        if console_task is not None:
            console_task.cancel()
        await server.stop()
        if frame_log:
            frame_log.close()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    try:
        profile = load_profile(args.profile)
    except (OSError, ValueError) as exc:
        print(f"error: cannot load profile: {exc}", file=sys.stderr)
        return 2
    try:
        with contextlib.suppress(KeyboardInterrupt):
            return asyncio.run(run(args, profile))
        return 130
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
