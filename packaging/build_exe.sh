#!/usr/bin/env sh
# Build the standalone executables for the current platform into dist/:
#   <name>                 the web application (dsp408-multiui)
#   <name with dsp408-sim> the simulated DSP (dsp408-sim), e.g. dsp408-sim-v1.0.0-linux-amd64
# Usage: packaging/build_exe.sh <output-name>     (run from the repository root)
# Needs Python >= 3.12 and uv; on Windows, run it under Git Bash or adapt the commands.
set -eu
NAME="${1:-dsp408-multiui}"
SIM_NAME="$(echo "$NAME" | sed 's/^dsp408-multiui/dsp408-sim/')"
[ "$SIM_NAME" != "$NAME" ] || SIM_NAME="$NAME-sim"
SEP=":"
case "$(uname -s 2>/dev/null || echo Windows)" in
  MINGW*|MSYS*|CYGWIN*|Windows) SEP=";" ;;
esac
PROFILES="src/dsp408_multiui/protocol/profiles${SEP}dsp408_multiui/protocol/profiles"
uv sync --frozen --no-dev
pyinstaller() {
  uv run --frozen --no-dev --with "pyinstaller==6.11.1" pyinstaller \
    --noconfirm --clean --onefile --paths src --copy-metadata dsp408-multiui "$@"
}
pyinstaller --name "$NAME" \
  --collect-submodules uvicorn \
  --collect-submodules websockets \
  --collect-submodules dsp408_multiui \
  --add-data "src/dsp408_multiui/web${SEP}dsp408_multiui/web" \
  --add-data "$PROFILES" \
  packaging/entry.py
pyinstaller --name "$SIM_NAME" \
  --collect-submodules dsp408_multiui.simulator \
  --collect-submodules dsp408_multiui.protocol \
  --add-data "$PROFILES" \
  packaging/entry_sim.py
