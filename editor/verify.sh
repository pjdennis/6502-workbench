#!/bin/bash
# The editor's whole check: the screen model, the console and direct-io builds, and the Michael
# board build. Needs the emulator and asm17 built (tools/build_all.sh asm) and vasm6502_oldstyle.

set -e
cd "$(dirname "$0")/.."

[ -x asm/17/out/asm.out ] || { echo "asm17 not built: run tools/build_all.sh asm"; exit 1; }

python3 editor/tests/ansi_screen.py &&
  editor/tests/editor_tests.py -q &&
  editor/tests/editor_tests.py -q --direct-io &&
  editor/tests/michael_tests.py
