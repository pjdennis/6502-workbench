#!/bin/bash
# The editor's whole check: the screen model, the console and direct-io builds, and the Michael
# board build. Needs the emulator and asm18 built (tools/build_all.sh asm) and vasm6502_oldstyle.

set -e
cd "$(dirname "$0")/.."

[ -f asm/18/out/asm.out ] || { echo "asm18 not built: run tools/build_all.sh asm"; exit 1; }

python3 editor/tests/ansi_screen.py &&
  editor/tests/editor_tests.py -q &&
  editor/tests/editor_tests.py -q --direct-io &&
  editor/tests/michael_tests.py
