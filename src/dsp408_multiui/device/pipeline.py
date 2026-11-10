"""Single command queue to the DSP (docs/ARCHITECTURE.md §4).

* One request in flight (the device is strictly request/response).
* Coalescing: a write whose ``coalesce_key`` matches a queued write replaces it in place, so a
  fader moved by several clients costs at most one frame in flight plus one queued per key.
* Writes go before meter polls, but a poll runs as soon as its period has elapsed, so the meter
  rate holds even while writes keep coming.
* ``exclusive()`` pauses the worker so a caller can run a multi-request sequence (preset recall,
  config read) directly on the connection.
* A timeout is retried; after ``max_failures`` consecutive failures, or on a transport error,
  the pipeline closes and reports why (the session then reconnects).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import deque
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field

from dsp408_multiui.device.reader import Requester
from dsp408_multiui.device.transport import TransportError, TransportTimeoutError
from dsp408_multiui.protocol import commands as cmd
from dsp408_multiui.protocol import responses as rsp

log = logging.getLogger(__name__)


class PipelineClosedError(ConnectionError):
    """The pipeline is closed (connection lost or session stopped)."""


class CommandTimeoutError(TimeoutError):
    """The device did not answer a command, even after retrying."""


@dataclass
class _Item:
    request: cmd.Request
    on_ack: Callable[[], object] | None
    futures: list[asyncio.Future[rsp.Response]] = field(default_factory=list)


@dataclass
class PipelineStats:
    sent: int = 0
    coalesced: int = 0
    timeouts: int = 0
    polls: int = 0


class CommandPipeline:
    def __init__(
        self,
        conn: Requester,
        *,
        meter_interval: float,
        on_meters: Callable[[bytes | None], None],
        retries: int = 1,
        max_failures: int = 3,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.conn = conn
        self.meter_interval = meter_interval
        self.on_meters = on_meters
        self.retries = retries
        self.max_failures = max_failures
        self.clock = clock
        self.stats = PipelineStats()
        self._queue: deque[_Item] = deque()
        self._by_key: dict[tuple[int, ...], _Item] = {}
        self._wake = asyncio.Event()
        self._gate = asyncio.Lock()
        self._last_poll = float("-inf")
        self._failures = 0
        self._task: asyncio.Task[None] | None = None
        self._closed: asyncio.Future[BaseException] = asyncio.get_running_loop().create_future()

    # --- lifecycle ------------------------------------------------------------------------------
    def start(self) -> None:
        self._task = asyncio.create_task(self._worker(), name="dsp-pipeline")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self._close(PipelineClosedError("pipeline stopped"))

    @property
    def closed(self) -> bool:
        return self._closed.done()

    async def wait_closed(self) -> BaseException:
        """Wait until the pipeline closes; return the reason."""
        return await asyncio.shield(self._closed)

    @property
    def queue_depth(self) -> int:
        return len(self._queue)

    # --- API ------------------------------------------------------------------------------------
    async def submit(
        self, request: cmd.Request, *, on_ack: Callable[[], object] | None = None
    ) -> rsp.Response:
        """Queue a request and wait for its response.

        ``on_ack`` runs once, when the device acknowledged the request actually sent; for
        coalesced writes that is the newest one.
        """
        if self.closed:
            raise PipelineClosedError("pipeline is closed")
        future: asyncio.Future[rsp.Response] = asyncio.get_running_loop().create_future()
        key = request.coalesce_key
        existing = self._by_key.get(key) if key is not None else None
        if existing is not None:
            existing.request = request
            existing.on_ack = on_ack
            existing.futures.append(future)
            self.stats.coalesced += 1
        else:
            item = _Item(request, on_ack, [future])
            self._queue.append(item)
            if key is not None:
                self._by_key[key] = item
        self._wake.set()
        return await future

    @contextlib.asynccontextmanager
    async def exclusive(self) -> AsyncIterator[Requester]:
        """Pause the worker and give direct access to the connection."""
        if self.closed:
            raise PipelineClosedError("pipeline is closed")
        async with self._gate:
            yield self.conn

    # --- worker -----------------------------------------------------------------------------------
    async def _worker(self) -> None:
        try:
            while True:
                async with self._gate:
                    if self.clock() - self._last_poll >= self.meter_interval:
                        await self._poll()
                        continue
                    if self._queue:
                        item = self._queue.popleft()
                        key = item.request.coalesce_key
                        if key is not None:
                            self._by_key.pop(key, None)
                        await self._execute(item)
                        continue
                self._wake.clear()
                if self._queue:
                    continue
                wait = self._last_poll + self.meter_interval - self.clock()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._wake.wait(), max(0.0, wait))
        except TransportError as exc:
            log.warning("connection lost: %s", exc)
            self._close(exc)
        except _TooManyFailuresError as exc:
            log.warning("%s", exc)
            self._close(exc)

    async def _send(self, request: cmd.Request) -> rsp.Response:
        for attempt in range(self.retries + 1):
            try:
                self.stats.sent += 1
                response = await self.conn.request(request)
            except TransportTimeoutError:
                self.stats.timeouts += 1
                log.debug("timeout on %r (attempt %d)", request, attempt + 1)
                continue
            self._failures = 0
            return response
        self._failures += 1
        if self._failures >= self.max_failures:
            raise _TooManyFailuresError(f"{self._failures} consecutive commands timed out")
        raise CommandTimeoutError(f"no answer to {type(request).__name__}")

    async def _poll(self) -> None:
        self._last_poll = self.clock()
        self.stats.polls += 1
        try:
            reply = await self._send(cmd.PollMeters())
        except CommandTimeoutError:
            self.on_meters(None)
            return
        self.on_meters(reply.data if isinstance(reply, rsp.MeterFrame) else None)

    async def _execute(self, item: _Item) -> None:
        try:
            response = await self._send(item.request)
        except CommandTimeoutError as exc:
            for future in item.futures:
                if not future.done():
                    future.set_exception(exc)
            return
        except BaseException as exc:
            for future in item.futures:
                if not future.done():
                    future.set_exception(PipelineClosedError(str(exc)))
            raise
        if item.on_ack is not None:
            try:
                item.on_ack()
            except Exception:
                log.exception("on_ack callback failed")
        for future in item.futures:
            if not future.done():
                future.set_result(response)

    def _close(self, reason: BaseException) -> None:
        if not self._closed.done():
            self._closed.set_result(reason)
        error = PipelineClosedError(str(reason) or type(reason).__name__)
        while self._queue:
            for future in self._queue.popleft().futures:
                if not future.done():
                    future.set_exception(error)
        self._by_key.clear()


class _TooManyFailuresError(Exception):
    pass
