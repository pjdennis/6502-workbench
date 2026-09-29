#!/bin/bash
# Compile a .p8 with upstream prog8c for the custom 'wendy2' target, then
# boot+upload+run it on the wendy2c emulator and print the final LCD frame.
#
# Mirrors the proven `p8c --run` path (toolchain/prog8/p8c/__main__.py):
#   prog8c -target wendy2.properties  ->  RAW binary loaded at $4000
#   wendy2_upload.py                  ->  serial-upload framing
#   emulator + wendy2c boot ROM + --serial-input
#
# Prereqs: /tmp/prog8c.jar, 64tass on PATH, vasm6502_oldstyle on PATH,
#          the emulator built. Usage: wendy2_run.sh demos/foo.p8 [cyclecap]
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"          # .../toolchain/prog8/upstream
PROG8="$HERE/.."                                # .../toolchain/prog8
REPO="$PROG8/../.."                            # repo root
JAR="${PROG8C:-/tmp/prog8c.jar}"
EMU="$REPO/emulator/emulator.out"
UPLOAD="$REPO/emulator/wendy2_upload.py"
BOOT_SRC="$REPO/firmware/boards/wendy2/upload_and_run_eeprom_wendy2c.s"
CAP="${2:-3000000}"

SRC="$1"; [ -n "$SRC" ] || { echo "usage: $0 demos/foo.p8 [cyclecap]"; exit 2; }
base="$(basename "${SRC%.p8}")"
OUT="$HERE/out/$base"; mkdir -p "$OUT"

# 1. compile (cwd = upstream so 'library = ./libraries/wendy2' resolves)
( cd "$HERE" && java -jar "$JAR" -target wendy2.properties -out "$OUT" "$(realpath "$SRC")" ) \
    >"$OUT/compile.log" 2>&1 || { echo "COMPILE FAILED"; tail -25 "$OUT/compile.log"; exit 1; }

# 2. frame for serial upload
python3 "$UPLOAD" "$OUT/$base.bin" -o "$OUT/$base.framed" >/dev/null

# 3. build the wendy2c boot ROM once (cwd = REPO so the .include paths resolve)
BOOT="$HERE/out/wendy2c_boot.bin"
[ -f "$BOOT" ] || ( cd "$REPO" && firmware/vasm -wdc02 -wfail -Fbin -dotdir \
        -ignore-mult-inc -esc -o "$BOOT" "$BOOT_SRC" ) >/dev/null

# 4. run; the emulator prints the final LCD frame on stderr
"$EMU" "$BOOT" --machine wendy2c --serial-input "$OUT/$base.framed" --cycle-cap "$CAP" 2>&1
