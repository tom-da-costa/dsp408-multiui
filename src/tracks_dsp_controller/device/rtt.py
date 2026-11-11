"""Adaptive command timeout from the measured round trips (RFC 6298, as TCP does).

A fixed timeout either fails on a slow link (Wi-Fi bridge, VPN, congested LAN: every command
times out, the session flaps offline) or makes a dead link slow to detect. The timeout follows
the smoothed round trip plus four times its variation, kept between a floor (the profile's
``command_timeout_s``, right for a DSP on the LAN) and a ceiling (``command_timeout_max_s``).
A timeout doubles it until the next answer (exponential backoff), so a link that suddenly got
slower is caught up with in a request or two.
"""

from __future__ import annotations

ALPHA = 1 / 8  # weight of a new sample in the smoothed round trip
BETA = 1 / 4  # weight of a new sample in the variation


class RttEstimator:
    def __init__(self, floor: float, ceiling: float) -> None:
        if not 0 < floor <= ceiling:
            raise ValueError("need 0 < floor <= ceiling")
        self.floor = floor
        self.ceiling = ceiling
        self.srtt: float | None = None
        self.rttvar = 0.0
        self._backoff = 1.0

    def sample(self, rtt: float) -> None:
        """A measured round trip (an answer to a request sent once, no ambiguity)."""
        rtt = max(0.0, rtt)
        if self.srtt is None:
            self.srtt, self.rttvar = rtt, rtt / 2
        else:
            self.rttvar = (1 - BETA) * self.rttvar + BETA * abs(self.srtt - rtt)
            self.srtt = (1 - ALPHA) * self.srtt + ALPHA * rtt
        self._backoff = 1.0

    def timed_out(self) -> None:
        """No answer in time: wait longer next time, until an answer comes."""
        self._backoff = min(self._backoff * 2, self.ceiling / self.floor)

    @property
    def timeout(self) -> float:
        base = self.floor if self.srtt is None else self.srtt + 4 * self.rttvar
        return min(self.ceiling, max(self.floor, base) * self._backoff)
