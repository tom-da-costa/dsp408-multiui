"""FastAPI application: login API, WebSocket, health check and the static UI."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response, WebSocket
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

from dsp408_multiui import __version__
from dsp408_multiui.device.session import DeviceSession
from dsp408_multiui.protocol.profile import ProtocolProfile
from dsp408_multiui.server.auth import (
    SESSION_COOKIE,
    AuthManager,
    LoginError,
    RateLimitedError,
)
from dsp408_multiui.server.lock import LockManager
from dsp408_multiui.server.settings import DEFAULT_PIN, ServerConfig
from dsp408_multiui.server.ws import Hub
from dsp408_multiui.simulator import Faults, SimulatedDevice, SimulatorServer, apply_scenario
from dsp408_multiui.state.store import StateStore

log = logging.getLogger(__name__)

LOCK_TICK_S = 1.0

PLACEHOLDER_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DSP 408 control</title></head>
<body style="font-family: system-ui, sans-serif; margin: 2rem; background: #111; color: #eee">
<h1>The web UI is not built</h1>
<p>The server is running, but <code>src/dsp408_multiui/web/</code> has no <code>index.html</code>.
Build it with <code>make web</code> (needs Node), or use a release package.</p>
</body></html>
"""


class LoginBody(BaseModel):
    pin: str
    name: str | None = None


def default_web_dir() -> Path:
    return Path(str(resources.files("dsp408_multiui").joinpath("web")))


@dataclass
class AppContext:
    config: ServerConfig
    profile: ProtocolProfile
    store: StateStore
    session: DeviceSession
    auth: AuthManager
    lock: LockManager
    hub: Hub
    simulator: SimulatorServer | None = None


def _origin_allowed(websocket: WebSocket) -> bool:
    """Reject cross-site WebSocket connections (the Origin host must match the Host header)."""
    origin = websocket.headers.get("origin")
    if origin is None:  # non-browser client
        return True
    return urlsplit(origin).netloc == websocket.headers.get("host", "")


def create_app(
    config: ServerConfig,
    profile: ProtocolProfile,
    *,
    web_dir: Path | None = None,
    simulated_device: SimulatedDevice | None = None,
) -> FastAPI:
    """Build the application. The device session starts with the app's lifespan."""
    web_root = web_dir or default_web_dir()
    if config.command_timeout_s is not None:
        profile = profile.with_overrides(
            {"timing": {"command_timeout_s": config.command_timeout_s}}
        )
    store = StateStore()
    auth = AuthManager(config.pin)
    lock = LockManager(config.lock_idle_timeout_s)
    simulator: SimulatorServer | None = None
    if config.demo:
        device = simulated_device or SimulatedDevice(profile)
        faults = Faults()
        if simulated_device is None:
            apply_scenario(config.demo_scenario, device, faults)
        simulator = SimulatorServer(device, host="127.0.0.1", port=0, faults=faults)
    # The simulator's port is only known once it runs, so the session resolves it lazily.
    session = DeviceSession(
        config.dsp_host or "127.0.0.1",
        config.dsp_port,
        profile,
        store,
        meter_rate_hz=config.meter_rate_hz,
    )
    hub = Hub(config, session, store, auth, lock)
    ctx = AppContext(config, profile, store, session, auth, lock, hub, simulator)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if ctx.simulator is not None:
            await ctx.simulator.start()
            session.port = ctx.simulator.bound_port
            session.host = "127.0.0.1"
        if config.pin == DEFAULT_PIN:
            log.warning("using the default access code %s: set --pin or DSP408_PIN", DEFAULT_PIN)
        await session.start()
        tasks = [asyncio.create_task(_lock_ticker(lock))]
        if config.resync_interval_s > 0:
            tasks.append(asyncio.create_task(_resync_loop(session, config.resync_interval_s)))
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            await session.stop()
            if ctx.simulator is not None:
                await ctx.simulator.stop()

    app = FastAPI(title="dsp408-multiui", version=__version__, lifespan=lifespan, docs_url=None,
                  redoc_url=None, openapi_url=None)  # fmt: skip
    app.state.ctx = ctx

    @app.post("/api/login")
    async def login(body: LoginBody, request: Request, response: Response) -> dict[str, Any]:
        address = request.client.host if request.client else "unknown"
        try:
            client = auth.login(body.pin, body.name, address)
        except RateLimitedError as exc:
            return JSONResponse(  # type: ignore[return-value]
                {"error": "rate_limited", "message": str(exc)},
                status_code=429,
                headers={"Retry-After": str(int(exc.retry_after) + 1)},
            )
        except LoginError:
            return JSONResponse(  # type: ignore[return-value]
                {"error": "wrong_code", "message": "wrong code"}, status_code=401
            )
        response.set_cookie(
            SESSION_COOKIE, client.token, httponly=True, samesite="strict", path="/"
        )
        return {"client_id": client.client_id, "name": client.name}

    @app.post("/api/logout")
    async def logout(request: Request, response: Response) -> dict[str, bool]:
        client = auth.logout(request.cookies.get(SESSION_COOKIE))
        if client is not None:
            lock.release(client.client_id)
            await hub.close_client_sessions(client.client_id)
        response.delete_cookie(SESSION_COOKIE, path="/")
        return {"ok": True}

    @app.get("/api/session")
    async def current_session(request: Request) -> JSONResponse:
        client = auth.get(request.cookies.get(SESSION_COOKIE))
        if client is None:
            return JSONResponse({"authenticated": False}, status_code=401)
        return JSONResponse(
            {"authenticated": True, "client_id": client.client_id, "name": client.name}
        )

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "device_status": session.status.value,
            "version": __version__,
            "demo": config.demo,
        }

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        client = auth.get(websocket.cookies.get(SESSION_COOKIE))
        if not _origin_allowed(websocket):
            await websocket.close(code=4403)
            return
        if client is None:
            await websocket.close(code=4401)
            return
        await websocket.accept()
        await hub.serve(websocket, client)

    @app.get("/{path:path}", include_in_schema=False)
    async def static(path: str) -> Response:
        index = web_root / "index.html"
        if not index.is_file():
            return HTMLResponse(PLACEHOLDER_HTML)
        candidate = (web_root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(web_root.resolve()):
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app


async def _lock_ticker(lock: LockManager) -> None:
    while True:
        await asyncio.sleep(LOCK_TICK_S)
        lock.expire()


async def _resync_loop(session: DeviceSession, interval: float) -> None:
    while True:
        await asyncio.sleep(interval)
        with contextlib.suppress(Exception):
            await session.resync()
