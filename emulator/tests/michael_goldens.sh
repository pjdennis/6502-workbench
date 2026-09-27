#!/bin/sh
# Michael end-to-end golden-LCD tests.
#
# For each (payload, expected-substring, cycle-cap) row:
#   1. Build the payload .s.
#   2. Run it on the Michael machine, loaded straight into RAM at the
#      board's PROGRAM_LOAD_ADDRESS.
#   3. Confirm the expected substring appears in the final-LCD-frame
#      stderr summary.
#
# Skips with a warning (exit 0) if vasm6502_oldstyle is not on PATH.

set -eu

REPO_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
EMU="$REPO_ROOT/emulator/emulator.out"
FW="$REPO_ROOT/firmware"
OUT="${OUT_DIR:-/tmp/michael-goldens}"
VASM=vasm6502_oldstyle

mkdir -p "$OUT"

if ! command -v "$VASM" >/dev/null 2>&1; then
    echo "michael_goldens: SKIP ($VASM not on PATH)"
    exit 0
fi

if [ ! -x "$EMU" ]; then
    echo "michael_goldens: FAIL ($EMU not built; run 'make' first)"
    exit 1
fi

LOAD=$(sed -n 's/^PROGRAM_LOAD_ADDRESS *= *\$\([0-9a-fA-F]*\).*/\1/p' \
    "$FW/boards/michael/base_config_v2.inc")

run_case() {
    name=$1
    payload_src=$2
    cycle_cap=$3
    expected=$4

    echo "michael_goldens: case $name"
    log="$OUT/$name.vasm.log"
    if ! "$FW/vasm" -wdc02 -wfail -Fbin -dotdir -ignore-mult-inc -esc \
            -o "$OUT/$name.bin" "$FW/programs/michael/$payload_src" >"$log" 2>&1; then
        echo "michael_goldens: vasm failed assembling $payload_src (log: $log)"
        cat "$log"
        exit 1
    fi

    "$EMU" "$OUT/$name.bin" \
        --machine michael \
        --load "$LOAD" \
        --cycle-cap "$cycle_cap" \
        >"$OUT/$name.stdout" 2>"$OUT/$name.stderr" || true

    if ! grep -qF "$expected" "$OUT/$name.stderr"; then
        echo "michael_goldens: FAIL $name -- expected '$expected' not in final LCD frame"
        echo "  stderr was:"
        sed 's/^/    /' "$OUT/$name.stderr"
        exit 1
    fi
    echo "  PASS $name (matched '$expected')"
}

run_case hello hello_michael_ram.s 2000000 "|Hi I'm Michael!     |"

echo "michael_goldens: all cases passed"
