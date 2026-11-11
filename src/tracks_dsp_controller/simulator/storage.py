"""Preset persistence for the standalone simulator (``tracks-dsp-sim --state-dir DIR``).

A real DSP 408 keeps its presets across power cycles. With a state directory, the simulator
does the same: every stored user preset is written as ``U01.bin`` … ``U20.bin`` (the 1448-byte
config blob, the same format as ``tracks-dsp-controller probe dump-config``), and the active
slot goes to ``active``. On start-up, the files found there are loaded back.

Edits that were not stored are lost on restart. Whether the real device keeps them is not known.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from tracks_dsp_controller.protocol import config_map as cm
from tracks_dsp_controller.protocol import preset_file as pf
from tracks_dsp_controller.protocol.profile import load_profile
from tracks_dsp_controller.simulator.device import SimulatedDevice

log = logging.getLogger(__name__)

ACTIVE_FILE = "active"


def preset_file(directory: Path, slot: int) -> Path:
    return directory / f"U{slot:02d}.bin"


def read_config(path: Path, layout: cm.ConfigLayout = cm.LAYOUT_408) -> cm.RawConfig:
    """Read a config dump (``probe dump-config`` output or a stored preset file), or a preset
    file of the official editor (.prs)."""
    data = path.read_bytes()
    if data.startswith(pf.MAGIC):
        try:
            model = pf.file_model(data)
            if cm.layout_for(load_profile(model=model)) != layout:
                raise pf.PresetFileError(f"preset file for a DSP {model}, not this model")
            data = pf.decode_preset_file(data, model, layout)
        except pf.PresetFileError as exc:
            raise cm.ConfigError(f"{path}: {exc}") from exc
    return cm.decode_config(data, layout)


def _write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


class PresetStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._saved: dict[int, bytes] = {}

    def load_into(self, device: SimulatedDevice) -> int:
        """Load the saved presets and active slot into ``device``. Returns the preset count."""
        self.directory.mkdir(parents=True, exist_ok=True)
        loaded = 0
        for slot in range(1, device.profile.preset_count + 1):
            path = preset_file(self.directory, slot)
            if not path.exists():
                continue
            try:
                config = read_config(path, cm.layout_for(device.profile))
            except (OSError, cm.ConfigError) as exc:
                log.warning("ignoring %s: %s", path, exc)
                continue
            device.set_preset(slot, config)
            self._saved[slot] = config.image
            loaded += 1
        active = self.directory / ACTIVE_FILE
        if active.exists():
            text = active.read_text().strip()
            if text.isdigit() and int(text) <= device.profile.preset_count:
                device.load(int(text))
            else:
                log.warning("ignoring %s: not a slot number", active)
        return loaded

    def save(self, device: SimulatedDevice) -> None:
        """Write the presets that changed since the last save, and the active slot."""
        self.directory.mkdir(parents=True, exist_ok=True)
        for slot in range(1, device.profile.preset_count + 1):
            blob = cm.encode_config(device.presets[slot])
            if self._saved.get(slot) == blob or device.presets[slot] is device.presets[0]:
                continue  # unchanged, or never written (still the factory preset)
            _write_atomic(preset_file(self.directory, slot), blob)
            self._saved[slot] = blob
        _write_atomic(self.directory / ACTIVE_FILE, f"{device.active_slot}\n".encode())
