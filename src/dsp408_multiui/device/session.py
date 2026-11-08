"""Device session: owns the DSP connection, mirrors its state, polls meters, reconnects.

Lifecycle: ``connecting → initialising → online ↔ offline`` (docs/SPEC.md F-DEV-1..4). This is
the only module that talks to the transport.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from dsp408_multiui.device import reader
from dsp408_multiui.device.pipeline import CommandPipeline, PipelineClosedError
from dsp408_multiui.device.transport import DspConnection, TransportError, TransportTimeoutError
from dsp408_multiui.protocol import commands as cmd
from dsp408_multiui.protocol import config_map as cm
from dsp408_multiui.protocol import responses as rsp
from dsp408_multiui.protocol.codecs import PRESET_NAME_LENGTH, validate_name
from dsp408_multiui.protocol.meters import MeterError, MeterReading, decode_meters
from dsp408_multiui.protocol.profile import ProtocolProfile
from dsp408_multiui.state.convert import build_state
from dsp408_multiui.state.models import DeviceInfo, DeviceState
from dsp408_multiui.state.registry import ParamError, Write, resolve
from dsp408_multiui.state.store import StateStore

log = logging.getLogger(__name__)

METER_RATE_MIN_HZ = 1.0
METER_RATE_MAX_HZ = 10.0


class DeviceStatus(StrEnum):
    STOPPED = "stopped"
    CONNECTING = "connecting"
    INITIALISING = "initialising"
    ONLINE = "online"
    OFFLINE = "offline"


class DeviceUnavailableError(RuntimeError):
    """The device is not online."""


type StatusListener = Callable[[DeviceStatus, str | None], None]
type MeterListener = Callable[[MeterReading | None], None]
type ConnectionFactory = Callable[[], DspConnection]


def clamp_meter_rate(hz: float) -> float:
    return max(METER_RATE_MIN_HZ, min(METER_RATE_MAX_HZ, float(hz)))


class DeviceSession:
    def __init__(
        self,
        host: str,
        port: int,
        profile: ProtocolProfile,
        store: StateStore,
        *,
        meter_rate_hz: float = 5.0,
        reconnect_min_s: float = 1.0,
        reconnect_max_s: float = 30.0,
        connection_factory: ConnectionFactory | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.profile = profile
        self.store = store
        self._meter_rate_hz = clamp_meter_rate(meter_rate_hz)
        self.reconnect_min_s = reconnect_min_s
        self.reconnect_max_s = reconnect_max_s
        self._factory = connection_factory or self._default_connection
        self.status = DeviceStatus.STOPPED
        self.last_error: str | None = None
        self.info = DeviceInfo()
        self._status_listeners: list[StatusListener] = []
        self._meter_listeners: list[MeterListener] = []
        self._conn: DspConnection | None = None
        self._pipeline: CommandPipeline | None = None
        self._task: asyncio.Task[None] | None = None
        self._online = asyncio.Event()
        # Latest full value of each object parameter (PEQ band, filter, dynamics) written but
        # not acked yet: a partial write merges onto it rather than onto the acked state, so two
        # quick edits of different fields of one band both survive.
        self._inflight: dict[str, dict[str, Any]] = {}

    def _default_connection(self) -> DspConnection:
        # Built at each attempt, so host/port can change (embedded simulator, reconfiguration).
        return DspConnection(self.host, self.port, self.profile)

    # --- listeners ------------------------------------------------------------------------------
    def on_status(self, listener: StatusListener) -> Callable[[], None]:
        self._status_listeners.append(listener)
        return lambda: self._status_listeners.remove(listener)

    def on_meters(self, listener: MeterListener) -> Callable[[], None]:
        self._meter_listeners.append(listener)
        return lambda: self._meter_listeners.remove(listener)

    def _set_status(self, status: DeviceStatus, error: str | None = None) -> None:
        self.status = status
        self.last_error = error
        if status is DeviceStatus.ONLINE:
            self._online.set()
        else:
            self._online.clear()
        log.info("device %s%s", status.value, f": {error}" if error else "")
        for listener in list(self._status_listeners):
            try:
                listener(status, error)
            except Exception:
                log.exception("status listener failed")

    def _publish_meters(self, data: bytes | None) -> None:
        reading: MeterReading | None = None
        if data is not None:
            try:
                reading = decode_meters(data, self.profile)
            except MeterError as exc:
                log.debug("bad meter frame: %s", exc)
        for listener in list(self._meter_listeners):
            try:
                listener(reading)
            except Exception:
                log.exception("meter listener failed")

    # --- meter rate -----------------------------------------------------------------------------
    @property
    def meter_rate_hz(self) -> float:
        return self._meter_rate_hz

    @meter_rate_hz.setter
    def meter_rate_hz(self, hz: float) -> None:
        self._meter_rate_hz = clamp_meter_rate(hz)
        if self._pipeline is not None:
            self._pipeline.meter_interval = 1.0 / self._meter_rate_hz

    # --- lifecycle --------------------------------------------------------------------------------
    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="dsp-session")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self._teardown()
        self._set_status(DeviceStatus.STOPPED)

    async def wait_online(self, timeout: float | None = None) -> None:
        await asyncio.wait_for(self._online.wait(), timeout)

    async def _teardown(self) -> None:
        if self._pipeline is not None:
            await self._pipeline.stop()
            self._pipeline = None
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def _run(self) -> None:
        delay = self.reconnect_min_s
        while True:
            self._set_status(DeviceStatus.CONNECTING)
            conn = self._factory()
            try:
                await conn.connect()
                self._conn = conn
                self._set_status(DeviceStatus.INITIALISING)
                state = await self._read_state(conn, previous=None)
            except (TransportError, TransportTimeoutError, reader.UnexpectedResponseError,
                    cm.ConfigError) as exc:  # fmt: skip
                await self._teardown()
                self._set_status(DeviceStatus.OFFLINE, str(exc) or type(exc).__name__)
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.reconnect_max_s)
                continue
            self.store.replace(state)
            delay = self.reconnect_min_s
            pipeline = CommandPipeline(
                conn, meter_interval=1.0 / self._meter_rate_hz, on_meters=self._publish_meters
            )
            self._pipeline = pipeline
            pipeline.start()
            self._set_status(DeviceStatus.ONLINE)
            reason = await pipeline.wait_closed()
            await self._teardown()
            self._set_status(DeviceStatus.OFFLINE, str(reason) or type(reason).__name__)
            await asyncio.sleep(delay)

    async def _read_state(
        self, conn: reader.Requester, previous: DeviceState | None
    ) -> DeviceState:
        summary = await reader.read_info(conn)
        raw = cm.decode_config(await reader.read_config_blob(conn))
        await reader.activate(conn)
        parts = summary.identity.split()
        self.info = DeviceInfo(
            identity=summary.identity,
            model=parts[0] if parts else "",
            firmware=parts[1] if len(parts) > 1 else "",
        )
        return build_state(
            raw,
            self.profile,
            info=self.info,
            preset_names=summary.preset_names,
            active_slot=summary.active_slot,
            previous=previous,
        )

    def _require_pipeline(self) -> CommandPipeline:
        if self.status is not DeviceStatus.ONLINE or self._pipeline is None:
            raise DeviceUnavailableError(f"device is {self.status.value}")
        return self._pipeline

    # --- operations -------------------------------------------------------------------------------
    def resolve(self, path: str, value: Any) -> Write:
        """Validate a write without sending it (raises ``ParamError``)."""
        return resolve(path, value, self.store.state, self.profile)

    async def write(self, path: str, value: Any, origin: str) -> Write:
        """Send a parameter change; the store is updated after the device's ACK."""
        pipeline = self._require_pipeline()
        pending = self._inflight.get(path)
        if pending is not None and isinstance(value, dict):
            value = {**pending, **value}
        write = self.resolve(path, value)
        mine = {p: v for p, v in write.changes if isinstance(v, dict)}
        self._inflight.update(mine)
        try:
            await pipeline.submit(
                write.request, on_ack=lambda: self.store.apply(write.changes, origin)
            )
        finally:
            for p, v in mine.items():
                if self._inflight.get(p) is v:
                    del self._inflight[p]
        return write

    async def recall(self, slot: int, origin: str) -> None:
        if not 0 <= slot <= self.profile.preset_count:
            raise ParamError(f"preset slot out of range: {slot}")
        pipeline = self._require_pipeline()
        try:
            async with pipeline.exclusive() as conn:
                reader.expect(await conn.request(cmd.RecallPreset(slot)), rsp.Ack)
                state = await self._read_state(conn, previous=self.store.state)
        except (TransportError, TransportTimeoutError) as exc:
            raise DeviceUnavailableError(str(exc)) from exc
        log.info("preset %d recalled by %s", slot, origin)
        self.store.replace(state)

    async def store_preset(self, slot: int, name: str, origin: str) -> None:
        if not 1 <= slot <= self.profile.preset_count:
            raise ParamError(f"user preset slot must be 1..{self.profile.preset_count}")
        try:
            validate_name(name, PRESET_NAME_LENGTH)
        except ValueError as exc:
            raise ParamError(str(exc)) from exc
        pipeline = self._require_pipeline()
        try:
            async with pipeline.exclusive() as conn:
                reader.expect(await conn.request(cmd.SetPresetName(name)), rsp.Ack)
                reader.expect(await conn.request(cmd.StorePreset(slot)), rsp.Ack)
                await reader.activate(conn)
        except (TransportError, TransportTimeoutError) as exc:
            raise DeviceUnavailableError(str(exc)) from exc
        log.info("preset %d stored as %r by %s", slot, name, origin)
        self.store.apply(
            [(f"presets.{slot - 1}.name", name), ("active_slot", slot), ("preset_name", name)],
            origin,
        )

    async def resync(self) -> None:
        """Re-read the whole configuration (front-panel changes)."""
        pipeline = self._require_pipeline()
        try:
            async with pipeline.exclusive() as conn:
                state = await self._read_state(conn, previous=self.store.state)
        except (TransportError, TransportTimeoutError) as exc:
            raise DeviceUnavailableError(str(exc)) from exc
        self.store.replace(state)


__all__ = [
    "DeviceSession",
    "DeviceStatus",
    "DeviceUnavailableError",
    "PipelineClosedError",
    "clamp_meter_rate",
]
