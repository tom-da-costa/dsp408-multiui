"""Minimal asyncio TCP transport to the DSP: one request in flight.

The command pipeline and the device session are built on top of this.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

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

    async def request_raw(
        self, payload: bytes, timeout: float | None = None, expect: int | None = None
    ) -> Frame:
        """Send ``payload`` and return the next device frame (with opcode ``expect`` if given).

        Frames with another opcode are late answers to an earlier, timed-out request: skip them.
        """
        if timeout is None:
            timeout = self.profile.command_timeout_s
        async with self._lock:
            if self._writer is None or self._reader is None:
                raise TransportError("not connected")
            # Responses are not tagged: drop anything left over from a timed-out request.
            self._pending.clear()
            frame = encode_frame(payload, dst=self.profile.host_dst)
            try:
                self._writer.write(frame)
                await self._writer.drain()
                return await asyncio.wait_for(self._next_device_frame(expect), timeout)
            except TimeoutError as exc:
                raise TransportTimeoutError(
                    f"no response to {payload[:1].hex()} within {timeout:.2f}s"
                ) from exc
            except (ConnectionError, OSError) as exc:
                await self.close()
                raise TransportError(str(exc)) from exc

    async def request(self, request: cmd.Request, timeout: float | None = None) -> rsp.Response:
        if timeout is None and request.SLOW:
            timeout = self.profile.slow_command_timeout_s
        frame = await self.request_raw(request.encode(self.profile), timeout, request.RESPONSE)
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
            data = await self._reader.read(4096)
            if not data:
                await self.close()
                raise TransportError("connection closed by the device")
            self._pending.extend(self._decoder.feed(data))
