"""WebSocket hub: fan-out of state, meters, device status and lock; request handling.

Each client has a bounded outgoing queue drained by its own task, so a slow client never
blocks the others. Meter frames are dropped for a client whose queue is full; any other
overflow closes that client, which reconnects and gets a fresh snapshot.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeGuard

from fastapi import WebSocket, WebSocketDisconnect

from tracks_dsp_controller import __version__
from tracks_dsp_controller.aio import cancel_and_wait
from tracks_dsp_controller.device.pipeline import CommandTimeoutError, PipelineClosedError
from tracks_dsp_controller.device.session import DeviceSession, DeviceStatus, DeviceUnavailableError
from tracks_dsp_controller.protocol import codecs as c
from tracks_dsp_controller.protocol.meters import MeterReading
from tracks_dsp_controller.server.auth import (
    AuthManager,
    ClientSession,
    LoginError,
    RateLimitedError,
)
from tracks_dsp_controller.server.lock import LockManager, LockState
from tracks_dsp_controller.server.master import MasterManager, MasterState
from tracks_dsp_controller.server.settings import ServerConfig
from tracks_dsp_controller.state.registry import HARDWARE_VERIFIED, ParamError, is_verified
from tracks_dsp_controller.state.store import Patch, Snapshot, StateStore, StoreEvent

log = logging.getLogger(__name__)

QUEUE_SIZE = 256
SHUTDOWN_FLUSH_S = 0.3  # lets the clients get the "shutdown" message before the server stops
# Accepted while the session's screen is locked.
SCREEN_LOCK_TYPES = {"screen.lock", "screen.unlock"}
ACTIVITY_TYPES = {
    "set",
    "preset.recall",
    "preset.store",
    "preset.import",
    "preset.export",
    "lock.acquire",
    "activity",
    "resync",
}
# Requests handled in their own task, so that the client's next messages are read meanwhile.
BACKGROUND_TYPES = {
    "set",
    "preset.recall",
    "preset.store",
    "preset.import",
    "preset.export",
    "link.set",
    "resync",
}
PRESET_FILE_MAX_BYTES = 16 * 1024  # a DSP 408 preset file is 1452 bytes


class RequestError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code


# Value ranges for the UI's controls (the server still clamps everything it receives).
LIMITS: dict[str, Any] = {
    "gain_db": [c.GAIN_MIN_DB, c.GAIN_MAX_DB],
    "eq_gain_db": [c.EQ_GAIN_MIN_DB, c.EQ_GAIN_MAX_DB],
    "attack_ms": list(c.ATTACK_RANGE_MS),
    "release_ms": list(c.RELEASE_RANGE_MS),
    "gate_release_ms": list(c.GATE_RELEASE_RANGE_MS),
    "hold_ms": list(c.HOLD_RANGE_MS),
    "threshold_db": [c.THRESHOLD_MIN_DB, c.DYNAMICS_THRESHOLD_MAX_DB],
    "gate_threshold_db": [c.THRESHOLD_MIN_DB, c.GATE_THRESHOLD_MAX_DB],
    "knee_db": [0, c.KNEE_MAX_DB],
    "channel_name_length": c.CHANNEL_NAME_LENGTH,
    "preset_name_length": c.PRESET_NAME_LENGTH,
    "speed_of_sound_m_s": c.SPEED_OF_SOUND_M_S,
}


@dataclass(eq=False)
class Client:
    session: ClientSession
    websocket: WebSocket
    queue: asyncio.Queue[dict[str, Any]] = field(
        default_factory=lambda: asyncio.Queue(maxsize=QUEUE_SIZE)
    )
    sender: asyncio.Task[None] | None = None
    # Requests still waiting for the device (strong references: the loop only keeps weak ones).
    writes: set[asyncio.Task[None]] = field(default_factory=set)

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
        master: MasterManager,
    ) -> None:
        self.config = config
        self.session = session
        self.store = store
        self.auth = auth
        self.lock = lock
        self.master = master
        self.clients: set[Client] = set()
        # Stops the server process (set by the CLI: uvicorn's should_exit).
        self.request_exit: Callable[[], None] | None = None
        self._meter_seq = 0
        store.subscribe(self._on_store)
        session.on_meters(self._on_meters)
        session.on_status(self._on_status)
        session.on_profile(self._on_profile)
        lock.on_change(self._on_lock)
        master.on_change(self._on_master)

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
            "model_tested": self.session.model_tested,
        }

    def _on_status(self, status: DeviceStatus, error: str | None) -> None:
        self.broadcast(self.device_message())

    def _on_profile(self, profile: object) -> None:
        """Another model was detected: every client gets the new channel counts and ranges."""
        for client in list(self.clients):
            self._send(client, self.hello_message(client))

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

    def master_message(self, state: MasterState | None = None) -> dict[str, Any]:
        state = state or self.master.state()
        return {
            "type": "master",
            "owner_id": state.owner_id,
            "owner_name": state.owner_name,
            "logins_blocked": state.logins_blocked,
        }

    def _on_master(self, state: MasterState) -> None:
        self.broadcast(self.master_message(state))

    def clients_message(self) -> dict[str, Any]:
        unique = {cl.id: cl.session.name for cl in self.clients}
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
            "screen_locked": client.session.screen_locked,
            "server_version": __version__,
            "demo": self.config.demo,
            "experimental": self.config.allow_unverified,
            "verified_kinds": sorted(HARDWARE_VERIFIED),
            "profile": {
                "input_count": p.input_count,
                "output_count": p.output_count,
                "preset_count": p.preset_count,
                "peq_types": list(p.peq_types),
                "slopes": list(p.slopes),
                "ratios": list(c.COMPRESSOR_RATIOS),
                "freq_min_hz": p.freq_min_hz,
                "freq_max_hz": p.freq_max_hz,
                "freq_steps": p.freq_steps,
                "q_min": p.q_min,
                "q_max": p.q_max,
                "q_steps": p.q_steps,
                "delay_sample_rate_hz": p.delay_sample_rate_hz,
                "delay_max_ms": p.delay_max_ms,
                "meter_floor_db": p.meter_floor_db,
                "meter_clip_db": p.meter_clip_db,
            },
            "limits": LIMITS,
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
        self._send(client, self.master_message())
        self.master.presence(client.id, True)
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
                if message.get("type") in BACKGROUND_TYPES:
                    # Do not wait for the DSP. The next values of a dragged control must reach
                    # the pipeline while this one is in flight, so that it coalesces them
                    # instead of replaying every step. Order is kept: up to the pipeline's
                    # queue, a write runs without yielding, and tasks start in creation order.
                    # A long sequence (an import, a recall on a slow link) can last longer than
                    # the client's silence limit (12 s): pings must still be answered meanwhile.
                    task = asyncio.create_task(self._dispatch(client, message))
                    client.writes.add(task)
                    task.add_done_callback(client.writes.discard)
                else:
                    await self._dispatch(client, message)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            self.clients.discard(client)
            if client.sender is not None:
                await cancel_and_wait(client.sender)
            if not any(cl.id == client.id for cl in self.clients):
                self.master.presence(client.id, False)
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
        if client.session.screen_locked and kind not in SCREEN_LOCK_TYPES:
            if kind != "activity":  # interactions behind the lock screen are not activity
                self._send(client, _result(req, "screen_locked", "the screen is locked"))
            return
        if kind in ACTIVITY_TYPES:
            self.lock.touch(client.id)
        if kind == "activity":
            return
        try:
            extra = await self._handle(client, str(kind), message)
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
        self._send(client, {**_result(req), **(extra or {})})

    def _require_lock(self, client: Client) -> None:
        """Control (the `lock.*` messages): only its holder may write while someone has it."""
        if not self.lock.can_write(client.id):
            owner = self.lock.state().owner_name or "another client"
            raise RequestError("locked", f"{owner} has control")

    def set_screen_lock(self, session: ClientSession, locked: bool) -> None:
        """Lock or unlock the screen of a browser session; all its tabs follow."""
        session.screen_locked = locked
        for client in [cl for cl in self.clients if cl.session is session]:
            self._send(client, {"type": "screen_lock", "locked": locked})

    async def _handle(
        self, client: Client, kind: str, message: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Handle a request; the fields returned are added to its (successful) result."""
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
            case "preset.import":
                self._require_lock(client)
                data = _preset_file(message.get("data"))
                slot = message.get("slot")
                if slot is not None:
                    slot = _int(message, "slot")
                name = message.get("name")
                if name is not None and not isinstance(name, str):
                    raise RequestError("invalid", "name must be a string")
                loaded = await self.session.import_preset(data, client.id, slot=slot, name=name)
                return {"name": loaded.name, "notes": list(loaded.notes)}
            case "preset.export":
                exported = await self.session.export_preset()
                return {
                    "filename": exported.filename,
                    "data": base64.b64encode(exported.data).decode("ascii"),
                    "notes": list(exported.notes),
                }
            case "link.set":
                self._require_lock(client)
                if not is_verified("link") and not self.config.allow_unverified:
                    raise RequestError("experimental", "links are not verified on a DSP 408")
                side, groups = message.get("side"), message.get("groups")
                if not isinstance(side, str) or not _int_groups(groups):
                    raise RequestError("invalid", "side must be a string, groups lists of ints")
                await self.session.set_links(side, groups, client.id)
            case "lock.acquire":
                if not self.lock.acquire(client.id, client.session.name):
                    raise RequestError("locked", "another client has control")
            case "lock.release":
                if not self.lock.release(client.id):
                    raise RequestError("invalid", "you do not have control")
            case "master.acquire":
                if not self.master.acquire(client.id, client.session.name):
                    owner = self.master.state().owner_name or "another client"
                    raise RequestError("master_taken", f"{owner} is the master")
            case "master.release":
                if not self.master.release(client.id):
                    raise RequestError("not_master", "you are not the master")
            case "logins.block":
                blocked = message.get("blocked")
                if not isinstance(blocked, bool):
                    raise RequestError("invalid", "blocked must be true or false")
                if not self.master.block_logins(client.id, blocked):
                    raise RequestError("not_master", "only the master can block new connections")
            case "client.kick":
                await self.kick(client, message.get("client_id"))
            case "server.shutdown":
                await self.shutdown(client)
            case "screen.lock":
                self.set_screen_lock(client.session, True)
            case "screen.unlock":
                pin = message.get("pin")
                if not isinstance(pin, str):
                    raise RequestError("invalid", "pin must be a string")
                address = client.websocket.client.host if client.websocket.client else "unknown"
                try:
                    self.auth.check_pin(pin, address)
                except RateLimitedError as exc:
                    raise RequestError("rate_limited", str(exc)) from exc
                except LoginError as exc:
                    raise RequestError("wrong_code", "wrong code") from exc
                self.set_screen_lock(client.session, False)
            case "settings.set":
                self._require_lock(client)
                rate = message.get("meter_rate_hz")
                if isinstance(rate, bool) or not isinstance(rate, int | float):
                    raise RequestError("invalid", "meter_rate_hz must be a number")
                self.session.meter_rate_hz = rate
                self.broadcast(self.settings_message())
            case "resync":
                await self.session.resync()
            case _:
                raise RequestError("invalid", f"unknown message type {kind!r}")
        return None

    async def shutdown(self, client: Client) -> None:
        """Disconnect from the DSP cleanly, then stop the server (every client is told)."""
        if self.request_exit is None:
            raise RequestError("unsupported", "this server cannot be shut down from the app")
        self._require_lock(client)
        master = self.master.state()
        if master.owner_id is not None and master.owner_id != client.id:
            raise RequestError("not_master", f"{master.owner_name} is the master")
        log.warning("shutdown requested by %s", client.session.name)
        self.broadcast({"type": "shutdown", "by": client.session.name})
        await self.session.stop()  # closes the TCP connection: the DSP is free for another client
        await asyncio.sleep(SHUTDOWN_FLUSH_S)
        self.request_exit()

    async def kick(self, master: Client, target: object) -> None:
        """The master disconnects a client: its session ends, it gets the login screen."""
        if not self.master.is_master(master.id):
            raise RequestError("not_master", "only the master can disconnect clients")
        if not isinstance(target, str):
            raise RequestError("invalid", "client_id must be a string")
        if target == master.id:
            raise RequestError("invalid", "you cannot disconnect yourself")
        if self.auth.logout_client(target) is None:
            raise RequestError("invalid", "no such client")
        self.lock.release(target)
        log.info("client %s disconnected by the master %s", target, master.session.name)
        await self.close_client_sessions(target, reason=f"Disconnected by {master.session.name}")

    async def close_client_sessions(self, client_id: str, reason: str = "") -> None:
        for client in [cl for cl in self.clients if cl.id == client_id]:
            with contextlib.suppress(Exception):
                # A close reason is at most 123 bytes.
                await client.websocket.close(
                    code=4401, reason=reason.encode()[:123].decode(errors="ignore")
                )


def _int(message: dict[str, Any], key: str) -> int:
    value = message.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise RequestError("invalid", f"{key} must be an integer")
    return value


def _preset_file(data: object) -> bytes:
    """The bytes of a preset file sent in base64."""
    if not isinstance(data, str) or len(data) > PRESET_FILE_MAX_BYTES * 4 // 3 + 4:
        raise RequestError("invalid", "data must be a preset file in base64")
    try:
        return base64.b64decode(data, validate=True)
    except binascii.Error as exc:
        raise RequestError("invalid", "data is not valid base64") from exc


def _result(req: Any, error: str | None = None, message: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"type": "result", "req": req, "ok": error is None}
    if error is not None:
        result["error"] = error
        result["message"] = message or error
    return result


def _int_groups(groups: object) -> TypeGuard[list[list[int]]]:
    return isinstance(groups, list) and all(
        isinstance(g, list) and all(isinstance(i, int) and not isinstance(i, bool) for i in g)
        for g in groups
    )
