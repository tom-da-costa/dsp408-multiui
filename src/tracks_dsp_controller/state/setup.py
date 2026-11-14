"""Setup wizard: a whole configuration described in physical units → the raw config to load.

The wizard (UI, Setup tab) works out the routing, names, links, crossovers, gains, polarity and
limiter thresholds of a speaker stack and sends them as a ``SetupPlan``. The server never trusts
it: every value is validated, clamped and quantised here, through the same codecs as a single
parameter write. Everything the plan does not set is reset (flat EQ, no delay, gate off), unused
outputs are muted, and so are all the inputs: the user lets the sound in once the system is
checked. The result is loaded with the preset-file sequence (``preset_file.plan_import``).
"""

from __future__ import annotations

from dataclasses import replace

from pydantic import BaseModel, ConfigDict, Field

from tracks_dsp_controller.protocol import codecs as c
from tracks_dsp_controller.protocol import config_map as cm
from tracks_dsp_controller.protocol.links import LinkError, masks_for, normalise
from tracks_dsp_controller.protocol.profile import ProtocolProfile
from tracks_dsp_controller.state.registry import ParamError

# Dynamics as the limiter calculator sets them: the compressor at ratio "Limit" holds the
# computed threshold, the limiter sits above it as a safety net.
DYNAMICS_ATTACK_MS = 1.0
DYNAMICS_RELEASE_MS = 1000.0
LIMIT_RATIO = c.COMPRESSOR_RATIOS.index("Limit")
SHELF_Q = 0.7


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SetupFilter(_Model):
    freq_hz: float = Field(gt=0)
    slope: int = Field(ge=1)  # index into profile.slopes (0 = "Off" is not a slope)


class SetupShelf(_Model):
    freq_hz: float = Field(gt=0)
    gain_db: float = Field(ge=c.EQ_GAIN_MIN_DB, le=c.EQ_GAIN_MAX_DB)


class SetupInput(_Model):
    name: str
    gain_db: float = Field(0.0, ge=c.GAIN_MIN_DB, le=c.GAIN_MAX_DB)
    low_shelf: SetupShelf | None = None


class SetupDynamics(_Model):
    compressor_threshold_db: float = Field(ge=c.THRESHOLD_MIN_DB, le=c.DYNAMICS_THRESHOLD_MAX_DB)
    limiter_threshold_db: float = Field(ge=c.THRESHOLD_MIN_DB, le=c.DYNAMICS_THRESHOLD_MAX_DB)


class SetupOutput(_Model):
    name: str
    used: bool
    sources: list[bool]  # one flag per input: the matrix
    gain_db: float = Field(0.0, ge=c.GAIN_MIN_DB, le=c.GAIN_MAX_DB)
    phase: bool = False
    hpf: SetupFilter | None = None
    lpf: SetupFilter | None = None
    dynamics: SetupDynamics | None = None  # None = no compressor or limiter


class SetupPlan(_Model):
    inputs: list[SetupInput]
    outputs: list[SetupOutput]
    input_links: list[list[int]] = Field(default_factory=list)
    output_links: list[list[int]] = Field(default_factory=list)


def _name(name: str) -> str:
    try:
        return c.validate_name(name, c.CHANNEL_NAME_LENGTH)
    except ValueError as exc:
        raise ParamError(f"channel name {name!r}: {exc}") from exc


def _masks(groups: list[list[int]], count: int, side: str) -> list[int]:
    try:
        return masks_for(normalise(groups, count), count)
    except LinkError as exc:
        raise ParamError(f"{side} links: {exc}") from exc


def _filter(flt: SetupFilter | None, profile: ProtocolProfile, default: int) -> tuple[int, int]:
    """(raw frequency, raw slope) of a crossover filter; None = bypassed at its default."""
    if flt is None:
        return default, 0
    if flt.slope >= len(profile.slopes):
        raise ParamError(f"slope must be in 1..{len(profile.slopes) - 1}")
    return c.freq_hz_to_raw(flt.freq_hz, profile), flt.slope


