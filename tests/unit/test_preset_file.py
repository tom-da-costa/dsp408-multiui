"""Preset files (.prs) of the official editor, and the plan that loads one into a DSP."""

from dataclasses import replace
from pathlib import Path

import pytest

from tracks_dsp_controller.protocol import commands as cmd
from tracks_dsp_controller.protocol import config_map as cm
from tracks_dsp_controller.protocol import preset_file as pf
from tracks_dsp_controller.protocol.profile import DEFAULT_PROFILE as P
from tracks_dsp_controller.protocol.profile import load_profile
from tracks_dsp_controller.simulator import SimulatedDevice

FIXTURES = Path(__file__).parent.parent / "fixtures"
EDITOR_FILE = FIXTURES / "presets" / "dsp408_editor.prs"
U08 = FIXTURES / "config" / "dsp408_u08.bin"


@pytest.fixture(scope="module")
def data() -> bytes:
    return EDITOR_FILE.read_bytes()


@pytest.fixture(scope="module")
def target(data: bytes) -> cm.RawConfig:
    return cm.decode_config(pf.decode_preset_file(data, "408", cm.LAYOUT_408))


def test_editor_file_layout(data: bytes, target: cm.RawConfig) -> None:
    assert len(data) == pf.file_size(cm.LAYOUT_408) == 1452
    assert data.startswith(b"***DSP408V010***")
    assert data.endswith(b"\r\n")
    assert pf.file_model(data) == "408"
    assert target.marker == cm.MARKER_MODIFIED
    assert target.preset_name == "FSMXLmGDLsEq"
    assert [c.name for c in target.inputs] == ["In Left", "In Right", "InC", "InD"]
    assert [c.name for c in target.outputs] == ["Sub", "Kick", "Med", "High"] * 2
    assert [c.link for c in target.inputs] == [3, 0, 12, 0]
    assert [c.link for c in target.outputs] == [0x11, 0x22, 0x44, 0x88, 0, 0, 0, 0]
    assert [c.mute for c in target.inputs] == [False, False, True, True]
    assert target.outputs[3].delay == 506  # 5.27 ms
    assert target.outputs[0].crossover == cm.RawCrossover(21, 61, 18, 10)
    # Not in the file: whole-PEQ bypass off, unknown trailer bytes 0.
    assert target.image[pf.stored_end(cm.LAYOUT_408) :] == bytes(12)


def test_round_trip_is_byte_exact(data: bytes) -> None:
    blob = pf.decode_preset_file(data, "408", cm.LAYOUT_408)
    assert pf.encode_preset_file(blob, cm.LAYOUT_408, "DSP408 V0104P") == data
    # The final line break is optional.
    assert pf.decode_preset_file(data[:-2], "408", cm.LAYOUT_408) == blob


def test_export_of_a_live_blob() -> None:
    blob = U08.read_bytes()
    data = pf.encode_preset_file(blob, cm.LAYOUT_408, "DSP408 V0104P")
    assert len(data) == 1452
    assert data[16:30] == blob[2:16]
    back = pf.decode_preset_file(data, "408", cm.LAYOUT_408)
    assert back[2 : pf.stored_end(cm.LAYOUT_408)] == blob[2 : pf.stored_end(cm.LAYOUT_408)]


@pytest.mark.parametrize("model", ["206", "204"])
def test_other_models_use_their_layout(model: str) -> None:
    layout = cm.layout_for(load_profile(model=model))
    blob = cm.encode_config(cm.default_config("Small", layout))
    data = pf.encode_preset_file(blob, layout, f"DSP{model} V0104P")
    assert data.startswith(f"***DSP{model}V010***".encode())
    assert len(data) == pf.file_size(layout)
    assert pf.decode_preset_file(data, model, layout)[2:-12] == blob[2:-12]
    with pytest.raises(pf.PresetFileError, match=f"for a DSP {model}, not a DSP 408"):
        pf.decode_preset_file(data, "408", cm.LAYOUT_408)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"", "not a t.racks preset"),
        (b"hello world, this is not a preset file", "not a t.racks preset"),
        (b"***FIR408V010***" + bytes(1436), "unsupported device"),
        (b"***DSP408V010***" + bytes(100), "100 bytes|116 bytes"),
    ],
)
def test_bad_files_are_refused(data: bytes, message: str) -> None:
    with pytest.raises(pf.PresetFileError, match=message):
        pf.decode_preset_file(data, "408", cm.LAYOUT_408)


