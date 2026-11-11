"""TCP man-in-the-middle between a client (official editor, backend) and a DSP.

Every frame in both directions is decoded and written to a JSONL frame log. Bytes are forwarded
unchanged, even when they do not decode.
"""

from __future__ import annotations

import asyncio
import logging

from tracks_dsp_controller.aio import cancel_and_wait
from tracks_dsp_controller.framelog import FROM_DEVICE, TO_DEVICE, FrameLog
from tracks_dsp_controller.protocol.framing import FrameDecoder

log = logging.getLogger(__name__)


class ProxyServer:
    def __init__(
        self,
        dsp_host: str,
        dsp_port: int,
        frame_log: FrameLog,
        *,
        listen_host: str = "0.0.0.0",  # the editor runs on another machine
        listen_port: int = 9761,
    ) -> None:
        self.dsp_host = dsp_host
        self.dsp_port = dsp_port
        self.frame_log = frame_log
        self.listen_host = listen_host
        self.listen_port = listen_port
        self._server: asyncio.Server | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def bound_port(self) -> int:
        if self._server is None or not self._server.sockets:
            raise RuntimeError("proxy is not running")
        port: int = self._server.sockets[0].getsockname()[1]
        return port

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._on_connect, self.listen_host, self.listen_port
        )
        log.info(
            "proxy %s:%d -> %s:%d",
            self.listen_host,
            self.bound_port,
            self.dsp_host,
            self.dsp_port,
        )

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
        for task in list(self._tasks):
            await cancel_and_wait(task)
        if self._server is not None:
            await self._server.wait_closed()
            self._server = None

    async def __aenter__(self) -> ProxyServer:
        await self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.stop()

    async def serve_forever(self) -> None:
        if self._server is None:
            await self.start()
        assert self._server is not None
        await self._server.serve_forever()

    async def _on_connect(
        self, client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter
    ) -> None:
        task = asyncio.current_task()
        assert task is not None
        self._tasks.add(task)
        peer = client_writer.get_extra_info("peername")
        log.info("client %s connected", peer)
        try:
            dsp_reader, dsp_writer = await asyncio.open_connection(self.dsp_host, self.dsp_port)
        except OSError as exc:
            log.error("cannot reach the DSP: %s", exc)
            client_writer.close()
            self._tasks.discard(task)
            return
        try:
            await asyncio.gather(
                self._pump(client_reader, dsp_writer, TO_DEVICE),
                self._pump(dsp_reader, client_writer, FROM_DEVICE),
            )
        finally:
            for writer in (client_writer, dsp_writer):
                writer.close()
            self._tasks.discard(task)
            log.info("client %s disconnected", peer)

    async def _pump(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, direction: str
    ) -> None:
        decoder = FrameDecoder()
        try:
            while data := await reader.read(4096):
                writer.write(data)
                await writer.drain()
                for frame in decoder.feed(data):
                    self.frame_log.write(direction, frame)
        except (ConnectionError, OSError):
            pass
        finally:
            writer.close()
