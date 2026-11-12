"""Option defaults from environment variables.

``tracks-dsp-controller`` reads ``TDSP_<NAME>``; its ``sim`` command reads ``TDSP_SIM_<NAME>``.
"""

from __future__ import annotations

import os


class Env:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix

    def get(self, name: str, default: str | None = None) -> str | None:
        return os.environ.get(self.prefix + name, default)

    def float(self, name: str, default: float) -> float:
        value = self.get(name)
        return float(value) if value else default

    def flag(self, name: str) -> bool:
        return (self.get(name) or "").lower() in ("1", "true", "yes", "on")
