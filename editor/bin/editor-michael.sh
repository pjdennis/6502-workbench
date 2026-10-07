#!/bin/sh
# Run the editor on the emulated Michael board: boots the Michael ROM, uploads the editor through
# its loader over the serial line, and draws the 20x4 LCD in this terminal, with this terminal's
# keys typed on its PS/2 keyboard. Ctrl-] quits. Extra arguments go to the emulator (e.g. --mhz 4);
# with --web the board is in the browser instead (http://127.0.0.1:8080/; Ctrl-C quits). With --graphic
# (first) the editor runs on the graphic display (the FPGA's text mode, 20x20) through a launcher that
# selects it, as on the board; only --web shows that display.
set -e
cd "$(dirname "$0")/../.."
graphic=False
if [ "$1" = --graphic ]; then graphic=True; shift; fi
work="$(mktemp -d)"
python3 - "$work" "$graphic" <<'PYTHON'
import sys
from pathlib import Path
sys.path.insert(0, "editor")
import michael_image
work = Path(sys.argv[1])
michael_image.build_rom(work / "michael_rom.bin")
michael_image.write_upload(michael_image.build(work / "editor_michael.bin"), work / "editor.upload", graphic=sys.argv[2] == "True")
PYTHON
mode=--live
for arg; do [ "$arg" = --web ] && mode=; done
exec emulator/emulator.out "$work/michael_rom.bin" --machine michael \
  --serial-input "$work/editor.upload" $mode "$@"
