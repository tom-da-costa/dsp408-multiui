from pathlib import Path
from typing import Any

import pytest

from tracks_dsp_controller.protocol import commands as c
from tracks_dsp_controller.protocol import config_map as cm
from tracks_dsp_controller.protocol.profile import DEFAULT_PROFILE as P
from tracks_dsp_controller.state.convert import build_state
from tracks_dsp_controller.state.models import DeviceInfo, DeviceState
from tracks_dsp_controller.state.registry import ParamError, resolve
from tracks_dsp_controller.state.store import Patch, Snapshot, StateStore, get_path, set_path

FOREST = Path(__file__).parent.parent / "fixtures" / "config" / "forest_408.bin"
U08 = FOREST.with_name("dsp408_u08.bin")


def forest_state(previous: DeviceState | None = None) -> DeviceState:
    raw = cm.decode_config(FOREST.read_bytes())
    return build_state(
        raw,
        P,
        info=DeviceInfo(identity="DSP408 V1.04", model="DSP408", firmware="V1.04"),
        preset_names=[f"P{i}" for i in range(1, 21)],
        active_slot=3,
        previous=previous,
    )


@pytest.fixture
def state() -> DeviceState:
    return forest_state()


# --- conversion --------------------------------------------------------------------------------
def test_build_state_from_real_dump(state: DeviceState) -> None:
    assert state.preset_name == "Forest"
    assert state.active_slot == 3
    assert [p.slot for p in state.presets] == list(range(1, 21))
    assert [ch.index for ch in state.inputs] == [0, 1, 2, 3]
    assert [ch.index for ch in state.outputs] == list(range(4, 12))
    out1 = state.outputs[0]
    assert out1.matrix == [True, True, True, True]
    assert out1.crossover.hpf.freq_hz == pytest.approx(25.4, abs=0.1)
    assert out1.crossover.hpf.slope == 8
    assert out1.crossover.hpf.enabled
    assert out1.crossover.lpf.freq_hz == pytest.approx(80.6, abs=0.1)
    assert out1.compressor.threshold_db == 20.0
    assert out1.compressor.attack_ms == 50.0
    assert out1.limiter.release_ms == 500.0
    assert state.inputs[0].geq[20] == pytest.approx(-4.7)
    assert state.inputs[0].gate.threshold_db == -90.0
    assert state.outputs[7].crossover.hpf.enabled is False
    assert state.outputs[7].crossover.hpf.slope == 10  # bypassed: default LR-24
    assert all(ch.gain_db == 0.0 for ch in state.outputs)


def test_previous_state_keeps_the_remembered_slope(state: DeviceState) -> None:
    state.outputs[7].crossover.hpf.slope = 3
    state.outputs[0].peq[2].bypass = True  # bypass comes from the blob, not from previous
    rebuilt = forest_state(previous=state)
    assert rebuilt.outputs[7].crossover.hpf.slope == 3
    assert not rebuilt.outputs[0].peq[2].bypass


def test_bypass_comes_from_the_blob(state: DeviceState) -> None:
    assert state.inputs[0].peq[0].bypass
    assert [b.bypass for b in state.outputs[1].peq] == [False, False] + [True] * 7
    assert not any(ch.peq_bypass for ch in [*state.inputs, *state.outputs])


def u08_state() -> DeviceState:
    raw = cm.decode_config(U08.read_bytes())
    info = DeviceInfo(identity="DSP408 V0104P", model="DSP408", firmware="V0104P")
    names = [f"P{i}" for i in range(1, 21)]
    return build_state(raw, P, info=info, preset_names=names, active_slot=8)


