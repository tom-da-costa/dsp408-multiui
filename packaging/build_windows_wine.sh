#!/usr/bin/env sh
# Cross-build the Windows executable on Linux, inside the tobix/pywine image (Python under Wine):
# the web application, with the simulated DSP as its `sim` command.
# Usually run through packaging/windows.Dockerfile:
#   docker buildx build -f packaging/windows.Dockerfile -o dist .
set -eu
NAME="${1:-tracks-dsp-controller-windows-amd64}"
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
