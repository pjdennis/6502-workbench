#!/bin/bash
# Run every regression check the repo has. The reorganization must keep all of
# these green (docs/REORGANIZATION_PLAN.md, rule R1). CI runs the same steps.
#
#   tools/check_all.sh [firmware|asm1|asm2|emulator|prog8]...   (default: all)
#
# Needs on PATH: vasm6502_oldstyle (CI uses the version recorded in firmware/manifest.txt --
# see .github/workflows/ci.yml; another version that gives identical binaries only warns),
# gcc, g++, make, python3, hexdump.
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

asm1() {
  # asmtestgen.sh always exits 0 and, without hexdump, "passes" by diffing two
  # empty dumps -- so require hexdump and check the printed verdicts instead.
  command -v hexdump >/dev/null || { echo "hexdump not on PATH"; return 1; }
  local log
  log="$(cd toolchain/asm1 && ./asmtestgen.sh </dev/null 2>&1)"
  echo "$log" | tail -3
  echo "$log" | grep -qx 'OK' && echo "$log" | grep -qx 'Assembled'
}

asm2() {
  (cd toolchain/asm2 && ./verify.sh)
}

emulator() {
  # Emulator C tests + wendy2c goldens; must run from the repo root. Clean
  # first so stale test binaries cannot mask a broken build rule.
  make -s clean && make test
}

prog8() {
  make -C toolchain/prog8 test
}

suites=("$@")
[ ${#suites[@]} -eq 0 ] && suites=(firmware asm1 asm2 emulator prog8)

for s in "${suites[@]}"; do
  echo "=== $s ==="
  if "$s"; then echo "=== $s: PASS ==="; else echo "=== $s: FAIL ==="; failed+=("$s"); fi
done

if [ ${#failed[@]} -gt 0 ]; then
  echo "FAILED: ${failed[*]}"
  exit 1
fi
echo "ALL PASSED: ${suites[*]}"