def _shelf_type(profile: ProtocolProfile) -> int:
    for index, name in enumerate(profile.peq_types):
        if name.lower().replace(" ", "") == "lowshelf":
            return index
    raise ParamError("this DSP has no low-shelf PEQ type")


def build_target(
    plan: SetupPlan, current: cm.RawConfig, profile: ProtocolProfile, preset_name: str
) -> cm.RawConfig:
    """The configuration the DSP should hold after the wizard (raises ``ParamError``)."""
    layout = cm.config_layout(current)
    if (len(plan.inputs), len(plan.outputs)) != (layout.inputs, layout.outputs):
        raise ParamError(
            f"the setup has {len(plan.inputs)} inputs and {len(plan.outputs)} outputs, "
            f"this DSP {layout.inputs} and {layout.outputs}"
        )
    base = cm.default_config(preset_name, layout)
    input_masks = _masks(plan.input_links, layout.inputs, "input")
    output_masks = _masks(plan.output_links, layout.outputs, "output")
    blank_x = cm.RawCrossover()

    inputs = []
    for i, (spec, raw_in) in enumerate(zip(plan.inputs, base.inputs, strict=True)):
        peq = list(raw_in.peq)
        if spec.low_shelf is not None:
            shelf = spec.low_shelf
            peq[0] = cm.RawPeqBand(
                gain=c.eq_gain_db_to_raw(shelf.gain_db),
                freq=c.freq_hz_to_raw(shelf.freq_hz, profile),
                q=c.q_to_raw(SHELF_Q, profile),
                type=_shelf_type(profile),
            )
        inputs.append(
            replace(
                raw_in,
                name=_name(spec.name),
                peq=tuple(peq),
                gain=c.gain_db_to_raw(spec.gain_db),
                mute=True,  # the user lets the sound in once the system is checked
                link=input_masks[i],
            )
        )

    outputs = []
    for i, (out, raw_out) in enumerate(zip(plan.outputs, base.outputs, strict=True)):
        if len(out.sources) != layout.inputs:
            raise ParamError(f"output {i + 1}: sources must list {layout.inputs} flags")
        hpf_freq, hpf_slope = _filter(out.hpf, profile, blank_x.hpf_freq)
        lpf_freq, lpf_slope = _filter(out.lpf, profile, blank_x.lpf_freq)
        compressor, limiter = raw_out.compressor, raw_out.limiter
        if out.dynamics is not None:
            attack = c.time_ms_to_raw(DYNAMICS_ATTACK_MS, *c.ATTACK_RANGE_MS)
            release = c.time_ms_to_raw(DYNAMICS_RELEASE_MS, *c.RELEASE_RANGE_MS)
            compressor = cm.RawCompressor(
                ratio=LIMIT_RATIO,
                attack=attack,
                release=release,
                knee=0,
                threshold=c.threshold_db_to_raw(out.dynamics.compressor_threshold_db),
            )
            limiter = cm.RawLimiter(
                attack=attack,
                release=release,
                threshold=c.threshold_db_to_raw(out.dynamics.limiter_threshold_db),
            )
        outputs.append(
            replace(
                raw_out,
                name=_name(out.name),
                matrix=sum(1 << n for n, on in enumerate(out.sources) if on),
                crosspoints=current.outputs[i].crosspoints,  # no verified request sets them
                crossover=cm.RawCrossover(hpf_freq, lpf_freq, hpf_slope, lpf_slope),
                compressor=compressor,
                limiter=limiter,
                gain=c.gain_db_to_raw(out.gain_db),
                phase=out.phase,
                mute=not out.used,
                link=output_masks[i],
            )
        )
    return replace(base, inputs=tuple(inputs), outputs=tuple(outputs), image=current.image)


__all__ = [
    "SetupDynamics",
    "SetupFilter",
    "SetupInput",
    "SetupOutput",
    "SetupPlan",
    "SetupShelf",
    "build_target",
]