def test_names() -> None:
    assert pf.header_for("DSP408 V0104P") == b"***DSP408V010***"
    assert pf.ascii_name("Pas touché svp", 14) == "Pas touche svp"
    assert pf.ascii_name("Bühne 2 → L", 14) == "Buhne 2 ? L"
    assert pf.ascii_name("A very long preset name", 14) == "A very long pr"
    assert pf.file_name("Pas touché svp") == "Pas touché svp.prs"
    assert pf.file_name('a/b:c*?"<>|') == "a_b_c_.prs"
    assert pf.file_name("..") == "preset.prs"


def apply(requests: tuple[cmd.Request, ...], device: SimulatedDevice) -> None:
    for request in requests:
        reply = device.handle(request.encode(P))
        assert reply.response is not None, request


def test_plan_loads_the_file_into_a_device(target: cm.RawConfig) -> None:
    device = SimulatedDevice(P)
    device.live = cm.decode_config(U08.read_bytes())
    plan = pf.plan_import(device.live, target, P)
    assert plan.notes == ()
    # Outputs muted first, unlinked before any parameter write, back on last.
    unlinked = plan.requests.index(cmd.Activate())
    mutes = plan.requests[:8]
    assert mutes == tuple(cmd.SetMute(ch, True) for ch in range(4, 12))
    assert all(isinstance(r, cmd.SetLink) for r in plan.requests[8:unlinked])
    relink = next(i for i, r in enumerate(plan.requests) if isinstance(r, cmd.PrepareLink))
    assert not any(isinstance(r, cmd.SetLink) for r in plan.requests[unlinked:relink])
    assert plan.requests[-9:-1] == tuple(cmd.SetMute(ch, False) for ch in range(4, 12))
    apply(plan.requests, device)
    assert pf.mismatches(plan.expected, device.config_blob, cm.LAYOUT_408) == []
    live = device.config_blob
    expected = pf.decode_preset_file(EDITOR_FILE.read_bytes(), "408", cm.LAYOUT_408)
    differing = {name for *_, name in cm.diff_blobs(expected, live)}
    assert differing <= {"marker", "preset_name"}  # the name comes with a store


def test_plan_writes_only_what_differs(target: cm.RawConfig) -> None:
    current = replace(target, image=cm.encode_config(target))
    plan = pf.plan_import(current, target, P)
    kinds = {type(r) for r in plan.requests}
    # Links are set again (2a + 3b), mutes go off and on: nothing else.
    assert kinds == {cmd.SetMute, cmd.SetLink, cmd.PrepareLink, cmd.Activate}


def test_plan_notes_what_it_cannot_load(target: cm.RawConfig) -> None:
    device = SimulatedDevice(P)
    out = replace(target.outputs[2], name="Médium", crosspoints=(200, 280, 280, 280))
    wanted = replace(target, outputs=(*target.outputs[:2], out, *target.outputs[3:]))
    plan = pf.plan_import(device.live, wanted, P)
    assert plan.notes == (
        "Out 3: matrix levels not loaded (kept as they are)",
        "Out 3: name 'Médium' written as 'Medium'",
    )
    apply(plan.requests, device)
    assert device.live.outputs[2].name == "Medium"
    assert pf.mismatches(plan.expected, device.config_blob, cm.LAYOUT_408) == []


def test_plan_refuses_values_the_dsp_refuses(target: cm.RawConfig) -> None:
    bad = replace(target.outputs[0], gain=999)
    wanted = replace(target, outputs=(bad, *target.outputs[1:]))
    with pytest.raises(pf.PresetFileError, match="gain=999"):
        pf.plan_import(SimulatedDevice(P).live, wanted, P)
    small = cm.default_config(layout=cm.ConfigLayout(2, 6))
    with pytest.raises(pf.PresetFileError, match="channels"):
        pf.plan_import(SimulatedDevice(P).live, small, P)


def test_mismatches_report_fields_and_links(target: cm.RawConfig) -> None:
    expected = cm.encode_config(target)
    changed = replace(target.outputs[0], gain=100, link=1)
    other = cm.encode_config(replace(target, outputs=(changed, *target.outputs[1:])))
    assert pf.mismatches(expected, other, cm.LAYOUT_408) == ["out0.gain", "outputs.links"]
