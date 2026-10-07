#!/bin/sh
# emulator/compile_and_run.sh end to end: a program assembled, uploaded
# through each board's ROM loader as the real board's upload script would
# send it, and run (headless under --cycle-cap, with the exit report that
# shows the LCD), its usage errors, and that it serves the board's web page
# unless told otherwise.
#
# Skips with a warning (exit 0) if vasm6502_oldstyle is not on PATH.

set -eu

REPO_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
RUN="$REPO_ROOT/emulator/compile_and_run.sh"
OUT="${OUT_DIR:-/tmp/compile-and-run-test}"

mkdir -p "$OUT"

if ! command -v vasm6502_oldstyle >/dev/null 2>&1; then
    echo "compile_and_run_test: SKIP (vasm6502_oldstyle not on PATH)"
    exit 0
fi

fail() {
    echo "compile_and_run_test: FAIL $1"
    sed 's/^/    /' "$OUT/$2.out"
    exit 1
}

# run_case NAME EXPECTED-STATUS EXPECTED-SUBSTRING ARGS...: the script's
# exit status and a substring of its output (stdout and stderr together).
run_case() {
    name=$1 status=$2 expected=$3
    shift 3
    actual=0
    "$RUN" "$@" >"$OUT/$name.out" 2>&1 || actual=$?
    [ "$actual" -eq "$status" ] || fail "$name -- exit status $actual, want $status" "$name"
    grep -qF -- "$expected" "$OUT/$name.out" || fail "$name -- '$expected' not in its output" "$name"
    echo "  PASS $name (matched '$expected')"
}

W=firmware/programs/wendy2
M=firmware/programs/michael

run_case wendy 0 "Hi! I'm Wendy 2." --wendy "$REPO_ROOT/$W/hello_ram_4000_wendy2c.s" --cycle-cap 3000000
run_case michael 0 "|Hi I'm Michael!     |" --michael "$REPO_ROOT/$M/hello_michael_ram.s" --cycle-cap 4000000
# Relative paths are the caller's, not the script's directory's.
(cd "$REPO_ROOT/$W" && run_case relative 0 "Hi! I'm Wendy 2." --wendy hello_ram_4000_wendy2c.s --cycle-cap 3000000)
run_case no-board 2 "Usage:" "$REPO_ROOT/$W/hello_ram_4000_wendy2c.s"
run_case no-program 2 "Usage:" --michael
run_case missing 2 "no such file" --wendy "$OUT/nonexistent.s"
run_case vasm-error 1 "error" --michael "$REPO_ROOT/emulator/tests/compile_and_run_test.sh"
# Michael's loader starts a program at its start label, which it must have.
printf '  .org $2000\nmain:\n  stp\n' >"$OUT/no_start.s"
run_case no-start 1 "<start>" --michael "$OUT/no_start.s" --cycle-cap 1000

# By default the board is in the browser: the server says where, and runs
# until stopped; then it says nothing more.
for board in wendy michael; do
    name=default-web-$board
    if [ $board = wendy ]; then program=$W/hello_ram_4000_wendy2c.s; else program=$M/hello_michael_ram.s; fi
    "$RUN" --$board "$REPO_ROOT/$program" --web-port 0 >"$OUT/$name.out" 2>&1 &
    pid=$!
    tries=0
    until grep -q "listening on http://" "$OUT/$name.out"; do
        tries=$((tries + 1))
        if [ "$tries" -gt 50 ] || ! kill -0 "$pid" 2>/dev/null; then
            kill -INT "$pid" 2>/dev/null || true
            fail "$name -- the web server never said it was listening" "$name"
        fi
        sleep 0.1
    done
    kill -INT "$pid"
    wait "$pid" || true
    [ "$(wc -l <"$OUT/$name.out")" -eq 1 ] || fail "$name -- more than the listening line" "$name"
    echo "  PASS $name (the server listened, and stopped quietly)"
done

echo "compile_and_run_test: all PASS"
