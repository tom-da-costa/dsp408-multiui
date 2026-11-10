"""Talk to a DSP (or the simulator) directly: identity, meters, config dumps, raw frames."""

from __future__ import annotations

import asyncio

from tracks_dsp_controller.device.reader import (
    DeviceSummary,
    UnexpectedResponseError,
    expect,
    read_config_blob,
    read_identity,
    read_info,
)
from tracks_dsp_controller.device.transport import DspConnection
from tracks_dsp_controller.protocol import commands as cmd
from tracks_dsp_controller.protocol import config_map as cm
from tracks_dsp_controller.protocol import responses as rsp
from tracks_dsp_controller.protocol.meters import decode_meters
from tracks_dsp_controller.protocol.profile import ProtocolProfile

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
    """Raw triplets with the profile's decoding (float32 dBFS on a 408) and the tail flags."""
    try:
        reading = decode_meters(data, profile)
    except ValueError as exc:
        return f"cannot decode ({exc}): {data.hex(' ')}"
    names = [f"In{chr(65 + i)}" for i in range(profile.input_count)] + [
        f"Out{i + 1}" for i in range(profile.output_count)
    ]
    lines = [f"chan    raw       {profile.meter_format.value} dB"]
    for i, name in enumerate(names):
        level = reading.levels_db[i]
        db = "   n/a" if level is None else f"{level:6.1f}"
        clip = "  CLIP" if reading.clip[i] else ""
        slot = profile.meter_slot(i)
        lines.append(f"{name:<6}  {data[3 * slot : 3 * slot + 3].hex(' ')}  {db}{clip}")

    def outputs(flags: tuple[bool, ...] | None) -> str:
        if flags is None:
            return "n/a"
        return " ".join(f"Out{i + 1}" for i, on in enumerate(flags) if on) or "-"

    lines.append(f"tail    {data[3 * profile.meter_slot_count :].hex(' ')}")
    lines.append(f"comp    {outputs(reading.comp)}")
    lines.append(f"limit   {outputs(reading.limit)}")
    return "\n".join(lines)


def format_diff(before: bytes, after: bytes, layout: cm.ConfigLayout = cm.LAYOUT_408) -> str:
    changes = cm.diff_blobs(before, after, layout)
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
    "read_identity",
    "read_info",
    "read_meters",
    "send_raw",
    "watch_meters",
]
