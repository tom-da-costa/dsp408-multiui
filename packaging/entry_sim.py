"""PyInstaller entry point for the standalone simulator executable (dsp408-sim)."""

from tracks_dsp_controller.simulator.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
