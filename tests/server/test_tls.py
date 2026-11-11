"""HTTPS: self-signed certificate, and TLS + the http → https redirect on one port."""

import asyncio
import ipaddress
import socket
import ssl
from pathlib import Path

import pytest

from tracks_dsp_controller.server import tls
from tracks_dsp_controller.server.listener import DualListener, redirect_response

NAMES: list[tls.HostName] = ["localhost", ipaddress.ip_address("127.0.0.1")]


def test_self_signed_is_generated_then_reused(tmp_path: Path) -> None:
    files = tls.self_signed(tmp_path, NAMES)
    assert files.cert.exists()
    assert files.key.stat().st_mode & 0o077 == 0  # the key is private
    first = files.cert.read_bytes()
    assert tls.self_signed(tmp_path, NAMES).cert.read_bytes() == first  # kept across restarts
    # a new address of this machine: renewed so that it is covered
    renewed = tls.self_signed(tmp_path, [*NAMES, ipaddress.ip_address("192.0.2.7")])
    assert renewed.cert.read_bytes() != first
    assert isinstance(tls.server_context(renewed), ssl.SSLContext)


def test_unusable_files_are_reported(tmp_path: Path) -> None:
    (tmp_path / "cert.pem").write_text("not a certificate")
    with pytest.raises(tls.TlsError, match="cannot use"):
        tls.server_context(tls.TlsFiles(tmp_path / "cert.pem", tmp_path / "missing.pem"))


def test_parse_names() -> None:
    assert tls.parse_names(" 192.168.1.10, dsp.local ,,") == [
        ipaddress.ip_address("192.168.1.10"),
        "dsp.local",
    ]
    with pytest.raises(tls.TlsError, match="not a host name"):
        tls.parse_names("bad name")


def test_local_names_include_localhost() -> None:
    names = [str(n) for n in tls.local_names()]
    assert "localhost" in names
    assert "127.0.0.1" in names
    assert "0.0.0.0" not in names


def test_redirect_response() -> None:
    head = b"GET /presets?x=1 HTTP/1.1\r\nHost: dsp.local:8080\r\nAccept: */*\r\n\r\n"
    response = redirect_response(head, "10.0.0.5:8080")
    assert response.startswith(b"HTTP/1.1 308 Permanent Redirect\r\n")
    assert b"Location: https://dsp.local:8080/presets?x=1\r\n" in response
    # no usable Host header: the address the connection came in on
    assert b"Location: https://10.0.0.5:8080/\r\n" in redirect_response(
        b"GET / HTTP/1.0\r\n\r\n", "10.0.0.5:8080"
    )
    # a forged Host header is not copied
    forged = b"GET / HTTP/1.1\r\nHost: evil\r\nX: y\r\nHost: a b\r\n\r\n"
    assert b"Location: https://evil/\r\n" in redirect_response(forged, "h:1")
    assert b"Location: https://h:1/\r\n" in redirect_response(
        b"GET / HTTP/1.1\r\nHost: a\x0bb\r\n\r\n", "h:1"
    )
    assert b"https://[::1]:8080/" in redirect_response(
        b"GET / HTTP/1.1\r\nHost: [::1]:8080\r\n\r\n", "h:1"
    )


class Echo(asyncio.Protocol):
    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        assert isinstance(transport, asyncio.Transport)
        self.transport = transport
        self.tls = transport.get_extra_info("sslcontext") is not None

    def data_received(self, data: bytes) -> None:
        self.transport.write(b"tls:" + data if self.tls else b"plain:" + data)


async def test_one_port_serves_tls_and_redirects_plain_http(tmp_path: Path) -> None:
    context = tls.server_context(tls.self_signed(tmp_path, NAMES))
    sock = socket.create_server(("127.0.0.1", 0))
    sock.setblocking(False)
    port = sock.getsockname()[1]
    listener = DualListener(sock, Echo, context)
    listener.start()
    try:
        # TLS: the app's protocol, over TLS
        client = ssl.create_default_context()
        client.check_hostname = False
        client.verify_mode = ssl.CERT_NONE
        reader, writer = await asyncio.open_connection("127.0.0.1", port, ssl=client)
        writer.write(b"hello")
        assert await asyncio.wait_for(reader.read(100), 5) == b"tls:hello"
        writer.close()
        # plain HTTP: redirected
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"GET /x HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n\r\n" % port)
        response = await asyncio.wait_for(reader.read(), 5)
        assert response.startswith(b"HTTP/1.1 308")
        assert b"Location: https://127.0.0.1:%d/x\r\n" % port in response
        writer.close()
        # a client that connects and leaves at once does not disturb the listener
        _, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.close()
        reader, writer = await asyncio.open_connection("127.0.0.1", port, ssl=client)
        writer.write(b"again")
        assert await asyncio.wait_for(reader.read(100), 5) == b"tls:again"
        writer.close()
    finally:
        listener.close()
        await listener.wait_closed()
