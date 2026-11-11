"""HTTPS and HTTP on one port: TLS for the app, a redirect to https:// for plain HTTP.

uvicorn serves either HTTP or HTTPS on a socket. To answer someone who types the address
without ``https://``, each connection's first byte is looked at (without reading it): ``0x16``
opens a TLS handshake and the connection goes to uvicorn with TLS; anything else is plain HTTP
and gets a ``308`` redirect to the same address in https.

Only public asyncio calls are used (``sock_accept``, ``connect_accepted_socket``), so it works
with every event loop, Windows' included; the first byte is peeked in a worker thread.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import socket
import ssl
import sys
from collections.abc import Callable

import uvicorn

log = logging.getLogger(__name__)

TLS_HANDSHAKE = 0x16  # first byte of a TLS record carrying a ClientHello
PEEK_TIMEOUT_S = 10.0
REQUEST_HEAD_MAX = 8192
_HOST_RE = re.compile(r"^[A-Za-z0-9.\-]+(:\d{1,5})?$|^\[[0-9A-Fa-f:.]+\](:\d{1,5})?$")


class RedirectProtocol(asyncio.Protocol):
    """Answer one plain HTTP request with a redirect to the same URL in https."""

    def __init__(self, fallback_host: str) -> None:
        self.fallback_host = fallback_host
        self.transport: asyncio.Transport | None = None
        self.buffer = b""
        self.timer: asyncio.TimerHandle | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        assert isinstance(transport, asyncio.Transport)
        self.transport = transport
        self.timer = asyncio.get_running_loop().call_later(PEEK_TIMEOUT_S, transport.close)

    def connection_lost(self, exc: Exception | None) -> None:
        if self.timer is not None:
            self.timer.cancel()

    def data_received(self, data: bytes) -> None:
        assert self.transport is not None
        self.buffer += data
        if b"\r\n\r\n" not in self.buffer and len(self.buffer) < REQUEST_HEAD_MAX:
            return
        self.transport.write(redirect_response(self.buffer, self.fallback_host))
        self.transport.close()


def redirect_response(head: bytes, fallback_host: str) -> bytes:
    """The ``308`` response for the request ``head`` (its first line and headers)."""
    lines = head.split(b"\r\n\r\n", 1)[0].decode("latin-1").split("\r\n")
    parts = lines[0].split(" ")
    target = parts[1] if len(parts) == 3 and parts[1].startswith("/") else "/"
    host = fallback_host
    for line in lines[1:]:
        name, _, value = line.partition(":")
        if name.strip().lower() == "host" and _HOST_RE.match(value.strip()):
            host = value.strip()
    location = f"https://{host}{target}"
    if any(ch in location for ch in "\r\n"):
        location = f"https://{fallback_host}/"
    body = f"Use HTTPS: {location}\n".encode()
    return (
        "HTTP/1.1 308 Permanent Redirect\r\n"
        f"Location: {location}\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n\r\n"
    ).encode() + body


def _peek(conn: socket.socket) -> bytes:
    conn.settimeout(PEEK_TIMEOUT_S)
    try:
        return conn.recv(1, socket.MSG_PEEK)
    finally:
        conn.setblocking(False)


class DualListener:
    """Accepts on one socket and dispatches each connection to TLS or to the redirect.

    Has what uvicorn needs of an ``asyncio.Server`` at shutdown: ``close()``,
    ``wait_closed()`` and ``sockets``."""

    def __init__(
        self,
        sock: socket.socket,
        app_protocol: Callable[[], asyncio.Protocol],
        context: ssl.SSLContext,
    ) -> None:
        self.sock = sock
        self.sockets = [sock]
        self.app_protocol = app_protocol
        self.context = context
        self._task: asyncio.Task[None] | None = None
        self._pending: set[asyncio.Task[None]] = set()

    def start(self) -> None:
        self._task = asyncio.create_task(self._accept_loop(), name="https-accept")

    async def _accept_loop(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            try:
                conn, _ = await loop.sock_accept(self.sock)
            except OSError as exc:
                if self.sock.fileno() == -1:
                    return  # closed
                log.warning("accept failed: %s", exc)
                await asyncio.sleep(0.1)
                continue
            task = asyncio.create_task(self._dispatch(conn))
            self._pending.add(task)
            task.add_done_callback(self._pending.discard)

    async def _dispatch(self, conn: socket.socket) -> None:
        loop = asyncio.get_running_loop()
        try:
            first = await asyncio.to_thread(_peek, conn)
            if not first:
                conn.close()
                return
            if first[0] == TLS_HANDSHAKE:
                await loop.connect_accepted_socket(
                    self.app_protocol, conn, ssl=self.context, ssl_handshake_timeout=PEEK_TIMEOUT_S
                )
            else:
                host, port = conn.getsockname()[:2]
                fallback = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
                await loop.connect_accepted_socket(lambda: RedirectProtocol(fallback), conn)
        except (OSError, ssl.SSLError, TimeoutError) as exc:
            log.debug("connection dropped before it started: %s", exc)
            with contextlib.suppress(OSError):
                conn.close()

    def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
        with contextlib.suppress(OSError):
            self.sock.close()

    async def wait_closed(self) -> None:
        if self._task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        for task in list(self._pending):
            task.cancel()


class HttpsServer(uvicorn.Server):
    """uvicorn with HTTPS and the http → https redirect on the same port."""

    def __init__(self, config: uvicorn.Config, context: ssl.SSLContext) -> None:
        super().__init__(config)
        self.context = context

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await self.lifespan.startup()
        if self.lifespan.should_exit:
            sys.exit(3)
        config = self.config
        loop = asyncio.get_running_loop()

        def create_protocol() -> asyncio.Protocol:
            protocol: asyncio.Protocol = config.http_protocol_class(  # type: ignore[call-arg]
                config=config,
                server_state=self.server_state,
                app_state=self.lifespan.state,
                _loop=loop,
            )
            return protocol

        try:
            family = socket.AF_INET6 if ":" in config.host else socket.AF_INET
            sock = socket.create_server((config.host, config.port), family=family)
        except OSError as exc:
            log.error("%s", exc)
            await self.lifespan.shutdown()
            sys.exit(3)
        sock.setblocking(False)
        listener = DualListener(sock, create_protocol, self.context)
        listener.start()
        self.servers = [listener]  # type: ignore[list-item]
        port = sock.getsockname()[1]
        log.info("Uvicorn running on https://%s:%d (plain http is redirected)", config.host, port)
        self.started = True
