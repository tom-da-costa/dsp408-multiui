"""Shared-code login, in-memory sessions and a login rate limit (docs/ARCHITECTURE.md §8)."""

from __future__ import annotations

import hmac
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field

SESSION_COOKIE = "dsp408_session"
MAX_FAILURES = 5
COOLDOWN_S = 30.0
NAME_MAX = 32


class LoginError(Exception):
    """Wrong code."""


class RateLimitedError(Exception):
    """Too many failures from this address."""

    def __init__(self, retry_after: float) -> None:
        super().__init__(f"too many attempts, retry in {retry_after:.0f} s")
        self.retry_after = retry_after


@dataclass(slots=True)
class ClientSession:
    token: str
    client_id: str
    name: str
    created: float


@dataclass(slots=True)
class _Attempts:
    failures: int = 0
    blocked_until: float = 0.0


def clean_name(name: str | None, fallback: str) -> str:
    """Printable, trimmed display name."""
    text = "".join(ch for ch in (name or "") if ch.isprintable()).strip()[:NAME_MAX]
    return text or fallback


@dataclass
class AuthManager:
    pin: str
    clock: Callable[[], float] = time.monotonic
    _sessions: dict[str, ClientSession] = field(default_factory=dict)
    _attempts: dict[str, _Attempts] = field(default_factory=dict)
    _counter: int = 0

    def login(self, pin: str, name: str | None, address: str) -> ClientSession:
        now = self.clock()
        attempts = self._attempts.setdefault(address, _Attempts())
        if attempts.blocked_until > now:
            raise RateLimitedError(attempts.blocked_until - now)
        if not hmac.compare_digest(pin.encode(), self.pin.encode()):
            attempts.failures += 1
            if attempts.failures >= MAX_FAILURES:
                attempts.failures = 0
                attempts.blocked_until = now + COOLDOWN_S
            raise LoginError("wrong code")
        self._attempts.pop(address, None)
        self._counter += 1
        client_id = f"c{self._counter}-{secrets.token_hex(3)}"
        session = ClientSession(
            token=secrets.token_urlsafe(32),
            client_id=client_id,
            name=clean_name(name, f"Client {self._counter}"),
            created=now,
        )
        self._sessions[session.token] = session
        return session

    def get(self, token: str | None) -> ClientSession | None:
        return self._sessions.get(token) if token else None

    def rename(self, token: str, name: str) -> ClientSession | None:
        session = self._sessions.get(token)
        if session is not None:
            session.name = clean_name(name, session.name)
        return session

    def logout(self, token: str | None) -> ClientSession | None:
        return self._sessions.pop(token, None) if token else None
