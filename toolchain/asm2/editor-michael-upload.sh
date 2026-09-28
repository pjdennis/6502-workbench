#!/bin/sh
# Upload the editor to the Michael board, whose ROM (firmware/boards/michael/michael_rom.s) runs it
# on the 20x4 LCD and the PS/2 keyboard: builds it (editor/michael_image.py) and sends it in upload
# format 3, which resets the board first. Options go to transfer.py (e.g. --port=/dev/ttyUSB0).
# Needs the emulator and asm17 built (make; ./asmtestgen.sh).
set -e
cd "$(dirname "$0")"
editor="$(mktemp -d)/editor_michael.bin"
python3 editor/michael_image.py "$editor"
exec python3 ../../tools/upload/transfer.py --baudrate=57600 --format=3 --load-address=0200 "$@" "$editor"
