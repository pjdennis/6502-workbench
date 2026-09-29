#!/bin/bash
# Boot the wendy2c MONITOR ROM with a simulated SPI disk and let it autoexec.
#
# Compiles demos/<name>.p8 for the wendy2 target, stages a temp disk holding
# the compiled program (named <name>) plus an 'autoexec' that names it, builds
# the monitor ROM, and runs the emulator with --rom monitor + --disk. No
# serial upload -- the program is loaded from disk by the monitor over the
# $F800+ file-I/O OS calls. Prints the final LCD frame.
#
# Usage: wendy2_monitor_run.sh demos/foo.p8 [cyclecap] [extra_disk_file ...]
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
PROG8="$HERE/.."; REPO="$PROG8/../.."
JAR="${PROG8C:-/tmp/prog8c.jar}"
EMU="$REPO/emulator/emulator.out"
MON_SRC="$REPO/firmware/boards/wendy2/wendy2c_monitor.s"

SRC="$1"; CAP="${2:-4000000}"
[ -n "$SRC" ] || { echo "usage: $0 demos/foo.p8 [cap] [extra disk files...]"; exit 2; }
shift 2 2>/dev/null || shift $#

base="$(basename "${SRC%.p8}")"
OUT="$HERE/out/$base"; mkdir -p "$OUT"

# compile the program
( cd "$HERE" && java -jar "$JAR" -target wendy2.properties -out "$OUT" "$(realpath "$SRC")" ) \
    >"$OUT/compile.log" 2>&1 || { echo "COMPILE FAILED"; tail -25 "$OUT/compile.log"; exit 1; }

# build the monitor ROM (cached)
MON="$HERE/out/wendy2c_monitor.bin"
[ -f "$MON" ] || ( cd "$REPO" && firmware/vasm -wdc02 -wfail -Fbin -dotdir \
        -ignore-mult-inc -esc -o "$MON" "$MON_SRC" ) >/dev/null

# stage a temp disk: program named <base>, autoexec naming it, + extras
DISK="$(mktemp -d)"
cp "$OUT/$base.bin" "$DISK/$base"
printf '%s\n' "$base" > "$DISK/autoexec"
for f in "$@"; do cp "$f" "$DISK/"; done

"$EMU" "$MON" --machine wendy2c --disk "$DISK" --cycle-cap "$CAP" 2>&1
rm -rf "$DISK"
