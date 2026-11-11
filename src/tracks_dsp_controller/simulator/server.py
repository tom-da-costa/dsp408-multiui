"""asyncio TCP server exposing a ``SimulatedDevice`` like a real DSP 408 on port 9761."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from enum import StrEnum

from tracks_dsp_controller.aio import cancel_and_wait
from tracks_dsp_controller.framelog import FROM_DEVICE, TO_DEVICE, FrameLog
from tracks_dsp_controller.protocol.commands import Opcode
from tracks_dsp_controller.protocol.framing import HOST, Frame, FrameDecoder
from tracks_dsp_controller.simulator.device import Link, SimulatedDevice
from tracks_dsp_controller.simulator.faults import Faults

log = logging.getLogger(__name__)

DEFAULT_PORT = 9761


class SecondClient(StrEnum):
    """What happens when a client connects while another one is connected."""

    # The DSP 408 (HW, PROTOCOL.md Q10): the new connection waits, unanswered, until the earlier
    # one leaves, then is served; the first client is not disturbed. (On the DSP the TCP
    # connection itself only completes then; here it completes at once but nothing is answered,
    # and what the client sends meanwhile is dropped.)
    QUEUE = "queue"
    ACCEPT = "accept"  # both are served (requests are serialised)
    REFUSE = "refuse"  # the new connection is closed immediately
    KICK = "kick"  # the old connection is closed, the new one is served


class SimulatorServer:
    def __init__(
        self,
        device: SimulatedDevice,
        *,
        host: str = "127.0.0.1",
        port: int = DEFAULT_PORT,
        faults: Faults | None = None,
        second_client: SecondClient = SecondClient.QUEUE,
        frame_log: FrameLog | None = None,
        device_id: int | None = None,
    ) -> None:
        """``device_id``: the ID number "set on the front panel" (the device address); None =
        the profile's (1 for a 408)."""
        self.device = device
        self.device_id = device_id if device_id is not None else device.profile.host_dst
        self.host = host
        self.port = port
        self.faults = faults or Faults()
        self.second_client = second_client
        self.frame_log = frame_log
        self._server: asyncio.Server | None = None
        self._clients: dict[asyncio.StreamWriter, asyncio.Task[None]] = {}
        self._device_lock = asyncio.Lock()  # the device handles one request at a time
        self._left = asyncio.Condition()  # notified when a client leaves (QUEUE mode)

    @property
    def bound_port(self) -> int:
        """Actual port (useful with ``port=0``)."""
        if self._server is None or not self._server.sockets:
            raise RuntimeError("server is not running")
        port: int = self._server.sockets[0].getsockname()[1]
        return port

    @property
    def client_count(self) -> int:
        return len(self._clients)

    @property
    def running(self) -> bool:
        return self._server is not None

    def peers(self) -> list[str]:
        """Addresses of the connected clients."""
        return [_peer(writer) for writer in self._clients]

    def kick(self) -> int:
        """Close every client connection (the clients see the DSP drop them)."""
        writers = list(self._clients)
        for writer in writers:
            writer.close()
        return len(writers)

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._on_connect, self.host, self.port)
        log.info("simulator listening on %s:%d", self.host, self.bound_port)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
        for writer in list(self._clients):
            writer.close()
        tasks = list(self._clients.values())
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError, ConnectionError):
                await task
        if self._server is not None:
            await self._server.wait_closed()
            self._server = None

    async def __aenter__(self) -> SimulatorServer:
        await self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.stop()

    async def serve_forever(self) -> None:
        if self._server is None:
            await self.start()
        assert self._server is not None
        await self._server.serve_forever()

    def addressed(self, address: int) -> bool:
        """Whether a frame sent to ``address`` is for this device: its ID; a captured DSP 206
        also answered frames sent to 0x01 (PROTOCOL.md §10)."""
        return address == self.device_id or (address == 0x01 and self.device.model.key == "206")

    # --- connections ----------------------------------------------------------------------------
    async def _on_connect(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        if self._clients and self.second_client is SecondClient.REFUSE:
            log.info("refusing second client %s", peer)
            writer.close()
            return
        if self._clients and self.second_client is SecondClient.QUEUE:
            log.info("client %s waits: another client is connected", peer)
            if not await self._wait_turn(reader, writer):
                return
        if self._clients and self.second_client is SecondClient.KICK:
            for old in list(self._clients):
                log.info("kicking client %s", old.get_extra_info("peername"))
                old.close()
        log.info("client connected: %s", peer)
        task = asyncio.current_task()
        assert task is not None
        self._clients[writer] = task
        try:
            await self._serve(reader, writer)
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            self._clients.pop(writer, None)
            writer.close()
            async with self._left:
                self._left.notify_all()
            with contextlib.suppress(ConnectionError):
                await writer.wait_closed()
            log.info("client disconnected: %s", peer)

    async def _wait_turn(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> bool:
        """QUEUE mode: hold the connection until no other client is connected.

        What the client sends meanwhile is dropped. Returns False if it left first."""

        async def discard() -> None:
            while await reader.read(4096):
                pass

        draining = asyncio.create_task(discard())
        try:
            async with self._left:
                while self._clients and self.second_client is SecondClient.QUEUE:
                    left = asyncio.create_task(self._left.wait())
                    await asyncio.wait({left, draining}, return_when=asyncio.FIRST_COMPLETED)
                    if draining.done():
                        left.cancel()
                        writer.close()
                        return False
        finally:
            await cancel_and_wait(draining)  # before _serve() reads the same stream
        return True

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        decoder = FrameDecoder()
        link = Link()  # the init sequence is needed again on each connection
        handled = 0
        while not writer.is_closing():
            data = await reader.read(4096)
            if not data:
                return
            for frame in decoder.feed(data):
                if self.frame_log:
                    self.frame_log.write(TO_DEVICE, frame)
                if frame.from_device:
                    continue  # ignore echoes of device frames
                if not self.addressed(frame.dst):
                    continue  # for another device ID: the DSP does not answer (HW)
                if not await self._handle(frame, writer, link):
                    return
                handled += 1
                limit = self.faults.disconnect_after
                if limit is not None and handled >= limit:
                    log.info("fault injection: disconnecting after %d requests", handled)
                    return

    async def _handle(self, frame: Frame, writer: asyncio.StreamWriter, link: Link) -> bool:
        """Process one request. Returns False when the connection must close."""
        async with self._device_lock:
            if frame.opcode == Opcode.METERS and self.faults.roll(self.faults.nan_meter_rate):
                self.device.meters.nan_next = True
            reply = self.device.handle(frame.payload, link)
            delay = reply.delay_s + self.faults.extra_latency_s
            if delay:
                await asyncio.sleep(delay)
        if reply.crash:
            return False
        if reply.response is None or self.faults.roll(self.faults.drop_rate):
            return True
        # It answers from the address the request was sent to (its ID; 0x01 too on a 206).
        out = Frame(frame.dst, HOST, reply.response.encode())
        wire = bytearray(out.encode())
        if self.faults.roll(self.faults.corrupt_rate):
            wire[-1] ^= 0xFF
        if self.frame_log:
            self.frame_log.write(FROM_DEVICE, out)
        writer.write(bytes(wire))
        await writer.drain()
        return True


def _peer(writer: asyncio.StreamWriter) -> str:
    peer = writer.get_extra_info("peername")
    return f"{peer[0]}:{peer[1]}" if isinstance(peer, tuple) else str(peer)
