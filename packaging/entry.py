"""PyInstaller entry point for the standalone executable."""

from tracks_dsp_controller.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
