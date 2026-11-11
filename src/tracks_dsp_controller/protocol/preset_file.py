"""Preset files (``.prs``) of the official t.racks editor, and how to load one into a DSP.

File format (docs/PROTOCOL.md §7.1), read from a file exported by the editor for a DSP 408::

    0    16   header: "***" + the identity without its space, cut to 10 characters + "***"
              ("***DSP408V010***" for "DSP408 V0104P")
    16   ...  the config blob (§7) from its byte 2 on: preset name (14 bytes, space padded),
              input and output records, and the trailer's first 4 + 2 × channels bytes
              (mute masks and per-band PEQ bypass masks)
    end  2    "\\r\\n"

The marker (blob bytes 0–1) and the end of the trailer (the whole-PEQ bypass masks and the
unknown bytes) are not in the file. A DSP 408 file is 1452 bytes. The 206 and 204 files are
expected to follow the same rule with their own layout (not seen yet).

No request writes a whole config at once, so a preset file is loaded with the parameter writes
verified on hardware (``plan_import``): mute every output, unlink, write each parameter that
differs, link again, then set the outputs' mutes last, so the system never plays half-loaded.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace

from tracks_dsp_controller.protocol import commands as cmd
from tracks_dsp_controller.protocol import config_map as cm
from tracks_dsp_controller.protocol.codecs import CHANNEL_NAME_LENGTH, decode_name
from tracks_dsp_controller.protocol.links import link_requests
from tracks_dsp_controller.protocol.profile import ProtocolProfile, detect_model

FILE_SUFFIX = ".prs"
HEADER_SIZE = 16
MAGIC = b"***"
IDENTITY_LENGTH = HEADER_SIZE - 2 * len(MAGIC)  # 10
FILE_END = b"\r\n"
NAME_START = 2  # the file starts at the blob's preset name: the marker is left out


class PresetFileError(ValueError):
    """The file is not a preset file for this device, or holds values the DSP refuses."""


def stored_end(layout: cm.ConfigLayout) -> int:
    """Blob offset where the file's copy of the config stops (408: 1436 of 1448)."""
    return layout.band_bypass_base + 2 * layout.channels


def file_size(layout: cm.ConfigLayout) -> int:
    """Size of a preset file for ``layout`` (408: 1452 bytes)."""
    return HEADER_SIZE + stored_end(layout) - NAME_START + len(FILE_END)


def header_for(identity: str) -> bytes:
    """File header for a device identity: "DSP408 V0104P" → ``***DSP408V010***``."""
    text = identity.replace(" ", "").encode("ascii", errors="replace")[:IDENTITY_LENGTH]
    return MAGIC + text.ljust(IDENTITY_LENGTH, b" ") + MAGIC


def file_model(data: bytes) -> str:
    """Model key ("408", "206", "204") named by a preset file's header."""
    header = data[:HEADER_SIZE]
    if len(header) < HEADER_SIZE or not (header.startswith(MAGIC) and header.endswith(MAGIC)):
        raise PresetFileError("not a t.racks preset file (.prs)")
    identity = header[len(MAGIC) : -len(MAGIC)].decode("latin-1")
    model = detect_model(identity)
    if model is None:
        raise PresetFileError(f"preset file for an unsupported device: {identity.strip()!r}")
    return model


def encode_preset_file(blob: bytes, layout: cm.ConfigLayout, identity: str) -> bytes:
    """Preset file of a config blob, as the official editor writes it."""
    if len(blob) != layout.size:
        raise cm.ConfigError(f"config blob is {len(blob)} bytes, expected {layout.size}")
    return header_for(identity) + blob[NAME_START : stored_end(layout)] + FILE_END


def decode_preset_file(data: bytes, model: str, layout: cm.ConfigLayout) -> bytes:
    """Config blob of a preset file for a DSP ``model`` with ``layout``.

    The bytes the file does not hold are filled in: marker ``ff ff`` (a user preset), whole-PEQ
    bypass off, unknown trailer bytes 0. The final line break is optional.
    """
    found = file_model(data)
    if found != model:
        raise PresetFileError(f"this preset is for a DSP {found}, not a DSP {model}")
    if data.endswith(FILE_END) and len(data) == file_size(layout):
        data = data[: -len(FILE_END)]
    expected = file_size(layout) - len(FILE_END)
    if len(data) != expected:
        raise PresetFileError(
            f"preset file is {len(data)} bytes, a DSP {model} preset is {file_size(layout)}"
        )
    blob = bytearray(layout.size)
    blob[0:NAME_START] = cm.MARKER_MODIFIED.to_bytes(2, "big")
    blob[NAME_START : stored_end(layout)] = data[HEADER_SIZE:]
    return bytes(blob)


