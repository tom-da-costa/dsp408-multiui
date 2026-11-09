"""PyInstaller entry point for the standalone simulator executable (dsp408-sim)."""

from dsp408_multiui.simulator.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
