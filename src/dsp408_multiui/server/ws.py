"""WebSocket hub: fan-out of state, meters, device status and lock; request handling.

Each client has a bounded outgoing queue drained by its own task, so a slow client never
blocks the others. Meter frames are dropped for a client whose queue is full; any other
overflow closes that client, which reconnects and gets a fresh snapshot.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from dsp408_multiui import __version__
from dsp408_multiui.device.pipeline import CommandTimeoutError, PipelineClosedError
from dsp408_multiui.device.session import DeviceSession, DeviceStatus, DeviceUnavailableError
from dsp408_multiui.protocol.codecs import COMPRESSOR_RATIOS
from dsp408_multiui.protocol.meters import MeterReading
from dsp408_multiui.server.auth import AuthManager, ClientSession
from dsp408_multiui.server.lock import LockManager, LockState
from dsp408_multiui.server.settings import ServerConfig
from dsp408_multiui.state.registry import HARDWARE_VERIFIED, ParamError
from dsp408_multiui.state.store import Patch, Snapshot, StateStore, StoreEvent

log = logging.getLogger(__name__)

QUEUE_SIZE = 256
ACTIVITY_TYPES = {"set", "preset.recall", "preset.store", "lock.acquire", "activity", "resync"}


class RequestError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code


@dataclass(eq=False)
class Client:
    session: ClientSession
    websocket: WebSocket
    queue: asyncio.Queue[dict[str, Any]] = field(
        default_factory=lambda: asyncio.Queue(maxsize=QUEUE_SIZE)
    )
    sender: asyncio.Task[None] | None = None

    @property
    def id(self) -> str:
        return self.session.client_id


class Hub:
    def __init__(
        self,
        config: ServerConfig,
        session: DeviceSession,
        store: StateStore,
        auth: AuthManager,
        lock: LockManager,
    ) -> None:
        self.config = config
        self.session = session
        self.store = store
        self.auth = auth
        self.lock = lock
        self.clients: set[Client] = set()
        self._meter_seq = 0
        store.subscribe(self._on_store)
        session.on_meters(self._on_meters)
        session.on_status(self._on_status)
        lock.on_change(self._on_lock)

    # --- outgoing ---------------------------------------------------------------------------------
    def _send(self, client: Client, message: dict[str, Any], *, droppable: bool = False) -> None:
        try:
            client.queue.put_nowait(message)
        except asyncio.QueueFull:
            if droppable:
                return
            log.warning("client %s is too slow, closing it", client.id)
            if client.sender is not None:
                client.sender.cancel()

    def broadcast(self, message: dict[str, Any], *, droppable: bool = False) -> None:
        for client in list(self.clients):
            self._send(client, message, droppable=droppable)

    def _on_store(self, event: StoreEvent) -> None:
        if isinstance(event, Snapshot):
            self.broadcast({"type": "snapshot", "rev": event.rev, "state": event.state})
        elif isinstance(event, Patch):
            changes = [{"path": path, "value": value} for path, value in event.changes]
            self.broadcast(
                {"type": "patch", "rev": event.rev, "changes": changes, "origin": event.origin}
            )

    def _on_meters(self, reading: MeterReading | None) -> None:
        self._meter_seq += 1
        message: dict[str, Any] = {"type": "meters", "seq": self._meter_seq}
        if reading is None:
            message["levels"] = None
        else:
            message.update(
                levels=[None if lv is None else round(lv, 1) for lv in reading.levels_db],
                clip=list(reading.clip),
                limit=None if reading.limit is None else list(reading.limit),
                comp=None if reading.comp is None else list(reading.comp),
                input_clip=reading.input_clip_flag,
            )
        self.broadcast(message, droppable=True)

    def device_message(self) -> dict[str, Any]:
        info = self.session.info
        return {
            "type": "device",
            "status": self.session.status.value,
            "error": self.session.last_error,
            "model": info.model,
            "firmware": info.firmware,
            "identity": info.identity,
        }

    def _on_status(self, status: DeviceStatus, error: str | None) -> None:
        self.broadcast(self.device_message())

    def lock_message(self, state: LockState | None = None) -> dict[str, Any]:
        state = state or self.lock.state()
        remaining = (
            None
            if state.idle_expires_at is None
            else max(0.0, round(state.idle_expires_at - self.lock.clock(), 1))
        )
        return {
            "type": "lock",
            "owner_id": state.owner_id,
            "owner_name": state.owner_name,
            "idle_remaining_s": remaining,
            "idle_timeout_s": self.lock.idle_timeout,
        }

    def _on_lock(self, state: LockState) -> None:
        self.broadcast(self.lock_message(state))

    def clients_message(self) -> dict[str, Any]:
        unique = {c.id: c.session.name for c in self.clients}
        return {
            "type": "clients",
            "clients": [{"id": cid, "name": name} for cid, name in sorted(unique.items())],
        }

    def settings_message(self) -> dict[str, Any]:
        return {
            "type": "settings",
            "meter_rate_hz": self.session.meter_rate_hz,
            "lock_idle_timeout_s": self.lock.idle_timeout,
        }

    def hello_message(self, client: Client) -> dict[str, Any]:
        p = self.session.profile
        return {
            "type": "hello",
            "client_id": client.id,
            "name": client.session.name,
            "server_version": __version__,
            "simulator": self.config.simulator,
            "experimental": self.config.allow_unverified,
            "verified_kinds": sorted(HARDWARE_VERIFIED),
            "profile": {
                "input_count": p.input_count,
                "output_count": p.output_count,
                "preset_count": p.preset_count,
                "peq_types": list(p.peq_types),
                "slopes": list(p.slopes),
                "ratios": list(COMPRESSOR_RATIOS),
                "freq_min_hz": p.freq_min_hz,
                "freq_max_hz": p.freq_max_hz,
                "q_min": p.q_min,
                "q_max": p.q_max,
                "delay_max_ms": p.delay_max_ms,
                "meter_floor_db": p.meter_floor_db,
                "meter_clip_db": p.meter_clip_db,
            },
            "settings": self.settings_message(),
        }

    # --- connection -------------------------------------------------------------------------------
    async def serve(self, websocket: WebSocket, session: ClientSession) -> None:
        client = Client(session, websocket)
        self.clients.add(client)
        client.sender = asyncio.create_task(self._sender(client))
        self._send(client, self.hello_message(client))
        snap = self.store.snapshot()
        self._send(client, {"type": "snapshot", "rev": snap.rev, "state": snap.state})
        self._send(client, self.device_message())
        self._send(client, self.lock_message())
        self.broadcast(self.clients_message())
        try:
            while True:
                try:
                    message = json.loads(await websocket.receive_text())
                except json.JSONDecodeError:
                    self._send(client, _result(None, "invalid", "message is not JSON"))
                    continue
                if not isinstance(message, dict):
                    self._send(client, _result(None, "invalid", "message must be an object"))
                    continue
                if self.auth.get(session.token) is None:  # logged out from another tab
                    await websocket.close(code=4401)
                    break
                await self._dispatch(client, message)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            self.clients.discard(client)
            if client.sender is not None:
                client.sender.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await client.sender
            self.broadcast(self.clients_message())

    async def _sender(self, client: Client) -> None:
        try:
            while True:
                message = await client.queue.get()
                await client.websocket.send_text(json.dumps(message))
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                await client.websocket.close()
            raise
        except Exception:  # client went away
            with contextlib.suppress(Exception):
                await client.websocket.close()

    # --- requests ------------------------------------------------------------------------------
    async def _dispatch(self, client: Client, message: dict[str, Any]) -> None:
        kind = message.get("type")
        req = message.get("req")
        if kind == "ping":
            self._send(client, {"type": "pong", "req": req})
            return
        if kind in ACTIVITY_TYPES:
            self.lock.touch(client.id)
        if kind == "activity":
            return
        try:
            await self._handle(client, str(kind), message)
        except RequestError as exc:
            self._send(client, _result(req, exc.code, exc.message))
            return
        except ParamError as exc:
            self._send(client, _result(req, "invalid", str(exc)))
            return
        except DeviceUnavailableError as exc:
            self._send(client, _result(req, "device_offline", str(exc)))
            return
        except PipelineClosedError as exc:
            self._send(client, _result(req, "device_offline", str(exc)))
            return
        except CommandTimeoutError as exc:
            self._send(client, _result(req, "device_timeout", str(exc)))
            return
        self._send(client, _result(req))

    def _require_lock(self, client: Client) -> None:
        if not self.lock.can_write(client.id):
            owner = self.lock.state().owner_name or "another client"
            raise RequestError("locked", f"controls are locked by {owner}")

    async def _handle(self, client: Client, kind: str, message: dict[str, Any]) -> None:
        match kind:
            case "set":
                self._require_lock(client)
                path, value = message.get("path"), message.get("value")
                if not isinstance(path, str):
                    raise RequestError("invalid", "path must be a string")
                write = self.session.resolve(path, value)
                if not write.hardware_verified and not self.config.allow_unverified:
                    raise RequestError(
                        "experimental",
                        f"{write.kind} is not verified on a DSP 408 yet (use --experimental)",
                    )
                await self.session.write(path, value, client.id)
            case "preset.recall":
                self._require_lock(client)
                await self.session.recall(_int(message, "slot"), client.id)
            case "preset.store":
                self._require_lock(client)
                name = message.get("name")
                if not isinstance(name, str):
                    raise RequestError("invalid", "name must be a string")
                await self.session.store_preset(_int(message, "slot"), name, client.id)
            case "lock.acquire":
                if not self.lock.acquire(client.id, client.session.name):
                    raise RequestError("locked", "the lock is held by another client")
            case "lock.release":
                if not self.lock.release(client.id):
                    raise RequestError("invalid", "you do not hold the lock")
            case "settings.set":
                self._require_lock(client)
                rate = message.get("meter_rate_hz")
                if isinstance(rate, bool) or not isinstance(rate, int | float):
                    raise RequestError("invalid", "meter_rate_hz must be a number")
                self.session.meter_rate_hz = rate
                self.broadcast(self.settings_message())
            case "rename":
                name = message.get("name")
                if not isinstance(name, str):
                    raise RequestError("invalid", "name must be a string")
                renamed = self.auth.rename(client.session.token, name)
                if renamed is not None:
                    self.lock.rename(client.id, renamed.name)
                self._send(client, {"type": "self", "name": client.session.name})
                self.broadcast(self.clients_message())
            case "resync":
                await self.session.resync()
            case _:
                raise RequestError("invalid", f"unknown message type {kind!r}")

    async def close_client_sessions(self, client_id: str) -> None:
        for client in [c for c in self.clients if c.id == client_id]:
            with contextlib.suppress(Exception):
                await client.websocket.close(code=4401)


def _int(message: dict[str, Any], key: str) -> int:
    value = message.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise RequestError("invalid", f"{key} must be an integer")
    return value


def _result(req: Any, error: str | None = None, message: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"type": "result", "req": req, "ok": error is None}
    if error is not None:
        result["error"] = error
        result["message"] = message or error
    return result
