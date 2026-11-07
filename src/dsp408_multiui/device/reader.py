"""Read sequences shared by the device session and the probe tool."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Protocol

from dsp408_multiui.device.transport import TransportTimeoutError
from dsp408_multiui.protocol import commands as cmd
from dsp408_multiui.protocol import config_map as cm
from dsp408_multiui.protocol import responses as rsp
from dsp408_multiui.protocol.profile import ProtocolProfile

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