def test_real_u08_dump() -> None:
    state = u08_state()
    assert state.preset_name == "Pas touché svp"
    assert [o.name for o in state.outputs[:4]] == ["Sub", "Kick", "Med L", "High L"]
    # the official editor shows 0 / 4.44 / 5.65 / 5.74 ms
    delays = [o.delay_ms for o in state.outputs[:4]]
    assert delays == pytest.approx([0, 4.44, 5.65, 5.74], abs=0.005)
    assert [o.linked for o in state.outputs] == [[4], [5], [6], [7], [0], [1], [2], [3]]
    assert [i.linked for i in state.inputs] == [[1], [0], [], []]
    assert not any(ch.mute or ch.phase for ch in [*state.inputs, *state.outputs])
    assert state.outputs[0].crossover.hpf.freq_hz == pytest.approx(32, abs=0.5)


def test_writes_are_copied_to_linked_channels() -> None:
    state = u08_state()
    write = resolve("outputs.5.gain_db", -2.0, state, P)  # Out6, linked with Out2
    assert write.changes == (("outputs.5.gain_db", -2.0), ("outputs.1.gain_db", -2.0))
    write = resolve("outputs.0.peq.3", {"gain_db": 4.0}, state, P)
    paths = [p for p, _ in write.changes]
    assert paths == ["outputs.0.peq.3", "outputs.4.peq.3"]
    assert write.changes[0][1] == write.changes[1][1]
    assert [p for p, _ in resolve("inputs.1.mute", True, state, P).changes] == [
        "inputs.1.mute",
        "inputs.0.mute",
    ]
    # not copied: names, matrix; unlinked channels
    assert len(resolve("outputs.0.name", "Solo", state, P).changes) == 1
    assert len(resolve("outputs.0.matrix", [True, False, False, False], state, P).changes) == 1
    assert len(resolve("inputs.2.gain_db", 0, state, P).changes) == 1


# --- registry ------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("path", "value", "request_", "new_value"),
    [
        ("outputs.0.gain_db", -3.24, c.SetGain(4, 248), -3.2),
        ("inputs.1.gain_db", -100, c.SetGain(1, 0), -60.0),
        ("outputs.2.mute", True, c.SetMute(6, True), True),
        ("inputs.0.phase", True, c.SetPhase(0, True), True),
        ("outputs.1.peq_bypass", True, c.SetPeqBypass(5, True), True),
        ("outputs.7.name", "MonR", c.SetChannelName(11, "MonR"), "MonR"),
        ("outputs.0.delay_ms", 1.0, c.SetDelay(4, 96), 1.0),
        ("inputs.2.delay_ms", 2.0, c.SetDelay(2, 192), 2.0),  # inputs have a delay too
        (
            "outputs.0.matrix",
            [True, False, True, False],
            c.SetMatrix(4, 0b0101),
            [True, False, True, False],
        ),
        ("inputs.3.geq.30", 12.5, c.SetGeqBand(3, 30, 240), 12.0),
    ],
)
def test_resolve_simple(
    state: DeviceState, path: str, value: Any, request_: c.Request, new_value: Any
) -> None:
    write = resolve(path, value, state, P)
    assert write.request == request_
    assert write.changes == ((path, new_value),)


def test_resolve_peq_partial_merge(state: DeviceState) -> None:
    write = resolve("outputs.2.peq.4", {"gain_db": -3.0}, state, P)
    assert isinstance(write.request, c.SetPeqBand)
    current = state.outputs[2].peq[4]
    assert write.request.gain == 90
    assert write.request.type == current.type
    ((path, value),) = write.changes
    assert path == "outputs.2.peq.4"
    assert value["gain_db"] == -3.0
    assert value["freq_hz"] == pytest.approx(current.freq_hz, rel=0.01)
    assert write.kind == "peq"
    assert write.hardware_verified


def test_resolve_crossover_bypass_sends_slope_zero(state: DeviceState) -> None:
    write = resolve("outputs.0.crossover.hpf", {"enabled": False}, state, P)
    assert write.request == c.SetHighPass(4, 11, 0)
    assert write.changes[0][1]["slope"] == 8  # remembered
    write = resolve("outputs.0.crossover.lpf", {"freq_hz": 100.0, "slope": 3}, state, P)
    assert isinstance(write.request, c.SetLowPass)
    assert write.request.slope == 3


