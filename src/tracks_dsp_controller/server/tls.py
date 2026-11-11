"""HTTPS: a certificate given by the user, or a self-signed one generated here, offline.

The self-signed certificate and its key are kept in a directory (``--tls-dir``), so that a
browser's exception for it survives restarts. It is regenerated when it expires or when this
machine's names and addresses are no longer all in it.
"""

from __future__ import annotations

import datetime as dt
import ipaddress
import logging
import os
import socket
import ssl
import sys
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

CERT_NAME = "self-signed-cert.pem"
KEY_NAME = "self-signed-key.pem"
VALIDITY_DAYS = 3650
RENEW_BEFORE_DAYS = 30

type HostName = str | ipaddress.IPv4Address | ipaddress.IPv6Address


class TlsError(ValueError):
    """The certificate or key cannot be used."""


@dataclass(frozen=True, slots=True)
class TlsFiles:
    cert: Path
    key: Path


def default_dir() -> Path:
    """Where the self-signed certificate is kept: the user's data directory."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "tracks-dsp-controller" / "tls"


def server_context(files: TlsFiles) -> ssl.SSLContext:
    """TLS context of the server (TLS 1.2 or later)."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        context.load_cert_chain(files.cert, files.key)
    except (OSError, ssl.SSLError) as exc:
        raise TlsError(f"cannot use {files.cert} / {files.key}: {exc}") from exc
    return context


def local_names(listen_host: str = "0.0.0.0") -> list[HostName]:
    """Names and addresses this machine is likely reached by (no network request)."""
    names: list[HostName] = ["localhost"]
    hostname = socket.gethostname()
    if hostname:
        names += [hostname, f"{hostname}.local"] if "." not in hostname else [hostname]
    addresses: set[str] = {"127.0.0.1", "::1"}
    if listen_host not in ("", "0.0.0.0", "::"):
        addresses.add(listen_host)
    try:
        for info in socket.getaddrinfo(hostname, None):
            addresses.add(str(info[4][0]))
    except OSError:
        pass
    # The address of the default route: connecting a UDP socket sends nothing.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("10.255.255.255", 1))
            addresses.add(probe.getsockname()[0])
        except OSError:
            pass
    for address in sorted(addresses):
        try:
            ip = ipaddress.ip_address(address.split("%")[0])
        except ValueError:
            names.append(address)
            continue
        if not ip.is_unspecified:
            names.append(ip)
    return names


def parse_names(text: str) -> list[HostName]:
    """``--tls-names``: comma-separated host names and IP addresses."""
    names: list[HostName] = []
    for item in (part.strip() for part in text.split(",")):
        if not item:
            continue
        try:
            names.append(ipaddress.ip_address(item))
        except ValueError:
            if not all(ch.isalnum() or ch in ".-*" for ch in item):
                raise TlsError(f"not a host name or IP address: {item!r}") from None
            names.append(item)
    return names


def self_signed(directory: Path, names: list[HostName]) -> TlsFiles:
    """The self-signed certificate in ``directory``, generated or renewed when needed."""
    files = TlsFiles(directory / CERT_NAME, directory / KEY_NAME)
    reason = _renewal_reason(files, names)
    if reason is None:
        log.info("using the self-signed certificate %s", files.cert)
        return files
    log.info("generating a self-signed certificate in %s (%s)", directory, reason)
    _generate(files, names)
    return files


def _renewal_reason(files: TlsFiles, names: list[HostName]) -> str | None:
    from cryptography import x509

    if not files.cert.exists() or not files.key.exists():
        return "none yet"
    try:
        cert = x509.load_pem_x509_certificate(files.cert.read_bytes())
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except (ValueError, x509.ExtensionNotFound) as exc:
        return f"unreadable: {exc}"
    remaining = cert.not_valid_after_utc - dt.datetime.now(dt.UTC)
    if remaining < dt.timedelta(days=RENEW_BEFORE_DAYS):
        return "expires soon"
    covered = {str(n) for n in san.get_values_for_type(x509.DNSName)}
    covered |= {str(ip) for ip in san.get_values_for_type(x509.IPAddress)}
    missing = [str(n) for n in names if str(n) not in covered]
    return f"new name or address: {', '.join(missing)}" if missing else None


def _generate(files: TlsFiles, names: list[HostName]) -> None:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "tracks-dsp-controller")])
    now = dt.datetime.now(dt.UTC)
    alt: list[x509.GeneralName] = [
        x509.DNSName(n) if isinstance(n, str) else x509.IPAddress(n) for n in names
    ]
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=VALIDITY_DAYS))
        .add_extension(x509.SubjectAlternativeName(alt), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(key, hashes.SHA256())
    )
    files.cert.parent.mkdir(parents=True, exist_ok=True)
    key_bytes = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    # The key is readable by its owner only.
    fd = os.open(files.key, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(key_bytes)
    files.cert.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
