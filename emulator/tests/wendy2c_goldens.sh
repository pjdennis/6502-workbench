#!/bin/sh
# wendy2c end-to-end golden-LCD tests (phase 16).
#
# For each (payload, expected-substring, cycle-cap) row:
#   1. Build the upload-and-run boot ROM (upload_and_run_eeprom_wendy2c.s).
#   2. Build the payload .s.
#   3. Frame it with wendy2_upload.py.
#   4. Run the wendy2c emulator with the framed bytes pre-queued into
#      the SERIAL_USB chip and --cycle-cap set.
#   5. Confirm the expected substring appears in the final-LCD-frame
#      stderr summary.
#
# Skips with a warning (exit 0) if vasm6502_oldstyle is not on PATH,
# matching the Harte runner's pattern -- this keeps the test target
# safe to wire into CI on hosts without vasm.

set -eu

REPO_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
EMU="$REPO_ROOT/emulator/emulator.out"
FW="$REPO_ROOT/firmware"
OUT="${OUT_DIR:-/tmp/wendy2c-goldens}"
VASM=vasm6502_oldstyle

mkdir -p "$OUT"

if ! command -v "$VASM" >/dev/null 2>&1; then
    echo "wendy2c_goldens: SKIP ($VASM not on PATH)"
    exit 0
fi

if [ ! -x "$EMU" ]; then
    echo "wendy2c_goldens: FAIL ($EMU not built; run 'make' first)"
    exit 1
fi

run_vasm() {
    out=$1
    src=$2
    log="$OUT/$(basename "$src").vasm.log"
    if ! "$FW/vasm" -wdc02 -wfail -Fbin -dotdir -ignore-mult-inc -esc \
            -o "$out" "$src" >"$log" 2>&1; then
        echo "wendy2c_goldens: vasm failed assembling $src (log: $log)"
        cat "$log"
        exit 1
    fi
}

# Boot ROM is shared across all cases -- assemble once.
echo "wendy2c_goldens: building boot ROM"
run_vasm "$OUT/boot.bin" "$FW/boards/wendy2/upload_and_run_eeprom_wendy2c.s"

# Each case: payload_src  cycle_cap  expected_substring
# cycle_cap is in oscillator ticks (--cycle-cap units).
run_case() {
    name=$1
    payload_src=$2
    cycle_cap=$3
    expected=$4

    echo "wendy2c_goldens: case $name"
    run_vasm "$OUT/$name.bin" "$FW/programs/wendy2/$payload_src"
    python3 "$REPO_ROOT/emulator/wendy2_upload.py" \
        "$OUT/$name.bin" -o "$OUT/$name.framed" >"$OUT/$name.upload.log"

    "$EMU" "$OUT/boot.bin" \
        --machine wendy2c \
        --serial-input "$OUT/$name.framed" \
        --cycle-cap "$cycle_cap" \
        >"$OUT/$name.stdout" 2>"$OUT/$name.stderr" || true

    if ! grep -q "$expected" "$OUT/$name.stderr"; then
        echo "wendy2c_goldens: FAIL $name -- expected '$expected' not in final LCD frame"
        echo "  stderr was:"
        sed 's/^/    /' "$OUT/$name.stderr"
        exit 1
    fi
    echo "  PASS $name (matched '$expected')"
}

# 3M osc ticks is comfortably above the ~1.5M minimum for the upload
# pipeline + first LCD frame; see demo_wendy2c.sh.
run_case hello_4000   hello_ram_4000_wendy2c.s 3000000 "Hi! I'm Wendy 2."
run_case led_test     wendy2c_led_test.s        3000000 "LED Flashing..."
# Multitasking exercises the WAI-wakes-on-masked-IRQ behavior: the
# scheduler's IRQ handler runs WAI with I set, and only wakes when the
# next T2 underflow asserts the IRQ line. Need ~150M osc ticks for the
# counters to step past zero. 'X' is the always-on "chase" character
# in the rightmost column of the busy_loop counter.
run_case multitasking multitasking_test_wendy2c.s 150000000 " X "
# Memory-map verification against the PLD. Each test prints its number
# then its results two to a cell as CGRAM tick/cross glyphs, wrapping
# onto line 2, which ends in " OK" only if all pass. Matched in the
# lcd-hex dump since the text frame shows every glyph as '?'. Glyph
# codes: 01 = tick over blank, 03 = tick over tick. Two cases because
# run_case matches a single-line substring.
run_case verification_l1 verification_wendy2c.s 20000000 "|31 03 03 03 03 03 03 03 01 32 03 03 03 03 03 33|"
run_case verification_l2 verification_wendy2c.s 20000000 "|03 01 34 03 35 03 03 36 03 03 03 37 03 20 4f 4b|"

echo "wendy2c_goldens: all PASS"
