"""Command-line entry point (``tracks-dsp-controller``).

``serve`` (the default) runs the web application; ``probe`` and ``proxy`` are developer tools.
The simulated DSP is a separate program, ``tracks-dsp-sim`` (``simulator/cli.py``). Every option can
also come from a ``DSP408_<NAME>`` environment variable.
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

from tracks_dsp_controller import __version__
from tracks_dsp_controller.protocol import config_map as cm
from tracks_dsp_controller.protocol.profile import (
    MODELS,
    ProtocolProfile,
    detect_model,
    load_profile,
)

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
        help="protocol profile TOML overriding the built-in profile of the model",
    )
    common.add_argument(
        "--model",
        choices=["auto", *MODELS],
        default=default or _env("MODEL", "auto"),
        help="DSP model: auto (default: detected from the device's identity), 408, 206 or 204",
    )
    return common


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tracks-dsp-controller",
        description="Multi-client web controller for the t.racks DSP 408 (and DSP 206, 204).",
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
        help="allow parameters not yet verified on a DSP 408 (the 206 and 204 use the same list)",
    )
    serve.add_argument(
        "--demo",
        action="store_true",
        default=_env_flag("DEMO"),
        help="demo mode: no DSP, a simulated one runs inside this process "
        "(to test against a separate fake DSP on the network, use tracks-dsp-sim)",
    )
    serve.add_argument(
        "--demo-scenario",
        default=_env("DEMO_SCENARIO", "demo"),
        help="presets and signals of the demo mode (demo, silent, clipping, stress)",
    )

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

    from tracks_dsp_controller.server.app import create_app
    from tracks_dsp_controller.server.settings import ServerConfig

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
        demo=args.demo,
        demo_scenario=args.demo_scenario,
        model=args.model,
    )
    app = create_app(config, profile, profile_for=lambda key: load_profile(args.profile, key))
    target = "demo mode (no DSP)" if config.demo else f"{config.dsp_host}:{config.dsp_port}"
    print(
        f"tracks-dsp-controller {__version__}: http://{config.host}:{config.port} -> {target}",
        flush=True,
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


async def _probe(args: argparse.Namespace, profile: ProtocolProfile) -> int:
    from tracks_dsp_controller.device.transport import DspConnection
    from tracks_dsp_controller.tools import probe

    if args.action == "diff-config":
        before, after = args.before.read_bytes(), args.after.read_bytes()
        if args.model == "auto":  # offline: the dump's size tells the model
            sizes = {load_profile(args.profile, key).config_size: key for key in MODELS}
            profile = load_profile(args.profile, sizes.get(len(before), "408"))
        print(probe.format_diff(before, after, cm.layout_for(profile)))
        return 0
    timeout = {"timing": {"command_timeout_s": args.timeout}} if args.timeout else {}
    profile = profile.with_overrides(timeout)
    async with DspConnection(args.dsp_host, args.dsp_port, profile) as conn:
        if args.model == "auto" and args.action != "raw":
            identity = await probe.read_identity(conn)
            key = detect_model(identity)
            if key is None:
                raise ValueError(f"unknown device {identity!r}: use --model 408|206|204")
            profile = load_profile(args.profile, key).with_overrides(timeout)
            conn.profile = profile
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
    from tracks_dsp_controller.framelog import FrameLog
    from tracks_dsp_controller.tools.proxy import ProxyServer

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


COMMANDS = {"serve": _serve, "probe": _probe, "proxy": _proxy}


def _with_default_command(argv: Sequence[str]) -> list[str]:
    """``tracks-dsp-controller --dsp-host X`` means ``tracks-dsp-controller serve --dsp-host X``."""
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
        profile = load_profile(args.profile, "408" if args.model == "auto" else args.model)
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
