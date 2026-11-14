"""Setup wizard plan → raw target configuration."""

from dataclasses import replace
from typing import Any

import pytest

from tracks_dsp_controller.protocol import codecs as c
from tracks_dsp_controller.protocol import config_map as cm
from tracks_dsp_controller.protocol import preset_file as pf
from tracks_dsp_controller.protocol.profile import DEFAULT_PROFILE
from tracks_dsp_controller.state.registry import ParamError
from tracks_dsp_controller.state.setup import LIMIT_RATIO, SetupPlan, build_target

P = DEFAULT_PROFILE


def output(name: str, used: bool = True, **extra: Any) -> dict[str, Any]:
    return {"name": name, "used": used, "sources": [False] * 4, **extra}


def plan_dict() -> dict[str, Any]:
    """Stereo source on In A/B; a mono sub on Out1, stereo tops on Out2/Out3."""
    outputs = [
        output(
            "Sub",
            sources=[True, True, False, False],
            gain_db=0.0,
            hpf={"freq_hz": 38, "slope": 8},
            lpf={"freq_hz": 105, "slope": 10},
            dynamics={"compressor_threshold_db": 0.5, "limiter_threshold_db": 6.5},
        ),
        output(
            "Top L",
            sources=[True, False, False, False],
            gain_db=-4.3,
            phase=True,
            hpf={"freq_hz": 105, "slope": 10},
        ),
        output(
            "Top R",
            sources=[False, True, False, False],
            gain_db=-4.3,
            phase=True,
            hpf={"freq_hz": 105, "slope": 10},
        ),
        *(output(f"Out{n}", used=False) for n in range(4, 9)),
    ]
    return {
        "inputs": [
            {"name": "Mix L", "low_shelf": {"freq_hz": 100, "gain_db": 3}},
            {"name": "Mix R", "low_shelf": {"freq_hz": 100, "gain_db": 3}},
            {"name": "InC"},
            {"name": "InD"},
        ],
        "outputs": outputs,
        "input_links": [[0, 1]],
        "output_links": [[1, 2]],
    }


def current() -> cm.RawConfig:
    """A live config full of leftovers, which the wizard must reset."""
    base = cm.default_config("Old show")
    outputs = replace(base.outputs[0], delay=500, crosspoints=(200, 280, 280, 280))
    inputs = replace(base.inputs[0], gate=cm.RawGate(threshold=100), geq=(130,) * 31)
    config = replace(base, inputs=(inputs, *base.inputs[1:]), outputs=(outputs, *base.outputs[1:]))
    return replace(config, image=cm.encode_config(config))


def test_builds_the_whole_configuration() -> None:
    target = build_target(SetupPlan.model_validate(plan_dict()), current(), P, "Club")
    sub, top_l, top_r, spare = (
        target.outputs[0],
        target.outputs[1],
        target.outputs[2],
        target.outputs[3],
    )
    assert target.preset_name == "Club"
    assert [o.name for o in target.outputs[:3]] == ["Sub", "Top L", "Top R"]
    assert (sub.matrix, top_l.matrix, top_r.matrix, spare.matrix) == (0b11, 0b01, 0b10, 0)
    assert sub.crossover == cm.RawCrossover(
        c.freq_hz_to_raw(38, P), c.freq_hz_to_raw(105, P), 8, 10
    )
    assert top_l.crossover.lpf_slope == 0  # no low-pass on the top way
    assert sub.compressor.ratio == LIMIT_RATIO
    assert c.threshold_raw_to_db(sub.compressor.threshold) == 0.5
    assert c.threshold_raw_to_db(sub.limiter.threshold) == 6.5
    assert c.time_raw_to_ms(sub.compressor.attack) == 1
    assert c.time_raw_to_ms(sub.limiter.release) == 1000
    assert top_l.compressor == cm.RawCompressor()  # no dynamics asked: the defaults
    assert c.gain_raw_to_db(top_l.gain) == pytest.approx(-4.3, abs=0.1)
    assert (top_l.phase, sub.phase) == (True, False)
    # Leftovers reset; the crosspoint levels cannot be written, so they stay.
    assert sub.delay == 0
    assert sub.crosspoints == (200, 280, 280, 280)
    assert target.inputs[0].gate == cm.RawGate()
    assert target.inputs[0].geq == (cm.EQ_FLAT_RAW,) * 31
    # Mutes: every input, and the outputs not used.
    assert all(i.mute for i in target.inputs)
    assert [o.mute for o in target.outputs] == [False] * 3 + [True] * 5
    # Links: the master holds the group's mask.
    assert [i.link for i in target.inputs] == [0b11, 0, 0b100, 0b1000]
    assert [o.link for o in target.outputs[:3]] == [0b1, 0b110, 0]
    # The low shelf on the inputs' first PEQ band.
    shelf = target.inputs[0].peq[0]
    assert P.peq_types[shelf.type] == "Low Shelf"
    assert c.eq_gain_raw_to_db(shelf.gain) == 3.0
    assert target.inputs[2].peq[0].type == 0


def test_loads_with_the_preset_sequence() -> None:
    live = current()
    target = build_target(SetupPlan.model_validate(plan_dict()), live, P, "Club")
    plan = pf.plan_import(live, target, P)
    assert not plan.notes  # crosspoints kept, names plain ASCII


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d["inputs"].pop(),
        lambda d: d["outputs"][0].update(name="Too long name"),
        lambda d: d["outputs"][0].update(sources=[True]),
        lambda d: d["outputs"][0]["hpf"].update(slope=21),
        lambda d: d.update(output_links=[[0, 1], [1, 2]]),
        lambda d: d.update(input_links=[[0, 9]]),
    ],
)
def test_refuses_bad_plans(change: Any) -> None:
    data = plan_dict()
    change(data)
    with pytest.raises(ParamError):
        build_target(SetupPlan.model_validate(data), current(), P, "Club")
