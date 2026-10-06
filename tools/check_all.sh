#!/bin/bash
# Run the repo's regression checks. The reorganization must keep all of
# these green (docs/REORGANIZATION_PLAN.md, rule R1). CI runs the same steps.
#
#   tools/check_all.sh [firmware|asm|editor|emulator|prog8]...   (default: all but prog8)
#
# prog8 is slow and rarely affected by current work, so it runs only when named;
# CI still runs it on every push.
#
# Needs on PATH: vasm6502_oldstyle (CI uses the version recorded in firmware/manifest.txt --
# see .github/workflows/ci.yml; another version that gives identical binaries only warns),
# gcc, g++, make, python3.
# The emulator suite also uses Python playwright; the prog8 suite uses 64tass and
# java + $PROG8C (default /tmp/prog8c.jar). Those tests SKIP when the tool is missing.
# The slow opt-in suites (Harte, P1_WENDY_SELFHOST, MERGE_SORT_FULL_N) are not run.

set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

command -v vasm6502_oldstyle >/dev/null || { echo "vasm6502_oldstyle not on PATH"; exit 1; }

failed=()

firmware() {
  python3 -m unittest discover -s tools/tests &&
    python3 tools/firmware_manifest.py check --include-list firmware/include-dirs
}

asm() {
  (cd asm && ./verify.sh)
}

# The editor and the emulator's terminal tests run on the assembler; build it once if it is missing.
need_asm() {
  [ -f asm/17/out/asm.out ] || (cd asm && ./asmtestgen.sh)
}

editor() {
  need_asm && editor/verify.sh
}

emulator() {
  # Emulator C tests + wendy2c goldens; must run from the repo root. Clean
  # first so stale test binaries cannot mask a broken build rule.
  make -s clean && make test && need_asm &&
    emulator/tests/terminal_tests.py && emulator/tests/emulator_tests.py
}

prog8() {
  make -C prog8 test
}

suites=("$@")
[ ${#suites[@]} -eq 0 ] && suites=(firmware asm editor emulator)

for s in "${suites[@]}"; do
  echo "=== $s ==="
  if "$s"; then echo "=== $s: PASS ==="; else echo "=== $s: FAIL ==="; failed+=("$s"); fi
done

if [ ${#failed[@]} -gt 0 ]; then
  echo "FAILED: ${failed[*]}"
  exit 1
fi
echo "ALL PASSED: ${suites[*]}"
