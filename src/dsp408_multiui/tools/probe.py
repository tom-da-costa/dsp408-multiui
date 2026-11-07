"""Talk to a DSP (or the simulator) directly: identity, meters, config dumps, raw frames."""

from __future__ import annotations

import asyncio

from dsp408_multiui.device.reader import (
    DeviceSummary,
    UnexpectedResponseError,
    expect,
    read_config_blob,
    read_info,
)
from dsp408_multiui.device.transport import DspConnection
from dsp408_multiui.protocol import commands as cmd
from dsp408_multiui.protocol import config_map as cm
from dsp408_multiui.protocol import responses as rsp
from dsp408_multiui.protocol.meters import decode_meters
from dsp408_multiui.protocol.profile import MeterFormat, ProtocolProfile

ProbeError = UnexpectedResponseError
_expect = expect


def format_info(summary: DeviceSummary) -> str:
    slot = summary.active_slot
    active = "F00" if slot == 0 else f"U{slot:02d}"
    lines = [
        f"identity   : {summary.identity!r}",
        f"handshake  : {summary.handshake.hex(' ')}",
        f"status     : {summary.status.hex(' ')}",
        f"active     : {active}",
        "presets    :",
    ]
    lines += [f"  U{i + 1:02d} {name}" for i, name in enumerate(summary.preset_names)]
    return "\n".join(lines)


async def read_meters(conn: DspConnection) -> bytes:
    return _expect(await conn.request(cmd.PollMeters()), rsp.MeterFrame).data


def format_meters(data: bytes, profile: ProtocolProfile) -> str:
    """Raw triplets with both interpretations, to settle PROTOCOL Q1 on hardware.

    ``float16 dB`` uses the profile's reference; ``level24`` is the raw 24-bit integer
    (``b2 | b0 << 8 | b1 << 16``), which only means something once calibrated.
    """
    f16_profile = profile.with_overrides({"meters": {"format": MeterFormat.FLOAT16.value}})
    try:
        f16 = decode_meters(data, f16_profile).levels_db
    except ValueError as exc:
        return f"cannot decode ({exc}): {data.hex(' ')}"
    names = [f"In{chr(65 + i)}" for i in range(profile.input_count)] + [
        f"Out{i + 1}" for i in range(profile.output_count)
    ]
    lines = ["chan    raw       float16 dB   level24"]
    for i, name in enumerate(names):
        t = data[3 * i : 3 * i + 3]
        level24 = t[2] | t[0] << 8 | t[1] << 16
        db = "   n/a" if f16[i] is None else f"{f16[i]:6.1f}"
        lines.append(f"{name:<6}  {t.hex(' ')}  {db}      {level24:8d}")
    lines.append(f"tail    {data[3 * len(names) :].hex(' ')}")
    return "\n".join(lines)


def format_diff(before: bytes, after: bytes) -> str:
    changes = cm.diff_blobs(before, after)
    if not changes:
        return "no difference"
    return "\n".join(
        f"{offset:5d}  {old:02x} -> {new:02x}  {name}" for offset, old, new, name in changes
    )


async def send_raw(conn: DspConnection, payload: bytes, timeout: float | None = None) -> str:
    frame = await conn.request_raw(payload, timeout)
    return f"{frame.payload.hex(' ')}  {rsp.decode_response(frame.payload)!r}"


async def watch_meters(conn: DspConnection, interval: float, count: int | None) -> None:
    done = 0
    while count is None or done < count:
        print(format_meters(await read_meters(conn), conn.profile), end="\n\n", flush=True)
        done += 1
        await asyncio.sleep(interval)


__all__ = [
    "DeviceSummary",
    "ProbeError",
    "format_diff",
    "format_info",
    "format_meters",
    "read_config_blob",
    "read_info",
    "read_meters",
    "send_raw",
    "watch_meters",
]