def preset_name(blob: bytes) -> str:
    return decode_name(blob[NAME_START : cm.HEADER_SIZE])


def ascii_name(name: str, length: int) -> str:
    """A name the DSP accepts: printable ASCII ("é" → "e", others "?"), ``length`` at most."""

    def plain(char: str) -> str:
        text = unicodedata.normalize("NFKD", char).encode("ascii", errors="ignore").decode()
        return "".join(c for c in text if 0x20 <= ord(c) < 0x7F) or "?"

    return "".join(map(plain, unicodedata.normalize("NFC", name)))[:length].rstrip()


_UNSAFE_FILENAME = re.compile(r'[\x00-\x1f\x7f/\\:*?"<>|]+')


def file_name(name: str) -> str:
    """File name for an exported preset: its name, made safe for every OS, plus ``.prs``."""
    safe = _UNSAFE_FILENAME.sub("_", name).strip(" .")
    return (safe or "preset") + FILE_SUFFIX


# --- loading a preset into the DSP ----------------------------------------------------------
@dataclass(frozen=True, slots=True)
class ImportPlan:
    requests: tuple[cmd.Request, ...]
    expected: bytes  # the config the DSP should hold afterwards (name and marker aside)
    notes: tuple[str, ...]  # what cannot be loaded exactly


def _label(index: int, is_input: bool) -> str:
    return f"In {chr(ord('A') + index)}" if is_input else f"Out {index + 1}"


def _channel_writes(
    ch: int,
    cur: cm.RawInput | cm.RawOutput,
    tgt: cm.RawInput | cm.RawOutput,
) -> list[cmd.Request]:
    """Writes that turn channel ``cur`` into ``tgt`` (name, mute and links aside)."""
    out: list[cmd.Request] = []
    if isinstance(cur, cm.RawInput) and isinstance(tgt, cm.RawInput):
        if cur.gate != tgt.gate:
            g = tgt.gate
            out.append(cmd.SetGate(ch, g.attack, g.release, g.hold, g.threshold))
        out += [
            cmd.SetGeqBand(ch, n, raw)
            for n, (old, raw) in enumerate(zip(cur.geq, tgt.geq, strict=True))
            if old != raw
        ]
    if isinstance(cur, cm.RawOutput) and isinstance(tgt, cm.RawOutput):
        if cur.matrix != tgt.matrix:
            out.append(cmd.SetMatrix(ch, tgt.matrix))
        if cur.compressor != tgt.compressor:
            k = tgt.compressor
            out.append(cmd.SetCompressor(ch, k.ratio, k.attack, k.release, k.knee, k.threshold))
        if cur.limiter != tgt.limiter:
            lim = tgt.limiter
            out.append(cmd.SetLimiter(ch, lim.attack, lim.release, lim.reserved, lim.threshold))
    for n, (old, band) in enumerate(zip(cur.peq, tgt.peq, strict=True)):
        if old != band:
            out.append(cmd.SetPeqBand(ch, n, band.gain, band.freq, band.q, band.type, band.bypass))
    if cur.peq_bypass != tgt.peq_bypass:
        out.append(cmd.SetPeqBypass(ch, tgt.peq_bypass))
    x, y = cur.crossover, tgt.crossover
    if (x.hpf_freq, x.hpf_slope) != (y.hpf_freq, y.hpf_slope):
        out.append(cmd.SetHighPass(ch, y.hpf_freq, y.hpf_slope))
    if (x.lpf_freq, x.lpf_slope) != (y.lpf_freq, y.lpf_slope):
        out.append(cmd.SetLowPass(ch, y.lpf_freq, y.lpf_slope))
    if cur.gain != tgt.gain:
        out.append(cmd.SetGain(ch, tgt.gain))
    if cur.phase != tgt.phase:
        out.append(cmd.SetPhase(ch, tgt.phase))
    if cur.delay != tgt.delay:
        out.append(cmd.SetDelay(ch, tgt.delay))
    return out


def _groups(masks: list[int]) -> list[tuple[int, ...]]:
    return sorted({g for i in range(len(masks)) if len(g := cm.link_group(masks, i)) > 1})


