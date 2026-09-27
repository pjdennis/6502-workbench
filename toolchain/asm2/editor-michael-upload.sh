#!/bin/sh
# Upload the editor to the Michael board, where it runs on the 20x4 LCD and the PS/2 keyboard:
# builds it with its services (editor/michael_image.py) and sends it with
# tools/upload/upload_michael_big.sh, which resets the board first. Options go to transfer.py
# (e.g. --port=/dev/ttyUSB0). Needs the emulator and asm17 built (make; ./asmtestgen.sh).
set -e
cd "$(dirname "$0")"
image="$(mktemp -d)/editor_michael.image"
python3 editor/michael_image.py "$image"
exec ../../tools/upload/upload_michael_big.sh "$@" "$image"
