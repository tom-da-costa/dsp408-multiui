#!/usr/bin/env sh
# Cross-build the Windows executables on Linux, inside the tobix/pywine image (Python under Wine):
# the web application and the simulated DSP (same name with tracks-dsp-sim instead of tracks-dsp-controller).
# Usually run through packaging/windows.Dockerfile:
#   docker buildx build -f packaging/windows.Dockerfile -o dist .
set -eu
NAME="${1:-tracks-dsp-controller-windows-amd64}"
SIM_NAME="$(echo "$NAME" | sed 's/^tracks-dsp-controller/tracks-dsp-sim/')"
[ "$SIM_NAME" != "$NAME" ] || SIM_NAME="$NAME-sim"
PROFILES="src/tracks_dsp_controller/protocol/profiles;tracks_dsp_controller/protocol/profiles"
wine python -m pip install --quiet --no-warn-script-location "pyinstaller==6.11.1" .
wine pyinstaller --noconfirm --clean --onefile --name "$NAME" \
  --paths src \
  --collect-submodules uvicorn \
  --collect-submodules websockets \
  --collect-submodules tracks_dsp_controller \
  --add-data "src/tracks_dsp_controller/web;tracks_dsp_controller/web" \
  --add-data "$PROFILES" \
  --copy-metadata tracks-dsp-controller \
  packaging/entry.py
wine pyinstaller --noconfirm --clean --onefile --name "$SIM_NAME" \
  --paths src \
  --collect-submodules tracks_dsp_controller.simulator \
  --collect-submodules tracks_dsp_controller.protocol \
  --add-data "$PROFILES" \
  --copy-metadata tracks-dsp-controller \
  packaging/entry_sim.py