def plan_import(
    current: cm.RawConfig, target: cm.RawConfig, profile: ProtocolProfile
) -> ImportPlan:
    """Requests that load ``target`` into a DSP whose live config is ``current``.

    Every request is checked against ``profile`` before anything is sent: a file holding a value
    the DSP refuses raises ``PresetFileError``.
    """
    layout = cm.config_layout(current)
    if cm.config_layout(target) != layout:
        raise PresetFileError("the preset does not have this DSP's channels")
    notes: list[str] = []
    first_output = layout.inputs

    # Names: the DSP takes printable ASCII only.
    def name(index: int, is_input: bool, wanted: str, now: str) -> str:
        if wanted == now:
            return wanted
        plain = ascii_name(wanted, CHANNEL_NAME_LENGTH)
        if plain != wanted:
            notes.append(f"{_label(index, is_input)}: name {wanted!r} written as {plain!r}")
        return plain

    inputs = tuple(
        replace(t, name=name(i, True, t.name, c.name))
        for i, (c, t) in enumerate(zip(current.inputs, target.inputs, strict=True))
    )
    outputs = []
    for i, (c, t) in enumerate(zip(current.outputs, target.outputs, strict=True)):
        if c.crosspoints != t.crosspoints:  # no verified request sets them
            notes.append(f"{_label(i, False)}: matrix levels not loaded (kept as they are)")
        outputs.append(replace(t, name=name(i, False, t.name, c.name), crosspoints=c.crosspoints))
    target = replace(target, inputs=inputs, outputs=tuple(outputs))

    requests: list[cmd.Request] = []
    # 1. Silence: every output muted until the end.
    requests += [
        cmd.SetMute(first_output + i, True) for i, c in enumerate(current.outputs) if not c.mute
    ]
    # 2. Unlink, so that each write reaches one channel only.
    for side, first in ((current.inputs, 0), (current.outputs, first_output)):
        for group in _groups([c.link for c in side]):
            requests += [cmd.SetLink(first + m, 1 << m) for m in group]
    if any(isinstance(r, cmd.SetLink) for r in requests):
        requests.append(cmd.Activate())
    # 3. Every parameter that differs.
    for i, (ci, ti) in enumerate(zip(current.inputs, target.inputs, strict=True)):
        if ci.name != ti.name:
            requests.append(cmd.SetChannelName(i, ti.name))
        requests += _channel_writes(i, ci, ti)
        if ci.mute != ti.mute:
            requests.append(cmd.SetMute(i, ti.mute))
    for i, (co, to) in enumerate(zip(current.outputs, target.outputs, strict=True)):
        if co.name != to.name:
            requests.append(cmd.SetChannelName(first_output + i, to.name))
        requests += _channel_writes(first_output + i, co, to)
    # 4. Links, the way the editor sets them (2a + 3b + 12).
    for side, first in ((target.inputs, 0), (target.outputs, first_output)):
        own = [1 << i for i in range(len(side))]
        requests += link_requests(own, _groups([c.link for c in side]), first)
    # 5. The outputs the preset does not mute back on.
    requests += [
        cmd.SetMute(first_output + i, False) for i, t in enumerate(target.outputs) if not t.mute
    ]
    requests.append(cmd.Activate())

    for request in requests:
        try:
            request.encode(profile)
        except cmd.CommandError as exc:
            raise PresetFileError(f"the preset holds a value the DSP refuses: {exc}") from exc
    expected = cm.encode_config(replace(target, image=current.image))
    return ImportPlan(tuple(requests), expected, tuple(notes))


# Fields the import does not write: the file and the DSP may differ there.
_NOT_COMPARED = ("marker", "preset_name", ".unknown", "trailer[", ".link")


def mismatches(expected: bytes, actual: bytes, layout: cm.ConfigLayout) -> list[str]:
    """Fields where the DSP's config differs from what an import expected."""
    fields = dict.fromkeys(name for *_, name in cm.diff_blobs(expected, actual, layout))
    differing = [f for f in fields if not any(skip in f for skip in _NOT_COMPARED)]
    exp, act = cm.decode_config(expected, layout), cm.decode_config(actual, layout)
    for side in ("inputs", "outputs"):
        groups = (
            _groups([c.link for c in getattr(exp, side)]),
            _groups([c.link for c in getattr(act, side)]),
        )
        if groups[0] != groups[1]:
            differing.append(f"{side}.links")
    return differing


__all__ = [
    "FILE_SUFFIX",
    "ImportPlan",
    "PresetFileError",
    "ascii_name",
    "decode_preset_file",
    "encode_preset_file",
    "file_model",
    "file_name",
    "file_size",
    "mismatches",
    "plan_import",
    "preset_name",
]
