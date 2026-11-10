"""The DSP models the simulator can play, and the replies that differ between them.

The protocol profile (``protocol/profiles/``) holds what the backend needs too: topology,
address, config pages, meter slots. This module only adds the bytes of the init replies, which
the backend reads but does not interpret.

Sources (docs/PROTOCOL.md): the 408 replies were recorded on a real DSP 408 (firmware V0104P);
the 206 replies come from Wireshark captures of a real DSP 206 (firmware V0104P) published by
FlexiFlizz/t.racks-DSP-control. The 204's protocol is documented by Givou/BetterDSPControl
(tested on a real 204), but not the exact bytes of these replies: they copy the 206's.
"""

from __future__ import annotations

from dataclasses import dataclass

from tracks_dsp_controller.protocol.profile import ProtocolProfile, load_profile


@dataclass(frozen=True, slots=True)
class SimModel:
    key: str  # "408", "206", "204"
    identity: str  # 0x13 reply text
    handshake: bytes  # 0x10 reply data
    status: bytes  # 0x2c reply data (the last byte is 1 when the device is PIN-locked)
    preset_header: bytes  # 0x22 reply data
    name_ack: bytes  # 0x26 reply data before the echoed name
    replies_observed: bool  # False: the init reply bytes are copied from a sibling model

    def profile(self, path: str | None = None) -> ProtocolProfile:
        """The built-in protocol profile of this model, optionally overridden by a file."""
        return load_profile(path, model=self.key)


SIM_MODELS: dict[str, SimModel] = {
    "408": SimModel(
        key="408",
        identity="DSP408 V0104P",
        handshake=b"\x13",
        status=bytes.fromhex("00 27 0f 00 00 00"),
        preset_header=b"\xff\xff" + bytes(28),
        name_ack=b"\x01",
        replies_observed=True,
    ),
    "206": SimModel(
        key="206",
        identity="DSP206 V0104P",
        handshake=b"\x19",
        status=bytes.fromhex("00 27 0f 00 00 00"),
        preset_header=bytes(20),
        name_ack=b"\x00",
        replies_observed=True,
    ),
    "204": SimModel(
        key="204",
        identity="DSP204 V0104P",
        handshake=b"\x19",
        status=bytes.fromhex("00 27 0f 00 00 00"),
        preset_header=bytes(20),
        name_ack=b"\x00",
        replies_observed=False,
    ),
}
DEFAULT_MODEL = "408"
