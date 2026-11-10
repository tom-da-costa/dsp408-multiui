"""PyInstaller entry point for the standalone simulator executable (tracks-dsp-sim)."""

from tracks_dsp_controller.simulator.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
