"""The simulator reproduces, byte for byte, what a real DSP 408 stored for each write."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from tracks_dsp_controller.protocol import config_map as cm
from tracks_dsp_controller.protocol.profile import DEFAULT_PROFILE as P
from tracks_dsp_controller.simulator import SimulatedDevice

FIXTURES = Path(__file__).parent.parent / "fixtures" / "hardware"
DOC = json.loads((FIXTURES / "write_diffs.json").read_text())


def test_fixture_is_complete() -> None:
    assert len(DOC["steps"]) == 40
    assert all(step["reply"] == "01" for step in DOC["steps"])  # every write was ACKed


def test_simulator_matches_every_recorded_write() -> None:
    device = SimulatedDevice(P)
    base = cm.decode_config((FIXTURES / DOC["base"]).read_bytes())
    device.live = base
    before = device.config_blob
    assert before == base.image  # the base decodes and re-encodes byte-exactly
    for step in DOC["steps"]:
        reply = device.handle(bytes.fromhex(step["request"]))
        assert reply.response is not None
        assert reply.response.encode().hex(" ") == step["reply"], step["label"]
        after = device.config_blob
        got = [[o, f"{a:02x}", f"{b:02x}"] for o, a, b, _ in cm.diff_blobs(before, after)]
        want = [change[:3] for change in step["changes"]]
        # the simulator marks the config as modified; the copy was already marked
        assert got == want, step["label"]
        before = after


@pytest.mark.parametrize("step", DOC["steps"], ids=[s["label"] for s in DOC["steps"]])
def test_field_names_match_the_verified_layout(step: dict[str, object]) -> None:
    for offset, _, _, _ in step["changes"]:  # type: ignore[attr-defined]
        assert "HYP" not in cm.field_at(offset)
        assert ".+" not in cm.field_at(offset)


def test_marker_is_already_modified() -> None:
    base = cm.decode_config((FIXTURES / DOC["base"]).read_bytes())
    assert base.marker == cm.MARKER_MODIFIED
    assert replace(base, marker=cm.MARKER_MODIFIED) == base


LINKS = json.loads((FIXTURES / "link_diffs.json").read_text())


def test_simulator_matches_the_recorded_link_writes() -> None:
    """2a copies the master's settings except name and routing; 3b writes the link mask."""
    device = SimulatedDevice(P)
    device.live = cm.decode_config((FIXTURES / LINKS["base"]).read_bytes())
    before = device.config_blob
    assert len(LINKS["steps"]) == 32
    for step in LINKS["steps"]:
        reply = device.handle(bytes.fromhex(step["request"]))
        assert reply.response is not None
        assert reply.response.encode().hex(" ") == step["reply"], step["label"]
        after = device.config_blob
        got = [[o, f"{a:02x}", f"{b:02x}"] for o, a, b, _ in cm.diff_blobs(before, after)]
        assert got == [change[:3] for change in step["changes"]], step["label"]
        before = after
