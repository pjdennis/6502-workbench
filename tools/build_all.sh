#!/bin/bash
# Build the main tools, so the scripts that use them work (e.g. editor/bin/editor.sh,
# editor-michael.sh and editor-michael-upload.sh). About 30 seconds.
#
#   tools/build_all.sh [emulator|asm|editor]...   (default: all, in this order)
#
#   emulator  emulator/emulator.out
#   asm       the asm chain 00..17, each stage built by the one before and tested
#             (asmtestgen.sh); 17/out/asm.out is the live assembler
#   editor    the editor's stable builds, editor/out/editor_stable.out and
#             editor_terminal_stable.out, which its tests write once they pass
#
# Each step's output is shown only if it fails. Needs gcc, make and python3; warns about
# what the firmware and upload scripts need besides: vasm6502_oldstyle and Python pyserial.
# tools/check_all.sh runs every test suite.

set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

command -v vasm6502_oldstyle >/dev/null ||
  echo "warning: vasm6502_oldstyle not on PATH (needed to build firmware and the Michael ROM)"
python3 -c "import serial" 2>/dev/null ||
  echo "warning: Python pyserial missing (needed by tools/upload/transfer.py)"

failed=()

emulator() {
  make -s
}

asm() {
  (cd asm && ./asmtestgen.sh)
}

editor() {
  python3 editor/tests/editor_tests.py -q
}

steps=("$@")
[ ${#steps[@]} -eq 0 ] && steps=(emulator asm editor)

for s in "${steps[@]}"; do
  echo "=== $s ==="
  if log="$("$s" </dev/null 2>&1)"; then
    echo "=== $s: OK ==="
  else
    echo "$log"
    echo "=== $s: FAIL ==="
    failed+=("$s")
  fi
done

if [ ${#failed[@]} -gt 0 ]; then
  echo "FAILED: ${failed[*]}"
  exit 1
fi
echo "ALL BUILT: ${steps[*]}"
