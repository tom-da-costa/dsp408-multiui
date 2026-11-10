#!/usr/bin/env sh
# Build the standalone executables for the current platform into dist/:
#   <name>                 the web application (tracks-dsp-controller)
#   <name with tracks-dsp-sim> the simulated DSP (tracks-dsp-sim), e.g. tracks-dsp-sim-v1.0.0-linux-amd64
# Usage: packaging/build_exe.sh <output-name>     (run from the repository root)
# Needs Python >= 3.12 and uv; on Windows, run it under Git Bash or adapt the commands.
set -eu
NAME="${1:-tracks-dsp-controller}"
SIM_NAME="$(echo "$NAME" | sed 's/^tracks-dsp-controller/tracks-dsp-sim/')"
[ "$SIM_NAME" != "$NAME" ] || SIM_NAME="$NAME-sim"
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
pyinstaller --name "$SIM_NAME" \
  --collect-submodules tracks_dsp_controller.simulator \
  --collect-submodules tracks_dsp_controller.protocol \
  --add-data "$PROFILES" \
  packaging/entry_sim.py