def test_resolve_dynamics(state: DeviceState) -> None:
    write = resolve("outputs.1.compressor", {"ratio": 5, "threshold_db": -10.0}, state, P)
    assert write.request == c.SetCompressor(5, 5, 49, 499, 0, 160)
    write = resolve("outputs.1.limiter", {"threshold_db": -6.0}, state, P)
    assert write.request == c.SetLimiter(5, 49, 499, 0, 168)
    write = resolve("inputs.2.gate", {"threshold_db": -40.0, "hold_ms": 20}, state, P)
    assert write.request == c.SetGate(2, 0, 99, 19, 100)


def test_every_parameter_kind_is_hardware_verified(state: DeviceState) -> None:
    assert resolve("outputs.0.gain_db", 0, state, P).hardware_verified
    assert resolve("outputs.0.delay_ms", 1, state, P).hardware_verified
    assert resolve("inputs.0.gate", {"hold_ms": 20}, state, P).hardware_verified


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("outputs.8.gain_db", 0),
        ("outputs.x.gain_db", 0),
        ("inputs.0.matrix", [True] * 4),
        ("outputs.0.geq.0", 0),  # GEQ is input-only
        ("inputs.0.geq.31", 0),
        ("outputs.0.peq.9", {}),
        ("outputs.0.peq.0", {"type": 9}),
        ("outputs.0.peq.0", {"gain_db": 20}),
        ("outputs.0.peq.0", {"bogus": 1}),
        ("outputs.0.peq.0", 3),
        ("outputs.0.crossover.hpf", {"slope": 21}),
        ("outputs.0.crossover.bpf", {}),
        ("outputs.0.gain_db", "loud"),
        ("outputs.0.gain_db", True),
        ("outputs.0.gain_db", float("nan")),
        ("outputs.0.mute", 1),
        ("outputs.0.matrix", [True]),
        ("outputs.0.name", "toolongname"),
        ("outputs.0.name", 5),
        ("outputs.0.compressor", {"ratio": 16}),
        ("outputs.0.gain_db.extra", 0),
        ("presets.0.name", "x"),
        ("outputs", 1),
    ],
)
def test_resolve_rejects(state: DeviceState, path: str, value: Any) -> None:
    with pytest.raises(ParamError):
        resolve(path, value, state, P)


# --- store ---------------------------------------------------------------------------------------
def test_store_replace_and_apply(state: DeviceState) -> None:
    store = StateStore()
    events: list[Snapshot | Patch] = []
    unsubscribe = store.subscribe(events.append)
    snap = store.replace(state)
    assert snap.rev == 1
    assert snap.state["outputs"][0]["gain_db"] == 0.0
    write = resolve("outputs.0.peq.1", {"gain_db": 6.0}, state, P)
    patch = store.apply(write.changes, "client-1")
    assert patch.rev == 2
    assert patch.origin == "client-1"
    assert store.state.outputs[0].peq[1].gain_db == 6.0
    store.apply([("outputs.0.gain_db", -6.0), ("active_slot", 4)], "x")
    assert get_path(store.state, "outputs.0.gain_db") == -6.0
    assert store.state.active_slot == 4
    assert [type(e).__name__ for e in events] == ["Snapshot", "Patch", "Patch"]
    unsubscribe()
    store.apply([("outputs.0.mute", True)], "x")
    assert len(events) == 3


def test_store_listener_errors_are_contained(state: DeviceState) -> None:
    store = StateStore()

    def broken(event: Snapshot | Patch) -> None:
        raise RuntimeError("boom")

    store.subscribe(broken)
    assert store.replace(state).rev == 1


def test_set_path_validates(state: DeviceState) -> None:
    set_path(state, "outputs.0.crossover.hpf", {"freq_hz": 50.0, "slope": 3, "enabled": True})
    assert state.outputs[0].crossover.hpf.slope == 3
    set_path(state, "inputs.0.geq.2", 1.5)
    assert state.inputs[0].geq[2] == 1.5
    with pytest.raises(ValueError, match="validation"):
        set_path(state, "outputs.0.gain_db", 99)
