"""Activity-based exclusive write lock (docs/ARCHITECTURE.md §4, multi-client rules).

The owner keeps the lock as long as it is active. Every owner activity (a write, a preset or
lock action, a UI interaction reported with an ``activity`` message) restarts the idle timer.
After ``idle_timeout`` seconds without activity, or on release/logout, the lock is free again.
A disconnect does not release it by itself: the idle timeout does.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LockState:
    owner_id: str | None
    owner_name: str | None
    idle_expires_at: float | None  # in the LockManager's clock


type LockListener = Callable[[LockState], None]


class LockManager:
    def __init__(self, idle_timeout: float, clock: Callable[[], float] = time.monotonic) -> None:
        if idle_timeout <= 0:
            raise ValueError("idle_timeout must be > 0")
        self.idle_timeout = idle_timeout
        self.clock = clock
        self._owner_id: str | None = None
        self._owner_name: str | None = None
        self._last_activity = 0.0
        self._listeners: list[LockListener] = []

    def on_change(self, listener: LockListener) -> None:
        self._listeners.append(listener)

    def _emit(self) -> None:
        state = self.state()
        for listener in list(self._listeners):
            listener(state)

    def state(self) -> LockState:
        if self._owner_id is None:
            return LockState(None, None, None)
        return LockState(self._owner_id, self._owner_name, self._last_activity + self.idle_timeout)

    def expire(self) -> bool:
        """Release the lock if the owner has been idle too long. Returns True if released."""
        if self._owner_id is not None and self.clock() - self._last_activity >= self.idle_timeout:
            self._owner_id = self._owner_name = None
            self._emit()
            return True
        return False

    def acquire(self, client_id: str, name: str) -> bool:
        self.expire()
        if self._owner_id not in (None, client_id):
            return False
        changed = self._owner_id != client_id or self._owner_name != name
        self._owner_id, self._owner_name = client_id, name
        self._last_activity = self.clock()
        if changed:
            self._emit()
        return True

    def release(self, client_id: str) -> bool:
        if self._owner_id != client_id:
            return False
        self._owner_id = self._owner_name = None
        self._emit()
        return True

    def touch(self, client_id: str) -> None:
        """Record activity from a client; only the owner's activity matters."""
        if self._owner_id == client_id:
            self._last_activity = self.clock()

    def can_write(self, client_id: str) -> bool:
        self.expire()
        return self._owner_id in (None, client_id)

    def rename(self, client_id: str, name: str) -> None:
        if self._owner_id == client_id:
            self._owner_name = name
            self._emit()
