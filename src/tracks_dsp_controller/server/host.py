"""Host role: one client may disconnect the others and block new logins (ARCHITECTURE §7).

The role is taken and released explicitly, like Control. Blocking new logins belongs to the
host: it ends with the role, so that the server is never left locked with nobody able to
unlock it. The role ends when its holder releases it, logs out, or stays away (no connection
open) for ``absent_timeout`` seconds; a reload or a short network loss keeps it.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HostState:
    owner_id: str | None
    owner_name: str | None
    logins_blocked: bool


type HostListener = Callable[[HostState], None]


class HostManager:
    def __init__(self, absent_timeout: float, clock: Callable[[], float] = time.monotonic) -> None:
        if absent_timeout <= 0:
            raise ValueError("absent_timeout must be > 0")
        self.absent_timeout = absent_timeout
        self.clock = clock
        self._owner_id: str | None = None
        self._owner_name: str | None = None
        self._blocked = False
        self._absent_since: float | None = None
        self._listeners: list[HostListener] = []

    def on_change(self, listener: HostListener) -> None:
        self._listeners.append(listener)

    def _emit(self) -> None:
        state = self.state()
        for listener in list(self._listeners):
            listener(state)

    def state(self) -> HostState:
        return HostState(self._owner_id, self._owner_name, self._blocked)

    @property
    def logins_blocked(self) -> bool:
        return self._blocked

    def is_host(self, client_id: str) -> bool:
        return self._owner_id is not None and self._owner_id == client_id

    def acquire(self, client_id: str, name: str) -> bool:
        """Take the role; False if another client has it."""
        if self._owner_id not in (None, client_id):
            return False
        if self._owner_id is None:
            self._owner_id, self._owner_name = client_id, name
            self._absent_since = None
            self._emit()
        return True

    def release(self, client_id: str) -> bool:
        """Give the role up (new logins are allowed again). False if not the host."""
        if not self.is_host(client_id):
            return False
        self._owner_id = self._owner_name = None
        self._blocked = False
        self._absent_since = None
        self._emit()
        return True

    def block_logins(self, client_id: str, blocked: bool) -> bool:
        """Block or allow new logins. False if ``client_id`` is not the host."""
        if not self.is_host(client_id):
            return False
        if self._blocked != blocked:
            self._blocked = blocked
            self._emit()
        return True

    def presence(self, client_id: str, connected: bool) -> None:
        """Whether the host has at least one connection open (the hub tells)."""
        if not self.is_host(client_id):
            return
        self._absent_since = None if connected else self.clock()

    def expire(self) -> bool:
        """Release the role of a host away for too long. Returns True if released."""
        if self._owner_id is None or self._absent_since is None:
            return False
        if self.clock() - self._absent_since < self.absent_timeout:
            return False
        return self.release(self._owner_id)
