"""Command-line entry point.

Sub-commands are added phase by phase (see docs/PLAN.md). For now only ``--version`` works.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from dsp408_multiui import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dsp408-multiui",
        description="Multi-client web controller for the t.racks DSP 408.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0
