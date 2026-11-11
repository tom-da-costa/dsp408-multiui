"""Minimal asyncio TCP transport to the DSP: one request in flight.

The command pipeline and the device session are built on top of this.

Responses carry no request tag, so an answer that comes after its request timed out could be
taken for the answer to the next request. After a timeout, the next request therefore first
waits for that late answer (up to the current timeout) and drops it; its round trip still
teaches the adaptive timeout (``rtt.py``) how slow the link has become.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time

from tracks_dsp_controller.device.rtt import RttEstimator
from tracks_dsp_controller.protocol import commands as cmd
from tracks_dsp_controller.protocol import responses as rsp
from tracks_dsp_controller.protocol.framing import Frame, FrameDecoder, encode_frame
from tracks_dsp_controller.protocol.profile import ProtocolProfile

log = logging.getLogger(__name__)


class TransportError(ConnectionError):
    """The connection failed or was closed."""


class TransportTimeoutError(TimeoutError):
    """No response arrived in time."""


class DspConnection:
    def __init__(
        self,
        host: str,
        port: int,
        profile: ProtocolProfile,
        *,
        connect_timeout: float = 5.0,
    ) -> None:
        self.host = host
        self.port = port
        self.profile = profile
        self.connect_timeout = connect_timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._decoder = FrameDecoder()
        self._pending: list[Frame] = []
        self._lock = asyncio.Lock()
        self.rtt = RttEstimator(profile.command_timeout_s, profile.command_timeout_max_s)
        # Answers still owed to timed-out requests: (sent at, waited for until, payload).
        self._owed: list[tuple[float, float, bytes]] = []
        self.late_answers = 0
        self.last_received = time.monotonic()  # last frame from the device (link liveness)

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), self.connect_timeout
            )
        except (OSError, TimeoutError) as exc:
            raise TransportError(f"cannot connect to {self.host}:{self.port}: {exc}") from exc
        self._decoder.reset()
        self._pending.clear()
        self._owed.clear()
        self.last_received = time.monotonic()
        log.info("connected to %s:%d", self.host, self.port)

    async def close(self) -> None:
        writer, self._writer, self._reader = self._writer, None, None
        if writer is not None:
            writer.close()
            with contextlib.suppress(ConnectionError, OSError):
                await writer.wait_closed()

    async def __aenter__(self) -> DspConnection:
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    @property
    def timeout(self) -> float:
        """Current timeout of an ordinary command (adapts to the link)."""
        return self.rtt.timeout

    async def request_raw(
        self,
        payload: bytes,
        timeout: float | None = None,
        expect: int | None = None,
        *,
        slow: bool = False,
    ) -> Frame:
        """Send ``payload`` and return the next device frame (with opcode ``expect`` if given).

        ``timeout`` None: the adaptive timeout, plus the profile's slow-command time for a
        ``slow`` request (preset recall and store, whose answer takes seconds).
        Frames with another opcode are late answers to an earlier, timed-out request: skip them.
        """
        adaptive = timeout is None
        if timeout is None:
            timeout = self.rtt.timeout
            if slow:
                timeout += self.profile.slow_command_timeout_s
        async with self._lock:
            if self._writer is None or self._reader is None:
                raise TransportError("not connected")
            # The same request again (a retry): the late answer to the first one answers it as
            # well. Another request: the answers still owed must not be taken for its own.
            retry = bool(self._owed) and all(owed == payload for _, _, owed in self._owed)
            sent = time.monotonic()
            try:
                if not retry:
                    await self._drain_late()
                frame = encode_frame(payload, dst=self.profile.host_dst)
                sent = time.monotonic()
                self._writer.write(frame)
                await self._writer.drain()
                reply = await asyncio.wait_for(self._next_device_frame(expect), timeout)
            except TimeoutError as exc:
                # Its answer is waited for as long again (at most the ceiling), then given up.
                wait = min(timeout, self.profile.command_timeout_max_s)
                self._owed.append((sent, sent + 2 * wait, payload))
                if adaptive:  # a short timeout chosen by the caller says nothing of the link
                    self.rtt.timed_out()
                raise TransportTimeoutError(
                    f"no response to {payload[:1].hex()} within {timeout:.2f}s"
                ) from exc
            except (ConnectionError, OSError) as exc:
                await self.close()
                raise TransportError(str(exc)) from exc
            if retry:
                # Which send this answers is unknown (no round-trip sample, as in TCP): take it
                # for the oldest one. The answer to the latest send, if it comes, comes about as
                # long after this one as the sends were apart.
                first, _, _ = self._owed.pop(0)
                now = time.monotonic()
                extra = now + 1.25 * (sent - first) + 0.05
                self._owed = [(t, max(d, extra), p) for t, d, p in self._owed]
                self._owed.append((sent, extra, payload))
            elif not slow:  # a slow command's time is the device's work, not the link's
                self.rtt.sample(time.monotonic() - sent)
            return reply

    async def _drain_late(self) -> None:
        """Wait for (and drop) the answers still owed to timed-out requests.

        One request is in flight at a time, so each timed-out request owes at most one frame.
        Past its deadline an answer is given up as lost.
        """
        assert self._reader is not None
        if self._owed:
            deadline = max(until for _, until, _ in self._owed)
            while self._owed:
                while self._pending and self._owed:
                    frame = self._pending.pop(0)
                    if frame.from_device:
                        self._owed.pop(0)
                        self.late_answers += 1
                        log.debug("dropping a late answer: %s", frame.payload[:1].hex())
                remaining = deadline - time.monotonic()
                if not self._owed or remaining <= 0:
                    break
                try:
                    data = await asyncio.wait_for(self._reader.read(4096), remaining)
                except TimeoutError:
                    break
                self._received(data)
            self._owed.clear()
        # Anything else left over is stale too.
        self._pending.clear()

    def _received(self, data: bytes) -> None:
        if not data:
            raise TransportError("connection closed by the device")
        frames = self._decoder.feed(data)
        if any(frame.from_device for frame in frames):
            self.last_received = time.monotonic()
        self._pending.extend(frames)

    async def request(self, request: cmd.Request, timeout: float | None = None) -> rsp.Response:
        frame = await self.request_raw(
            request.encode(self.profile), timeout, request.RESPONSE, slow=request.SLOW
        )
        return rsp.decode_response(frame.payload)

    async def _next_device_frame(self, expect: int | None) -> Frame:
        assert self._reader is not None
        while True:
            while self._pending:
                frame = self._pending.pop(0)
                if not frame.from_device:
                    continue
                if expect is None or frame.opcode == expect:
                    return frame
                log.debug("skipping unexpected frame %s", frame.payload.hex(" "))
            self._received(await self._reader.read(4096))
