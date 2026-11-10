"""JSONL logging of protocol frames (simulator and proxy)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import IO

from tracks_dsp_controller.protocol import commands as cmd
from tracks_dsp_controller.protocol import responses as rsp
from tracks_dsp_controller.protocol.framing import Frame
from tracks_dsp_controller.protocol.profile import ProtocolProfile

TO_DEVICE = "host->dsp"
FROM_DEVICE = "dsp->host"


def describe(frame: Frame, profile: ProtocolProfile) -> str:
    """Decoded form of a frame, or the decoding error."""
    try:
        if frame.from_device:
            return repr(rsp.decode_response(frame.payload))
        return repr(cmd.decode_request(frame.payload, profile))
    except ValueError as exc:
        return f"<undecodable: {exc}>"


class FrameLog:
    """Append one JSON object per frame: ts, dir, hex, decoded."""

    def __init__(self, target: str | Path | IO[str], profile: ProtocolProfile) -> None:
        self.profile = profile
        if isinstance(target, str | Path):
            self._handle: IO[str] = Path(target).open("a", encoding="utf-8")  # noqa: SIM115
            self._owned = True
        else:
            self._handle = target
            self._owned = False

    def write(self, direction: str, frame: Frame, note: str | None = None) -> None:
        record = {
            "ts": round(time.time(), 6),
            "dir": direction,
            "hex": frame.encode().hex(" "),
            "decoded": describe(frame, self.profile),
        }
        if note:
            record["note"] = note
        self._handle.write(json.dumps(record) + "\n")
        self._handle.flush()

    def close(self) -> None:
        if self._owned:
            self._handle.close()
