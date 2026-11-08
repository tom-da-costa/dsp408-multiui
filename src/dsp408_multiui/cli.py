"""Command-line entry point (``dsp408-multiui``).

``serve`` (the default) runs the web application; ``simulate``, ``probe`` and ``proxy`` are
developer tools. Every option can also come from a ``DSP408_<NAME>`` environment variable.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from dsp408_multiui import __version__
from dsp408_multiui.protocol.profile import ProtocolProfile, load_profile

DSP_PORT = 9761


def _env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(f"DSP408_{name}", default)


def _env_float(name: str, default: float) -> float:
    value = _env(name)
    return float(value) if value else default


def _env_flag(name: str) -> bool:
    return (_env(name) or "").lower() in ("1", "true", "yes", "on")


def _common(suppress: bool) -> argparse.ArgumentParser:
    """Global options, accepted before or after the sub-command."""
    common = argparse.ArgumentParser(add_help=False)
    default = argparse.SUPPRESS if suppress else None
    common.add_argument(
        "--log-level",
        default=default or _env("LOG_LEVEL", "info"),
        choices=["debug", "info", "warning", "error"],
    )
    common.add_argument(
        "--profile",
        type=Path,
        default=default or _env("PROFILE"),
        help="protocol profile TOML overriding the built-in defaults",
    )
    return common


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dsp408-multiui",
        description="Multi-client web controller for the t.racks DSP 408.",
        parents=[_common(suppress=False)],
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    common = _common(suppress=True)

    # serve (default)
    serve = sub.add_parser("serve", parents=[common], help="run the web application (default)")
    serve.add_argument("--dsp-host", default=_env("HOST"), help="DSP IP address")
    serve.add_argument("--dsp-port", type=int, default=int(_env("PORT") or DSP_PORT))
    serve.add_argument("--host", default=_env("LISTEN_HOST", "0.0.0.0"), help="listen address")
    serve.add_argument("--port", type=int, default=int(_env("LISTEN_PORT") or 8080))
    serve.add_argument("--pin", default=_env("PIN", "0000"), help="access code (default 0000)")
    serve.add_argument(
        "--meter-rate",
        type=float,
        default=_env_float("METER_RATE", 5.0),
        help="meter refresh rate in Hz, 1-10 (default 5)",
    )
    serve.add_argument(
        "--lock-idle-timeout",
        type=float,
        default=_env_float("LOCK_IDLE_TIMEOUT", 120.0),
        help="seconds of owner inactivity before the lock is released",
    )
    serve.add_argument(
        "--resync-interval",
        type=float,
        default=_env_float("RESYNC_INTERVAL", 0),
        help="re-read the DSP config every N seconds (0 = off)",
    )
    serve.add_argument("--command-timeout", type=float, default=None)
    serve.add_argument(
        "--experimental",
        action="store_true",
        default=_env_flag("EXPERIMENTAL"),
        help="allow parameters not yet verified on a DSP 408",
    )
    serve.add_argument(
        "--simulator",
        action="store_true",
        default=_env_flag("SIMULATOR"),
        help="run against an embedded simulated DSP",
    )
    serve.add_argument(
        "--scenario", default=_env("SCENARIO", "demo"), help="simulator scenario (with --simulator)"
    )

    # simulate
    sim = sub.add_parser("simulate", parents=[common], help="run a simulated DSP 408 on TCP")
    sim.add_argument("--host", default="127.0.0.1", help="listen address (default 127.0.0.1)")
    sim.add_argument("--port", type=int, default=DSP_PORT)
    sim.add_argument("--scenario", default="demo")
    sim.add_argument("--second-client", choices=["accept", "refuse", "kick"], default="accept")
    sim.add_argument("--latency-ms", type=float, default=0.0, help="extra latency per response")
    sim.add_argument("--drop-rate", type=float, default=0.0)
    sim.add_argument("--corrupt-rate", type=float, default=0.0)
    sim.add_argument("--frame-log", type=Path, help="append every frame to this JSONL file")

    # probe
    probe = sub.add_parser("probe", parents=[common], help="query a DSP or the simulator directly")
    probe.add_argument("--dsp-host", default=_env("HOST", "127.0.0.1"))
    probe.add_argument("--dsp-port", type=int, default=int(_env("PORT", str(DSP_PORT)) or DSP_PORT))
    probe.add_argument("--timeout", type=float, help="response timeout in seconds")
    actions = probe.add_subparsers(dest="action", metavar="ACTION", required=True)
    actions.add_parser("info", help="identity, status, active preset, preset names")
    meters = actions.add_parser("meters", help="raw meter frame with both decodings")
    meters.add_argument("--watch", action="store_true")
    meters.add_argument("--interval", type=float, default=0.5)
    meters.add_argument("--count", type=int, help="stop after N frames (with --watch)")
    dump = actions.add_parser("dump-config", help="read the live config blob to a file")
    dump.add_argument("-o", "--output", type=Path, required=True)
    diff = actions.add_parser("diff-config", help="compare two config dumps (offline)")
    diff.add_argument("before", type=Path)
    diff.add_argument("after", type=Path)
    raw = actions.add_parser("raw", help="send a raw payload, e.g. '34 04 18 01'")
    raw.add_argument("payload", nargs="+")
    raw.add_argument(
        "--no-init", action="store_true", help="skip the init sequence sent before the frame"
    )

    # proxy
    proxy = sub.add_parser(
        "proxy", parents=[common], help="log every frame between a client and the DSP"
    )
    proxy.add_argument("--dsp-host", default=_env("HOST"), required=_env("HOST") is None)
    proxy.add_argument("--dsp-port", type=int, default=DSP_PORT)
    proxy.add_argument("--listen", default="0.0.0.0:9761", help="HOST:PORT to listen on")
    proxy.add_argument("--log", type=Path, required=True, help="JSONL frame log file")
    return parser


# --- commands ---
async def _serve(args: argparse.Namespace, profile: ProtocolProfile) -> int:
    import uvicorn

    from dsp408_multiui.server.app import create_app
    from dsp408_multiui.server.settings import ServerConfig

    config = ServerConfig(
        dsp_host=args.dsp_host,
        dsp_port=args.dsp_port,
        host=args.host,
        port=args.port,
        pin=args.pin,
        meter_rate_hz=args.meter_rate,
        lock_idle_timeout_s=args.lock_idle_timeout,
        resync_interval_s=args.resync_interval,
        command_timeout_s=args.command_timeout,
        experimental=args.experimental,
        simulator=args.simulator,
        scenario=args.scenario,
    )
    app = create_app(config, profile)
    target = "embedded simulator" if config.simulator else f"{config.dsp_host}:{config.dsp_port}"
    print(
        f"dsp408-multiui {__version__}: http://{config.host}:{config.port} -> {target}", flush=True
    )
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=config.host,
            port=config.port,
            log_level=args.log_level,
            access_log=False,
            ws_ping_interval=20,
        )
    )
    await server.serve()
    return 0


async def _simulate(args: argparse.Namespace, profile: ProtocolProfile) -> int:
    from dsp408_multiui.framelog import FrameLog
    from dsp408_multiui.simulator import (
        Faults,
        SecondClient,
        SimulatedDevice,
        SimulatorServer,
        apply_scenario,
    )

    device = SimulatedDevice(profile)
    faults = Faults(
        extra_latency_s=args.latency_ms / 1000,
        drop_rate=args.drop_rate,
        corrupt_rate=args.corrupt_rate,
    )
    apply_scenario(args.scenario, device, faults)
    frame_log = FrameLog(args.frame_log, profile) if args.frame_log else None
    server = SimulatorServer(
        device,
        host=args.host,
        port=args.port,
        faults=faults,
        second_client=SecondClient(args.second_client),
        frame_log=frame_log,
    )
    await server.start()
    print(
        f"Simulated DSP 408 ({args.scenario}) on {args.host}:{server.bound_port}",
        flush=True,
    )
    try:
        await server.serve_forever()
    finally:
        await server.stop()
        if frame_log:
            frame_log.close()
    return 0


async def _probe(args: argparse.Namespace, profile: ProtocolProfile) -> int:
    from dsp408_multiui.device.transport import DspConnection
    from dsp408_multiui.tools import probe

    if args.action == "diff-config":
        print(probe.format_diff(args.before.read_bytes(), args.after.read_bytes()))
        return 0
    if args.timeout:
        profile = profile.with_overrides({"timing": {"command_timeout_s": args.timeout}})
    async with DspConnection(args.dsp_host, args.dsp_port, profile) as conn:
        if args.action != "info" and not getattr(args, "no_init", False):
            # The 408 serves config pages and meters only after the init sequence.
            await probe.read_info(conn)
        if args.action == "info":
            print(probe.format_info(await probe.read_info(conn)))
        elif args.action == "meters":
            if args.watch:
                await probe.watch_meters(conn, args.interval, args.count)
            else:
                print(probe.format_meters(await probe.read_meters(conn), profile))
        elif args.action == "dump-config":
            blob = await probe.read_config_blob(conn)
            args.output.write_bytes(blob)
            print(f"wrote {len(blob)} bytes to {args.output}")
        elif args.action == "raw":
            payload = bytes.fromhex("".join(args.payload))
            print(await probe.send_raw(conn, payload))
    return 0


async def _proxy(args: argparse.Namespace, profile: ProtocolProfile) -> int:
    from dsp408_multiui.framelog import FrameLog
    from dsp408_multiui.tools.proxy import ProxyServer

    host, _, port = args.listen.rpartition(":")
    frame_log = FrameLog(args.log, profile)
    proxy = ProxyServer(
        args.dsp_host,
        args.dsp_port,
        frame_log,
        listen_host=host or "0.0.0.0",
        listen_port=int(port),
    )
    await proxy.start()
    print(
        f"Proxy listening on {host or '0.0.0.0'}:{proxy.bound_port} -> "
        f"{args.dsp_host}:{args.dsp_port}, logging to {args.log}",
        flush=True,
    )
    try:
        await proxy.serve_forever()
    finally:
        await proxy.stop()
        frame_log.close()
    return 0


COMMANDS = {"serve": _serve, "simulate": _simulate, "probe": _probe, "proxy": _proxy}


def _with_default_command(argv: Sequence[str]) -> list[str]:
    """``dsp408-multiui --dsp-host X`` means ``dsp408-multiui serve --dsp-host X``."""
    args = list(argv)
    if any(a in COMMANDS for a in args) or any(a in ("-h", "--help", "--version") for a in args):
        return args
    return ["serve", *args] if args else args


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(_with_default_command(sys.argv[1:] if argv is None else argv))
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    if args.command is None:
        parser.print_help()
        return 0
    try:
        profile = load_profile(args.profile)
    except (OSError, ValueError) as exc:
        print(f"error: cannot load profile: {exc}", file=sys.stderr)
        return 2
    try:
        with contextlib.suppress(KeyboardInterrupt):
            return asyncio.run(COMMANDS[args.command](args, profile))
        return 130
    except (ConnectionError, TimeoutError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
