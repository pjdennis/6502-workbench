#!/bin/sh
# Run the editor on the emulated Michael board: its 20x4 LCD drawn in this
# terminal, and this terminal's keys typed on its PS/2 keyboard. Ctrl-]
# quits. Extra arguments go to the emulator (e.g. --mhz 4).
set -e
cd "$(dirname "$0")"
image="$(mktemp -d)/editor_michael.image"
python3 editor/michael_image.py "$image"
exec ../../emulator/emulator.out "$image" --machine michael --load 0400 --live "$@"
