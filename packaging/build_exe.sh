#!/usr/bin/env sh
# Build the standalone executable for the current platform into dist/.
# Usage: packaging/build_exe.sh <output-name>     (run from the repository root)
# Needs Python >= 3.12 and uv; on Windows, run it under Git Bash or adapt the commands.
set -eu
NAME="${1:-dsp408-multiui}"
SEP=":"
case "$(uname -s 2>/dev/null || echo Windows)" in
  MINGW*|MSYS*|CYGWIN*|Windows) SEP=";" ;;
esac
uv sync --frozen --no-dev
uv run --frozen --no-dev --with "pyinstaller==6.11.1" pyinstaller \
  --noconfirm --clean --onefile \
  --name "$NAME" \
  --paths src \
  --collect-submodules uvicorn \
  --collect-submodules websockets \
  --collect-submodules dsp408_multiui \
  --add-data "src/dsp408_multiui/web${SEP}dsp408_multiui/web" \
  --add-data "src/dsp408_multiui/protocol/profiles${SEP}dsp408_multiui/protocol/profiles" \
  --copy-metadata dsp408-multiui \
  packaging/entry.py
