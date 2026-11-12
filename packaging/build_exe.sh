#!/usr/bin/env sh
# Build the standalone executable for the current platform into dist/<name>. It holds the web
# application and the simulated DSP (`<name> sim`).
# Usage: packaging/build_exe.sh <output-name>     (run from the repository root)
# Needs Python >= 3.12 and uv; on Windows, run it under Git Bash or adapt the commands.
set -eu
NAME="${1:-tracks-dsp-controller}"
SEP=":"
case "$(uname -s 2>/dev/null || echo Windows)" in
  MINGW*|MSYS*|CYGWIN*|Windows) SEP=";" ;;
esac
PROFILES="src/tracks_dsp_controller/protocol/profiles${SEP}tracks_dsp_controller/protocol/profiles"
uv sync --frozen --no-dev
pyinstaller() {
  uv run --frozen --no-dev --with "pyinstaller==6.11.1" pyinstaller \
    --noconfirm --clean --onefile --paths src --copy-metadata tracks-dsp-controller "$@"
}
pyinstaller --name "$NAME" \
  --collect-submodules uvicorn \
  --collect-submodules websockets \
  --collect-submodules tracks_dsp_controller \
  --add-data "src/tracks_dsp_controller/web${SEP}tracks_dsp_controller/web" \
  --add-data "$PROFILES" \
  packaging/entry.py
