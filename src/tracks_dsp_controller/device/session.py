"""Device session: owns the DSP connection, mirrors its state, polls meters, reconnects.

Lifecycle: ``connecting → initialising → online ↔ offline`` (docs/ARCHITECTURE.md §4). This is
the only module that talks to the transport.

With ``model="auto"`` the session reads the device's identity first and switches to the
protocol profile of the model it reports (DSP 408, 206 or 204); with a model key it refuses a
device that reports another model.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable
from enum import StrEnum
from typing import Any

from tracks_dsp_controller.aio import cancel_and_wait
from tracks_dsp_controller.device import reader
from tracks_dsp_controller.device.pipeline import (
    CommandPipeline,
    CommandTimeoutError,
    PipelineClosedError,
)
from tracks_dsp_controller.device.transport import (
    DspConnection,
    TransportError,
    TransportTimeoutError,
)
from tracks_dsp_controller.protocol import commands as cmd
from tracks_dsp_controller.protocol import config_map as cm
from tracks_dsp_controller.protocol import responses as rsp
from tracks_dsp_controller.protocol.codecs import PRESET_NAME_LENGTH, validate_name
from tracks_dsp_controller.protocol.links import LinkError, link_requests, masks_for, normalise
from tracks_dsp_controller.protocol.meters import MeterError, MeterReading, decode_meters
from tracks_dsp_controller.protocol.profile import (
    MODELS,
    TESTED_MODELS,
    ProtocolProfile,
    detect_model,
    load_profile,
)
from tracks_dsp_controller.state.convert import build_state
from tracks_dsp_controller.state.models import DeviceInfo, DeviceState
from tracks_dsp_controller.state.registry import ParamError, Write, resolve
from tracks_dsp_controller.state.store import StateStore

log = logging.getLogger(__name__)

METER_RATE_MIN_HZ = 1.0
METER_RATE_MAX_HZ = 10.0
RESYNC_DELAY_S = 0.5  # after a write left unanswered: let the link settle, then re-read

# A multi-request sequence (recall, store, links, config read) can fail with these.
SEQUENCE_ERRORS = (
    TransportError,
    TransportTimeoutError,
    reader.UnexpectedResponseError,
    cm.ConfigError,
)


class DeviceStatus(StrEnum):
    STOPPED = "stopped"
    CONNECTING = "connecting"
    INITIALISING = "initialising"
    ONLINE = "online"
    OFFLINE = "offline"


class DeviceUnavailableError(RuntimeError):
    """The device is not online."""


class ModelError(RuntimeError):
    """The device is not a model this session can drive."""


AUTO = "auto"

type StatusListener = Callable[[DeviceStatus, str | None], None]
type ProfileListener = Callable[[ProtocolProfile], None]
type ProfileFactory = Callable[[str], ProtocolProfile]
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
        model: str | None = None,
        profile_for: ProfileFactory | None = None,
    ) -> None:
        """``model``: None = use ``profile`` as is (no identity check), "auto" = detect the
        model, or a model key ("408", "206", "204") the device must report.
        ``profile_for`` builds the profile of a model key (default: the built-in one)."""
        if model is not None and model != AUTO and model not in MODELS:
            raise ValueError(f"unknown model {model!r}; choose from auto, {', '.join(MODELS)}")
        self.host = host
        self.port = port
        self.profile = profile
        self.model = model
        self._profile_for = profile_for or (lambda key: load_profile(model=key))
        self._profile_listeners: list[ProfileListener] = []
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
        self._resync_task: asyncio.Task[None] | None = None

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

    def on_profile(self, listener: ProfileListener) -> Callable[[], None]:
        """Called when the session switches to another model's profile (before the snapshot)."""
        self._profile_listeners.append(listener)
        return lambda: self._profile_listeners.remove(listener)

    @property
    def model_key(self) -> str | None:
        """Model of the current profile ("408", "206", "204"), from its model name."""
        return detect_model(self.profile.model)

    @property
    def model_tested(self) -> bool:
        """Whether this project verified the current model on real hardware."""
        return self.model_key in TESTED_MODELS

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
        if self._resync_task is not None:
            await cancel_and_wait(self._resync_task)
            self._resync_task = None
        if self._task is not None:
            await cancel_and_wait(self._task)
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
                await self._identify(conn)
                state = await self._read_state(conn, previous=None)
            except (TransportError, TransportTimeoutError, reader.UnexpectedResponseError,
                    cm.ConfigError, ModelError) as exc:  # fmt: skip
                await self._teardown()
                self._set_status(DeviceStatus.OFFLINE, str(exc) or type(exc).__name__)
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.reconnect_max_s)
                continue
            self.store.replace(self._after_reconnect(state))
            delay = self.reconnect_min_s
            pipeline = CommandPipeline(
                conn,
                meter_interval=1.0 / self._meter_rate_hz,
                on_meters=self._publish_meters,
                # no frame at all for this long: the link is dead (4 s with the 0.5 s floor)
                dead_after_s=8 * self.profile.command_timeout_s,
            )
            self._pipeline = pipeline
            pipeline.start()
            self._set_status(DeviceStatus.ONLINE)
            reason = await pipeline.wait_closed()
            await self._teardown()
            self._set_status(DeviceStatus.OFFLINE, str(reason) or type(reason).__name__)
            await asyncio.sleep(delay)

    async def _identify(self, conn: reader.Requester) -> None:
        """Check the device's model and switch to its profile (``model`` "auto" or a key)."""
        if self.model is None:
            return
        identity = await reader.read_identity(conn)
        detected = detect_model(identity)
        if self.model == AUTO:
            if detected is None:
                raise ModelError(
                    f"unknown device {identity!r}: only the DSP 408, 206 and 204 are supported"
                )
            key = detected
        else:
            if detected is not None and detected != self.model:
                raise ModelError(
                    f"the device is a DSP {detected} ({identity}), not a DSP {self.model}: "
                    "start with --model auto"
                )
            key = self.model
        if key != self.model_key:
            self.profile = self._profile_for(key)
            log.info("device %r: using the DSP %s profile", identity, key)
            if key not in TESTED_MODELS:
                log.warning(
                    "the DSP %s has not been tested by this project: its protocol was checked "
                    "against captures and other projects only",
                    key,
                )
            for listener in list(self._profile_listeners):
                try:
                    listener(self.profile)
                except Exception:
                    log.exception("profile listener failed")
        conn.profile = self.profile

    async def _read_state(
        self, conn: reader.Requester, previous: DeviceState | None
    ) -> DeviceState:
        summary = await reader.read_info(conn)
        raw = cm.decode_config(await reader.read_config_blob(conn), cm.layout_for(self.profile))
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

    # --- "modified" (unsaved changes) -------------------------------------------------------
    @staticmethod
    def _same_config(a: DeviceState, b: DeviceState) -> bool:
        return a.model_dump(exclude={"modified"}) == b.model_dump(exclude={"modified"})

    def _after_reconnect(self, state: DeviceState) -> DeviceState:
        """After a (re)connection: keep what we knew if the DSP is where we left it."""
        previous = self.store.state if self.store.rev else None
        if previous is None or previous.active_slot != state.active_slot:
            return state  # first connection, or another preset: unknown
        if (len(previous.inputs), len(previous.outputs)) != (len(state.inputs), len(state.outputs)):
            return state  # another model
        same = self._same_config(previous, state)
        return state.model_copy(update={"modified": previous.modified if same else True})

    def _with_modified(self, changes: tuple[tuple[str, Any], ...]) -> list[tuple[str, Any]]:
        """A write's changes, plus ``modified`` when it becomes true."""
        extra = [] if self.store.state.modified is True else [("modified", True)]
        return [*changes, *extra]

    def _require_pipeline(self) -> CommandPipeline:
        if self.status is not DeviceStatus.ONLINE or self._pipeline is None:
            raise DeviceUnavailableError(f"device is {self.status.value}")
        return self._pipeline

    @contextlib.asynccontextmanager
    async def _sequence(self, what: str, *, abort: bool = True) -> AsyncIterator[reader.Requester]:
        """Run a multi-request sequence alone on the connection.

        If it fails half-way (no answer, a wrong answer), part of it may have reached the DSP and
        its state is unknown: with ``abort`` the connection is dropped, so the session reconnects
        and re-reads everything rather than showing a guess.
        """
        pipeline = self._require_pipeline()
        try:
            async with pipeline.exclusive() as conn:
                yield conn
        except SEQUENCE_ERRORS as exc:
            if abort:
                log.warning("%s failed (%s): reconnecting to re-read the DSP", what, exc)
                pipeline.abort(exc)
            raise DeviceUnavailableError(f"{what} failed: {exc}") from exc

    def _resync_soon(self) -> None:
        """A write was left unanswered: the DSP may or may not have applied it. Re-read."""
        if self._resync_task is None or self._resync_task.done():
            self._resync_task = asyncio.create_task(self._resync_later(), name="dsp-resync")

    async def _resync_later(self) -> None:
        await asyncio.sleep(RESYNC_DELAY_S)
        log.info("re-reading the DSP after an unanswered write")
        # Failing, it drops the connection: the reconnection re-reads everything.
        with contextlib.suppress(DeviceUnavailableError, PipelineClosedError):
            await self.resync(abort=True)

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
                write.request,
                on_ack=lambda: self.store.apply(self._with_modified(write.changes), origin),
            )
        except CommandTimeoutError:
            self._resync_soon()
            raise
        finally:
            for p, v in mine.items():
                if self._inflight.get(p) is v:
                    del self._inflight[p]
        return write

    async def recall(self, slot: int, origin: str) -> None:
        if not 0 <= slot <= self.profile.preset_count:
            raise ParamError(f"preset slot out of range: {slot}")
        async with self._sequence(f"recall of preset {slot}") as conn:
            reader.expect(await conn.request(cmd.RecallPreset(slot)), rsp.Ack)
            state = await self._read_state(conn, previous=self.store.state)
        log.info("preset %d recalled by %s", slot, origin)
        self.store.replace(state.model_copy(update={"modified": False}))

    async def store_preset(self, slot: int, name: str, origin: str) -> None:
        if not 1 <= slot <= self.profile.preset_count:
            raise ParamError(f"user preset slot must be 1..{self.profile.preset_count}")
        try:
            validate_name(name, PRESET_NAME_LENGTH)
        except ValueError as exc:
            raise ParamError(str(exc)) from exc
        async with self._sequence(f"store to preset {slot}") as conn:
            reader.expect(await conn.request(cmd.SetPresetName(name)), rsp.Ack)
            reader.expect(await conn.request(cmd.StorePreset(slot)), rsp.Ack)
            await reader.activate(conn)
        log.info("preset %d stored as %r by %s", slot, name, origin)
        self.store.apply(
            [
                (f"presets.{slot - 1}.name", name),
                ("active_slot", slot),
                ("preset_name", name),
                ("modified", False),
            ],
            origin,
        )

    async def set_links(self, side: str, groups: list[list[int]], origin: str) -> None:
        """Link channels of one side ("inputs" or "outputs") into ``groups`` of indices.

        Channels in no group are unlinked. A channel joining a group takes the settings of the
        group's first channel (the DSP copies them); the config is re-read afterwards.
        """
        if side not in ("inputs", "outputs"):
            raise ParamError(f"side must be inputs or outputs, not {side!r}")
        channels = self.store.state.inputs if side == "inputs" else self.store.state.outputs
        count = len(channels)
        first = 0 if side == "inputs" else self.profile.input_count
        now = sorted(
            {tuple(sorted([ch.index - first, *ch.linked])) for ch in channels if ch.linked}
        )
        try:
            requests = link_requests(masks_for(normalise(now, count), count), groups, first)
        except LinkError as exc:
            raise ParamError(str(exc)) from exc
        if not requests:
            return
        async with self._sequence(f"{side} link change") as conn:
            for request in requests:
                reader.expect(await conn.request(request), rsp.Ack)
            state = await self._read_state(conn, previous=self.store.state)
        log.info("%s links set to %s by %s", side, normalise(groups, count), origin)
        self.store.replace(state.model_copy(update={"modified": True}))

    async def resync(self, *, abort: bool = False) -> None:
        """Re-read the whole configuration (front-panel changes).

        ``abort``: the state is in doubt, so a failed re-read drops the connection (the
        reconnection re-reads everything); otherwise the known state simply stays."""
        async with self._sequence("configuration read", abort=abort) as conn:
            state = await self._read_state(conn, previous=self.store.state)
        previous = self.store.state
        if previous.active_slot != state.active_slot:
            modified = None  # recalled from the front panel or another client
        elif self._same_config(previous, state):
            modified = previous.modified
        else:
            modified = True  # changed from the front panel or another client
        self.store.replace(state.model_copy(update={"modified": modified}))


__all__ = [
    "DeviceSession",
    "DeviceStatus",
    "DeviceUnavailableError",
    "PipelineClosedError",
    "clamp_meter_rate",
]
