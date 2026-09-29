#!/bin/bash
# Like wendy2_run.sh, but also mounts a host directory as the simulated SPI
# "disk" (--disk) so the program can use the $F800+ file-I/O OS calls.
#
# Usage: wendy2_disk_run.sh demos/foo.p8 DISKDIR [cyclecap] [--rom ROM.bin]
#   DISKDIR must already contain whatever files the program/monitor reads.
#   --rom overrides the boot ROM (default: the serial-upload boot ROM, which
#   uploads the compiled program to $4000 and runs it).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
PROG8="$HERE/.."; REPO="$PROG8/../.."
JAR="${PROG8C:-/tmp/prog8c.jar}"
EMU="$REPO/emulator/emulator.out"
UPLOAD="$REPO/emulator/wendy2_upload.py"
BOOT_SRC="$REPO/firmware/boards/wendy2/upload_and_run_eeprom_wendy2c.s"

SRC="$1"; DISK="$2"; CAP="${3:-3000000}"
[ -n "$SRC" ] && [ -n "$DISK" ] || { echo "usage: $0 demos/foo.p8 DISKDIR [cap]"; exit 2; }
ROM=""
shift 3 2>/dev/null || shift $#
while [ $# -gt 0 ]; do case "$1" in --rom) ROM="$2"; shift 2;; *) shift;; esac; done

base="$(basename "${SRC%.p8}")"
OUT="$HERE/out/$base"; mkdir -p "$OUT"

( cd "$HERE" && java -jar "$JAR" -target wendy2.properties -out "$OUT" "$(realpath "$SRC")" ) \
    >"$OUT/compile.log" 2>&1 || { echo "COMPILE FAILED"; tail -25 "$OUT/compile.log"; exit 1; }
python3 "$UPLOAD" "$OUT/$base.bin" -o "$OUT/$base.framed" >/dev/null

if [ -z "$ROM" ]; then
    ROM="$HERE/out/wendy2c_boot.bin"
    [ -f "$ROM" ] || ( cd "$REPO" && firmware/vasm -wdc02 -wfail -Fbin -dotdir \
            -ignore-mult-inc -esc -o "$ROM" "$BOOT_SRC" ) >/dev/null
fi

"$EMU" "$ROM" --machine wendy2c --serial-input "$OUT/$base.framed" \
    --disk "$(realpath "$DISK")" --cycle-cap "$CAP" 2>&1
