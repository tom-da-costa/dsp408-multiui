#!/usr/bin/env sh
# Cross-build the Windows executable on Linux, inside the tobix/pywine image (Python under Wine).
# Usually run through packaging/windows.Dockerfile:
#   docker buildx build -f packaging/windows.Dockerfile -o dist .
set -eu
NAME="${1:-dsp408-multiui-windows-amd64}"
wine python -m pip install --quiet --no-warn-script-location "pyinstaller==6.11.1" .
wine pyinstaller --noconfirm --clean --onefile --name "$NAME" \
  --paths src \
  --collect-submodules uvicorn \
  --collect-submodules websockets \
  --collect-submodules dsp408_multiui \
  --add-data "src/dsp408_multiui/web;dsp408_multiui/web" \
  --add-data "src/dsp408_multiui/protocol/profiles;dsp408_multiui/protocol/profiles" \
  --copy-metadata dsp408-multiui \
  packaging/entry.py
