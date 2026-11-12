"""Command-line entry point (``tracks-dsp-controller``).

``serve`` (the default) runs the web application; ``sim`` runs a simulated DSP on the network
(``simulator/cli.py``, also installed as ``tracks-dsp-sim``); ``probe`` and ``proxy`` are
developer tools. Every option can also come from a ``TDSP_<NAME>`` environment variable.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from tracks_dsp_controller import __version__
from tracks_dsp_controller.envvars import Env
from tracks_dsp_controller.protocol import config_map as cm
from tracks_dsp_controller.protocol.profile import (
    MODELS,
    ProtocolProfile,
    detect_model,
    load_profile,
)

DSP_PORT = 9761


ENV = Env("TDSP_")
_env = ENV.get
_env_float = ENV.float
_env_flag = ENV.flag


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
    env_id = _env("DEVICE_ID")
    common.add_argument(
        "--device-id",
        type=_device_id,
        default=default or (int(env_id) if env_id else None),
        help="the ID number set on the DSP (1-250); default: searched for",
    )
    return common


def _device_id(text: str) -> int:
    value = int(text)
    if not 1 <= value <= 250:
        raise argparse.ArgumentTypeError("the device ID is 1-250")
    return value


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
    serve.add_argument(
        "--command-timeout",
        type=float,
        default=float(_env("COMMAND_TIMEOUT") or 0) or None,
        help="floor of the adaptive command timeout in s (default 0.5; it grows on a slow link)",
    )
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
        "(to test against a separate fake DSP on the network, use the sim command)",
    )
    tls = serve.add_argument_group("HTTPS (one port: plain http on it is redirected to https)")
    tls.add_argument("--tls-cert", default=_env("TLS_CERT"), help="certificate file (PEM)")
    tls.add_argument("--tls-key", default=_env("TLS_KEY"), help="private key file (PEM)")
    tls.add_argument(
        "--tls-self-signed",
        action="store_true",
        default=_env_flag("TLS_SELF_SIGNED"),
        help="generate a self-signed certificate (kept in --tls-dir, renewed when needed); "
        "browsers ask once to accept it",
    )
    tls.add_argument(
        "--tls-names",
        default=_env("TLS_NAMES", ""),
        help="extra names or addresses for the self-signed certificate, comma-separated "
        "(e.g. this host's address when running in Docker)",
    )
    tls.add_argument(
        "--tls-dir",
        type=Path,
        default=_env("TLS_DIR"),
        help="where the self-signed certificate is kept (default: the user's data directory)",
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
    export = actions.add_parser(
        "export-preset", help="read the live setup to a preset file (.prs) for the editor"
    )
    export.add_argument("-o", "--output", type=Path, required=True)
    diff = actions.add_parser(
        "diff-config", help="compare two config dumps or preset files (.prs) (offline)"
    )
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

    # sim: only listed here; main() hands everything after "sim" to the simulator's own parser
    sim = sub.add_parser(
        "sim",
        add_help=False,
        help="run a simulated DSP on the network, to test without a device (sim --help)",
    )
    sim.add_argument("sim_args", nargs=argparse.REMAINDER)
    return parser


# --- commands ---
async def _serve(args: argparse.Namespace, profile: ProtocolProfile) -> int:
    import uvicorn

    from tracks_dsp_controller.server import tls
    from tracks_dsp_controller.server.app import create_app
    from tracks_dsp_controller.server.listener import HttpsServer
    from tracks_dsp_controller.server.settings import ServerConfig

    context = None
    if args.tls_cert or args.tls_key or args.tls_self_signed:
        if args.tls_self_signed and (args.tls_cert or args.tls_key):
            raise ValueError("use either --tls-cert/--tls-key or --tls-self-signed")
        if args.tls_self_signed:
            names = tls.local_names(args.host) + tls.parse_names(args.tls_names)
            files = tls.self_signed(args.tls_dir or tls.default_dir(), names)
        elif args.tls_cert and args.tls_key:
            files = tls.TlsFiles(Path(args.tls_cert), Path(args.tls_key))
        else:
            raise ValueError("--tls-cert and --tls-key go together")
        context = tls.server_context(files)

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
        device_id=getattr(args, "device_id", None),
        tls=context is not None,
    )
    app = create_app(config, profile, profile_for=lambda key: load_profile(args.profile, key))
    target = "demo mode (no DSP)" if config.demo else f"{config.dsp_host}:{config.dsp_port}"
    scheme = "https" if context else "http"
    print(
        f"tracks-dsp-controller {__version__}: {scheme}://{config.host}:{config.port} -> {target}",
        flush=True,
    )
    uv_config = uvicorn.Config(
        app,
        host=config.host,
        port=config.port,
        log_level=args.log_level,
        access_log=False,
        ws_ping_interval=20,
    )
    server = HttpsServer(uv_config, context) if context else uvicorn.Server(uv_config)

    def request_exit() -> None:  # "Disconnect from DSP and shutdown" in the UI
        server.should_exit = True

    app.state.ctx.hub.request_exit = request_exit
    await server.serve()
    return 0


async def _probe(args: argparse.Namespace, profile: ProtocolProfile) -> int:
    from tracks_dsp_controller.device.transport import DspConnection
    from tracks_dsp_controller.protocol import preset_file
    from tracks_dsp_controller.tools import probe

    if args.action == "diff-config":
        before, after = args.before.read_bytes(), args.after.read_bytes()
        if args.model == "auto":  # offline: the file tells the model
            profile = load_profile(args.profile, probe.file_model(before))
        layout = cm.layout_for(profile)
        before, after = probe.as_blob(before, layout), probe.as_blob(after, layout)
        print(probe.format_diff(before, after, layout))
        return 0
    # --timeout: the adaptive timeout's floor (the ceiling follows if it is lower)
    timeout: dict[str, Any] = {}
    if args.timeout:
        ceiling = max(args.timeout, profile.command_timeout_max_s)
        timeout = {"timing": {"command_timeout_s": args.timeout, "command_timeout_max_s": ceiling}}
    profile = profile.with_overrides(timeout)
    device_id = getattr(args, "device_id", None)
    if device_id is not None:
        profile = replace(profile, host_dst=device_id)
    async with DspConnection(args.dsp_host, args.dsp_port, profile) as conn:
        if args.model == "auto" and args.action != "raw":
            identity = await probe.read_identity(conn, scan=device_id is None)
            key = detect_model(identity)
            if key is None:
                raise ValueError(f"unknown device {identity!r}: use --model 408|206|204")
            address = conn.profile.host_dst
            profile = replace(
                load_profile(args.profile, key).with_overrides(timeout), host_dst=address
            )
            conn.profile = profile
        summary = None
        if args.action != "info" and not getattr(args, "no_init", False):
            # The 408 serves config pages and meters only after the init sequence.
            summary = await probe.read_info(conn)
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
        elif args.action == "export-preset":
            blob = await probe.read_config_blob(conn)
            identity = summary.identity if summary else profile.model
            data = preset_file.encode_preset_file(blob, cm.layout_for(profile), identity)
            args.output.write_bytes(data)
            name = preset_file.preset_name(blob)
            print(f"wrote {name!r} ({len(data)} bytes) to {args.output}")
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
SIM_COMMAND = "sim"


def _with_default_command(argv: Sequence[str]) -> list[str]:
    """``tracks-dsp-controller --dsp-host X`` means ``tracks-dsp-controller serve --dsp-host X``."""
    args = list(argv)
    if any(a in (*COMMANDS, SIM_COMMAND, "-h", "--help", "--version") for a in args):
        return args
    return ["serve", *args] if args else args


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == [SIM_COMMAND]:
        from tracks_dsp_controller.simulator import cli as sim_cli

        return sim_cli.main(argv[1:], prog=f"tracks-dsp-controller {SIM_COMMAND}")
    parser = build_parser()
    args = parser.parse_args(_with_default_command(argv))
    if args.command == SIM_COMMAND:  # options before "sim" would belong to the wrong program
        parser.error(f"put the simulator's options after '{SIM_COMMAND}', e.g. sim --model 206")
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
