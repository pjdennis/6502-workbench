#!/bin/sh
# wendy2c end-to-end serial-link upload smoke test.
#
# Same flow as wendy2c_goldens.sh but exercises the live --serial-link
# socket transport (the path wendy2c_emu_upload.py drives) instead of
# the pre-queued --serial-input. Verifies that:
#   1. The boot ROM listens on the link.
#   2. The Python upload script delivers the framed payload bit-by-bit.
#   3. The on-target checksum + JMP-to-RAM succeeds.
#   4. The final LCD frame matches the expected string.
#
# Skips (exit 0) if vasm6502_oldstyle is not installed, matching the
# golden test's pattern.

set -eu

REPO_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
EMU="$REPO_ROOT/emulator/emulator.out"
FW="$REPO_ROOT/firmware"
OUT="${OUT_DIR:-/tmp/wendy2c-serial-link-test}"
VASM=vasm6502_oldstyle

mkdir -p "$OUT"

if ! command -v "$VASM" >/dev/null 2>&1; then
    echo "wendy2c_serial_link: SKIP ($VASM not on PATH)"
    exit 0
fi

if [ ! -x "$EMU" ]; then
    echo "wendy2c_serial_link: FAIL ($EMU not built; run 'make' first)"
    exit 1
fi

run_vasm() {
    out=$1
    src=$2
    log="$OUT/$(basename "$src").vasm.log"
    if ! "$FW/vasm" -wdc02 -wfail -Fbin -dotdir -ignore-mult-inc -esc \
            -o "$out" "$src" >"$log" 2>&1; then
        echo "wendy2c_serial_link: vasm failed assembling $src (log: $log)"
        cat "$log"
        exit 1
    fi
}

echo "wendy2c_serial_link: building boot ROM"
run_vasm "$OUT/boot.bin" "$FW/boards/wendy2/upload_and_run_eeprom_wendy2c.s"

run_case() {
    name=$1
    payload_src=$2
    cycle_cap=$3
    expected=$4

    echo "wendy2c_serial_link: case $name"
    run_vasm "$OUT/$name.bin" "$FW/programs/wendy2/$payload_src"

    sock="$OUT/$name.sock"
    rm -f "$sock"

    "$EMU" "$OUT/boot.bin" \
        --machine wendy2c \
        --serial-link "$sock" \
        --cycle-cap "$cycle_cap" \
        --exit-report \
        >"$OUT/$name.stdout" 2>"$OUT/$name.stderr" &
    emu_pid=$!

    # Give the emulator a moment to start listening before connecting.
    # The Python client retries for several seconds, so this is just to
    # avoid the worst case wait.
    sleep 0.2

    if ! python3 "$REPO_ROOT/emulator/wendy2c_emu_upload.py" \
            "$sock" "$OUT/$name.bin" \
            >"$OUT/$name.upload.log" 2>&1; then
        echo "wendy2c_serial_link: FAIL $name -- upload failed"
        cat "$OUT/$name.upload.log"
        kill "$emu_pid" 2>/dev/null || true
        exit 1
    fi

    # Wait for emulator to hit its cycle cap and print the final LCD.
    wait "$emu_pid" || true

    if ! grep -q "$expected" "$OUT/$name.stderr"; then
        echo "wendy2c_serial_link: FAIL $name -- expected '$expected' not in final LCD frame"
        echo "  stderr was:"
        sed 's/^/    /' "$OUT/$name.stderr"
        exit 1
    fi
    echo "  PASS $name (matched '$expected')"
}

# 100M osc ticks ~= 5 seconds emulated, plenty for a 50ms reset +
# 50ms init + ~25ms upload + a few frames of post-boot execution.
run_case hello_4000 hello_ram_4000_wendy2c.s 100000000 "Hi! I'm Wendy 2."

echo "wendy2c_serial_link: all PASS"
