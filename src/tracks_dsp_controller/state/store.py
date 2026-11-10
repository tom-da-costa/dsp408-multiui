"""Authoritative in-memory mirror of the device state (no database)."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from tracks_dsp_controller.state.models import DeviceState

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Snapshot:
    rev: int
    state: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Patch:
    rev: int
    changes: tuple[tuple[str, Any], ...]
    origin: str  # client id, or "device"


type StoreEvent = Snapshot | Patch
type Listener = Callable[[StoreEvent], None]


def get_path(model: BaseModel, path: str) -> Any:
    target: Any = model
    for part in path.split("."):
        target = target[int(part)] if isinstance(target, list) else getattr(target, part)
    return target


def set_path(model: BaseModel, path: str, value: Any) -> None:
    """Set a value by dotted path, validating it against the model."""
    *parents, last = path.split(".")
    target: Any = model
    for part in parents:
        target = target[int(part)] if isinstance(target, list) else getattr(target, part)
    if isinstance(target, list):
        index = int(last)
        current = target[index]
        target[index] = (
            type(current).model_validate(value) if isinstance(current, BaseModel) else value
        )
        return
    current = getattr(target, last)
    if isinstance(current, BaseModel):
        value = type(current).model_validate(value)
    setattr(target, last, value)


class StateStore:
    def __init__(self) -> None:
        self._state = DeviceState()
        self._rev = 0
        self._listeners: list[Listener] = []

    @property
    def rev(self) -> int:
        return self._rev

    @property
    def state(self) -> DeviceState:
        """The live state. Treat it as read-only; change it through ``replace``/``apply``."""
        return self._state

    def snapshot(self) -> Snapshot:
        return Snapshot(self._rev, self._state.model_dump(mode="json"))

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def _emit(self, event: StoreEvent) -> None:
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:  # a broken listener must not break the device session
                log.exception("store listener failed")

    def replace(self, state: DeviceState) -> Snapshot:
        """Install a full new state (after a config read)."""
        self._state = state
        self._rev += 1
        snap = self.snapshot()
        self._emit(snap)
        return snap

    def apply(self, changes: Iterable[tuple[str, Any]], origin: str) -> Patch:
        changes = tuple(changes)
        for path, value in changes:
            set_path(self._state, path, value)
        self._rev += 1
        patch = Patch(self._rev, changes, origin)
        self._emit(patch)
        return patch
