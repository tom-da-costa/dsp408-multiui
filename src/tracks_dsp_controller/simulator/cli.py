"""``tracks-dsp-controller sim`` (or ``tracks-dsp-sim``): a simulated t.racks DSP on the network.

It plays a DSP 408 (default), 206 or 204 (``--model``) and listens on TCP port 9761 like the real
device. Point ``tracks-dsp-controller --dsp-host``, the probe tools or the official editor at it.
Every option can also come from a ``TDSP_SIM_<NAME>`` environment variable
(``TRACKS_DSP_SIM_<NAME>`` before 0.8: still read, with a warning).
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import signal
import sys
from collections.abc import Sequence
from pathlib import Path

from tracks_dsp_controller import __version__
from tracks_dsp_controller.envvars import Env
from tracks_dsp_controller.protocol.profile import ProtocolProfile, load_profile
from tracks_dsp_controller.simulator.console import Console
from tracks_dsp_controller.simulator.device import SimulatedDevice
from tracks_dsp_controller.simulator.faults import Faults
from tracks_dsp_controller.simulator.models import DEFAULT_MODEL, SIM_MODELS
from tracks_dsp_controller.simulator.scenarios import SCENARIOS, apply_scenario
from tracks_dsp_controller.simulator.server import DEFAULT_PORT, SecondClient, SimulatorServer
from tracks_dsp_controller.simulator.storage import PresetStore, read_config

ENV = Env("TDSP_SIM_", legacy_prefix="TRACKS_DSP_SIM_")
_env = ENV.get
_env_float = ENV.float
_env_flag = ENV.flag


def _preset_arg(value: str) -> tuple[int, Path]:
    slot, sep, path = value.partition("=")
    if not sep or not slot.strip().upper().lstrip("U").isdigit():
        raise argparse.ArgumentTypeError(f"expected SLOT=FILE, e.g. 8=u08.bin, got {value!r}")
    return int(slot.strip().upper().lstrip("U")), Path(path)


def build_parser(prog: str = "tracks-dsp-sim") -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=prog,
        description="Simulated t.racks DSP (408, 206 or 204) on TCP, for testing "
        "tracks-dsp-controller without a device.",
        epilog=f"Example: {prog} --state-dir sim-state   then   "
        "tracks-dsp-controller --dsp-host 127.0.0.1",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument(
        "--model",
        default=_env("MODEL", DEFAULT_MODEL),
        choices=list(SIM_MODELS),
        help="DSP model to simulate (default 408)",
    )
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
        help="load a config dump (probe dump-config) or a preset file (.prs) of the same model "
        "into user preset SLOT (1-20); "
        "repeatable",
    )
    p.add_argument("--active", type=int, help="active preset at start-up (0 = F00)")
    env_id = _env("DEVICE_ID")
    p.add_argument(
        "--device-id",
        type=int,
        default=int(env_id) if env_id else None,
        help="the ID number set on the front panel, 1-250: the DSP only answers frames sent to "
        "it (default: 1, 2 for a 206)",
    )
    p.add_argument(
        "--state-dir",
        type=Path,
        default=_env("STATE_DIR"),
        help="keep stored presets and the active slot in this directory across restarts",
    )
    p.add_argument("--identity", default=_env("IDENTITY"), help="0x13 reply (default: the model's)")
    p.add_argument(
        "--fast",
        action="store_true",
        default=_env_flag("FAST"),
        help="answer recall and store at once (a DSP 408 takes 3.2 s and 7.4 s)",
    )
    faults = p.add_argument_group("fault injection (also adjustable from the console)")
    faults.add_argument("--latency-ms", type=float, default=_env_float("LATENCY_MS", 0.0))
    faults.add_argument("--drop-rate", type=float, default=_env_float("DROP_RATE", 0.0))
    faults.add_argument("--corrupt-rate", type=float, default=_env_float("CORRUPT_RATE", 0.0))
    faults.add_argument("--nan-rate", type=float, default=_env_float("NAN_RATE", 0.0))
    faults.add_argument(
        "--second-client",
        choices=[m.value for m in SecondClient],
        default=_env("SECOND_CLIENT", SecondClient.QUEUE.value),
        help="what happens when a second client connects (default queue: it waits for the "
        "first to leave, like a DSP 408)",
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
    p.add_argument(
        "--profile",
        type=Path,
        default=_env("PROFILE"),
        help="protocol profile TOML overriding the model's built-in profile",
    )
    return p


def build_device(
    args: argparse.Namespace, profile: ProtocolProfile
) -> tuple[SimulatedDevice, Faults, PresetStore | None]:
    model = SIM_MODELS[args.model]
    device = SimulatedDevice(profile, model=model, identity=args.identity or "")
    if not model.replies_observed:
        logging.getLogger(__name__).info(
            "DSP %s: the bytes of the init replies are copied from the 206", model.key
        )
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
            device.set_preset(slot, read_config(path, device.layout))
        except (OSError, ValueError) as exc:
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
    from tracks_dsp_controller.framelog import FrameLog

    device, faults, _ = build_device(args, profile)
    frame_log = FrameLog(args.frame_log, profile) if args.frame_log else None
    server = SimulatorServer(
        device,
        host=args.host,
        port=args.port,
        faults=faults,
        second_client=SecondClient(args.second_client),
        frame_log=frame_log,
        device_id=args.device_id,
    )
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError, RuntimeError):  # Windows
            loop.add_signal_handler(sig, stopped.set)
    await server.start()
    slot = "F00" if device.active_slot == 0 else f"U{device.active_slot:02d}"
    print(
        f"tracks-dsp-controller sim {__version__}: simulated DSP {device.model.key} "
        f"'{device.identity}' on {args.host}:{server.bound_port}, "
        f"preset {slot} {device.live.preset_name!r}",
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


def main(argv: Sequence[str] | None = None, prog: str = "tracks-dsp-sim") -> int:
    """``tracks-dsp-sim``, also run as ``tracks-dsp-controller sim``."""
    args = build_parser(prog).parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    ENV.warn_legacy(logging.getLogger(__name__))
    try:
        profile = load_profile(args.profile, model=args.model)
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
