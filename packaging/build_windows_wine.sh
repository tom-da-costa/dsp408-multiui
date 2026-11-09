#!/usr/bin/env sh
# Cross-build the Windows executables on Linux, inside the tobix/pywine image (Python under Wine):
# the web application and the simulated DSP (same name with dsp408-sim instead of dsp408-multiui).
# Usually run through packaging/windows.Dockerfile:
#   docker buildx build -f packaging/windows.Dockerfile -o dist .
set -eu
NAME="${1:-dsp408-multiui-windows-amd64}"
SIM_NAME="$(echo "$NAME" | sed 's/^dsp408-multiui/dsp408-sim/')"
[ "$SIM_NAME" != "$NAME" ] || SIM_NAME="$NAME-sim"
PROFILES="src/dsp408_multiui/protocol/profiles;dsp408_multiui/protocol/profiles"
wine python -m pip install --quiet --no-warn-script-location "pyinstaller==6.11.1" .
wine pyinstaller --noconfirm --clean --onefile --name "$NAME" \
  --paths src \
  --collect-submodules uvicorn \
  --collect-submodules websockets \
  --collect-submodules dsp408_multiui \
  --add-data "src/dsp408_multiui/web;dsp408_multiui/web" \
  --add-data "$PROFILES" \
  --copy-metadata dsp408-multiui \
  packaging/entry.py
wine pyinstaller --noconfirm --clean --onefile --name "$SIM_NAME" \
  --paths src \
  --collect-submodules dsp408_multiui.simulator \
  --collect-submodules dsp408_multiui.protocol \
  --add-data "$PROFILES" \
  --copy-metadata dsp408-multiui \
  packaging/entry_sim.py
