"""Read sequences shared by the device session and the probe tool."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import Protocol

from tracks_dsp_controller.device.transport import TransportTimeoutError
from tracks_dsp_controller.protocol import commands as cmd
from tracks_dsp_controller.protocol import config_map as cm
from tracks_dsp_controller.protocol import responses as rsp
from tracks_dsp_controller.protocol.profile import ProtocolProfile

ACTIVATE_GRACE_S = 0.05  # the 4x4 Mini needs a short pause after 0x12 before polling


class Requester(Protocol):
    profile: ProtocolProfile

    async def request(self, request: cmd.Request, timeout: float | None = None) -> rsp.Response: ...


class UnexpectedResponseError(RuntimeError):
    """The device answered something unexpected."""


READ_RETRIES = 2  # reads are idempotent: retry them on timeout


async def ask(conn: Requester, request: cmd.Request, retries: int = READ_RETRIES) -> rsp.Response:
    """Send an idempotent request, retrying on timeout."""
    for attempt in range(retries + 1):
        try:
            return await conn.request(request)
        except TransportTimeoutError:
            if attempt == retries:
                raise
    raise AssertionError("unreachable")  # pragma: no cover


def expect[T: rsp.Response](reply: rsp.Response, kind: type[T]) -> T:
    if not isinstance(reply, kind):
        raise UnexpectedResponseError(f"expected {kind.__name__}, got {reply!r}")
    return reply


@dataclass
class DeviceSummary:
    identity: str
    handshake: bytes
    status: bytes
    active_slot: int
    preset_names: list[str] = field(default_factory=list)


async def read_preset_names(conn: Requester) -> list[str]:
    return [
        expect(await ask(conn, cmd.GetPresetName(i)), rsp.PresetName).name
        for i in range(conn.profile.preset_count)
    ]


async def read_active_slot(conn: Requester) -> int:
    return expect(await ask(conn, cmd.GetActivePreset()), rsp.ActivePreset).slot


# The device address is the "ID number" set on the DSP's front panel (1–250, factory 1; HW,
# PROTOCOL.md §2): the DSP answers only frames sent to it. These are tried first, then every ID.
KNOWN_ADDRESSES = (0x01, 0x02)
DEVICE_IDS = range(1, 251)


class AddressScanner(Protocol):
    async def find_device(self, addresses: Iterable[int]) -> int | None: ...


async def _identity_at(conn: Requester, address: int) -> str:
    conn.profile = replace(conn.profile, host_dst=address)
    expect(await ask(conn, cmd.Handshake(), retries=0), rsp.HandshakeReply)
    return expect(await ask(conn, cmd.GetDeviceInfo()), rsp.DeviceInfo).text


async def read_identity(conn: Requester, *, scan: bool = True) -> str:
    """Handshake and 0x13 identity on the profile's address (the last ID found, ``--device-id``,
    or the model's default). With ``scan``, then on the other known addresses, then on every
    device ID when the connection can search for it.

    Leaves ``conn.profile`` on the address that answered."""
    base = conn.profile
    tried = list(dict.fromkeys((base.host_dst, *(KNOWN_ADDRESSES if scan else ()))))
    for address in tried:
        try:
            return await _identity_at(conn, address)
        except TransportTimeoutError:
            conn.profile = base
    if scan and hasattr(conn, "find_device"):
        scanner: AddressScanner = conn  # type: ignore[assignment]
        found = await scanner.find_device(a for a in DEVICE_IDS if a not in tried)
        if found is not None:
            try:
                return await _identity_at(conn, found)
            except TransportTimeoutError:
                conn.profile = base
    if not scan:
        raise TransportTimeoutError(
            f"no answer from device ID {base.host_dst}: check the ID number set on the DSP "
            "(or leave --device-id out to search for it)"
        )
    raise TransportTimeoutError("no DSP answered, on any device ID (1–250)")


async def read_info(conn: Requester) -> DeviceSummary:
    """The editor's init sequence up to the preset names."""
    handshake = expect(await ask(conn, cmd.Handshake()), rsp.HandshakeReply)
    info = expect(await ask(conn, cmd.GetDeviceInfo()), rsp.DeviceInfo)
    status = expect(await ask(conn, cmd.GetStatus()), rsp.Status)
    expect(await ask(conn, cmd.GetPresetHeader()), rsp.PresetHeader)
    active = await read_active_slot(conn)
    names = await read_preset_names(conn)
    return DeviceSummary(info.text, handshake.data, status.data, active, names)


async def read_config_blob(conn: Requester) -> bytes:
    pages = {}
    for page in range(conn.profile.page_count):
        reply = expect(await ask(conn, cmd.ReadConfigPage(page)), rsp.ConfigPage)
        if reply.page != page:
            raise UnexpectedResponseError(f"asked for page {page}, got page {reply.page}")
        pages[page] = reply.data
    return cm.join_pages(pages, conn.profile)


async def activate(conn: Requester) -> None:
    expect(await ask(conn, cmd.Activate()), rsp.Ack)
    await asyncio.sleep(ACTIVATE_GRACE_S)
