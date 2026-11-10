"""The DSP 204 profile against what Givou/BetterDSPControl observed on a real DSP 204
(firmware V0104P): see docs/PROTOCOL.md §10 and the README attribution table.

The link masks and limiter status bytes below come from BetterDSPControl
(https://git.thiemoo.at/Givou/BetterDSPControl), Copyright (c) 2026 Givou, MIT License.
"""

from dataclasses import replace

from tracks_dsp_controller.protocol import commands as c
from tracks_dsp_controller.protocol import config_map as cm
from tracks_dsp_controller.protocol.framing import encode_frame
from tracks_dsp_controller.protocol.meters import decode_meters, meter_data_length
from tracks_dsp_controller.protocol.profile import load_profile
from tracks_dsp_controller.simulator import SimulatedDevice
from tracks_dsp_controller.simulator.models import SIM_MODELS

P204 = load_profile(model="204")
L204 = cm.layout_for(P204)


def test_topology_address_and_config_size() -> None:
    assert (P204.input_count, P204.output_count, P204.preset_count) == (2, 4, 20)
    assert P204.host_dst == 0x01  # BetterDSPControl talks to its 204 as device 01
    assert encode_frame(b"\x40", dst=P204.host_dst) == bytes.fromhex("10 02 00 01 01 40 10 03 41")
    # Config: 724 bytes in chunks 0-14 (the 408 records with 2 inputs and 4 outputs)
    assert (L204.size, P204.config_size, P204.page_count) == (724, 724, 15)
    assert L204.output_record == 100
    # Out 1-4 are channels 2-5 on the wire
    assert c.SetGain(5, 280).encode(P204) == bytes.fromhex("34 05 18 01")


def test_meter_slots_and_limiter_bits_seen_on_a_204() -> None:
    assert meter_data_length(P204) == 38
    assert [P204.meter_slot(ch) for ch in range(6)] == [0, 1, 4, 5, 6, 7]
    # Status bytes seen on a DSP 204 while forcing the limiters: 00 03 = Out 1+2, 00 0C = Out 3+4
    assert decode_meters(bytes(36) + b"\x00\x03", P204).limit == (True, True, False, False)
    assert decode_meters(bytes(36) + b"\x00\x0c", P204).limit == (False, False, True, True)
    assert decode_meters(bytes(36) + b"\x00\x0c", P204).comp == (False,) * 4


def test_link_masks_read_from_a_204() -> None:
    """Masks read from a real DSP 204 with In A+B, Out 1+2 and Out 3+4 linked: 3 0 / 3 0 12 0."""
    inputs, outputs = [3, 0], [3, 0, 12, 0]
    assert cm.link_group(inputs, 1) == (0, 1)
    assert cm.link_group(outputs, 1) == (0, 1)
    assert cm.link_group(outputs, 3) == (2, 3)
    base = cm.default_config("Links", L204)
    config = replace(
        base,
        inputs=tuple(replace(ch, link=m) for ch, m in zip(base.inputs, inputs, strict=True)),
        outputs=tuple(replace(ch, link=m) for ch, m in zip(base.outputs, outputs, strict=True)),
    )
    config = replace(config, image=cm.encode_config(config))
    # The 204 applies a change on any member to its group, except the name (BetterDSPControl).
    device = SimulatedDevice(P204, model=SIM_MODELS["204"])
    device.set_preset(1, config)
    device.load(1)
    device.handle(c.SetGain(5, 100).encode(P204))  # Out 4
    device.handle(c.SetChannelName(5, "Sub").encode(P204))
    assert device.live.outputs[2].gain == device.live.outputs[3].gain == 100
    assert (device.live.outputs[2].name, device.live.outputs[3].name) == ("Out3", "Sub")
