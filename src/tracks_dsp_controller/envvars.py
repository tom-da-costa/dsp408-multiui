"""Option defaults from environment variables, with the names of earlier versions as a fallback.

``tracks-dsp-controller`` reads ``TDSP_<NAME>`` and ``tracks-dsp-sim`` reads ``TDSP_SIM_<NAME>``.
Before 0.8 they were ``DSP408_<NAME>`` and ``TRACKS_DSP_SIM_<NAME>``: those are still read when
the new name is not set, and :meth:`Env.warn_legacy` logs which ones should be renamed.
"""

from __future__ import annotations

import logging
import os


class Env:
    def __init__(self, prefix: str, legacy_prefix: str) -> None:
        self.prefix = prefix
        self.legacy_prefix = legacy_prefix
        self.legacy_used: set[str] = set()  # names read under the legacy prefix

    def get(self, name: str, default: str | None = None) -> str | None:
        value = os.environ.get(self.prefix + name)
        if value is None:
            value = os.environ.get(self.legacy_prefix + name)
            if value is not None:
                self.legacy_used.add(name)
        return default if value is None else value

    def float(self, name: str, default: float) -> float:
        value = self.get(name)
        return float(value) if value else default

    def flag(self, name: str) -> bool:
        return (self.get(name) or "").lower() in ("1", "true", "yes", "on")

    def warn_legacy(self, log: logging.Logger) -> None:
        for name in sorted(self.legacy_used):
            log.warning(
                "%s%s is deprecated: rename it to %s%s",
                self.legacy_prefix,
                name,
                self.prefix,
                name,
            )
