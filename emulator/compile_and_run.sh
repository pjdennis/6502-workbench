#!/usr/bin/env bash
# Usage: compile_and_run.sh --wendy|--michael <program.s> [emulator options]
# Assembles a program and runs it on the emulated board, uploaded through the board's ROM loader
# over the serial line as tools/upload/compile_and_upload_<board>.sh sends it to the real board:
#   --wendy    Wendy 2c: its boot ROM (firmware/boards/wendy2/upload_and_run_eeprom_wendy2c.s)
#              takes the program framed by wendy2_upload.py and runs it at $4000.
#   --michael  Michael: its ROM (firmware/boards/michael/michael_rom.s) takes it in upload format 3,
#              from S-records: it loads at its .org and starts at its start label, which it must have.
# The board runs in the browser (--web, at http://127.0.0.1:8080/; Ctrl-C stops it) unless the
# options say --live (this terminal; Ctrl-] quits on Michael) or --cycle-cap (headless; the exit
# report shows the LCD). Options after the program go to the emulator (e.g. --web-port 8081, --mhz 4).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
FW="$ROOT/firmware"

usage() { echo "Usage: $(basename "$0") --wendy|--michael <program.s> [emulator options]" >&2; exit 2; }

board= program=
options=()
mode=--web
for arg; do
  case "$arg" in
    --wendy|--michael) [ -z "$program" ] && [ -z "$board" ] || usage; board=${arg#--} ;;
    --web|--live|--cycle-cap) mode=; options+=("$arg") ;;
    *) if [ -z "$program" ] && [ -n "$board" ] && [ "${arg#-}" = "$arg" ]; then program=$arg
       else options+=("$arg"); fi ;;
  esac
done
[ -n "$board" ] && [ -n "$program" ] || usage
[ -f "$program" ] || { echo "$(basename "$0"): no such file: $program" >&2; exit 2; }

work="$(mktemp -d)"
vasm() { "$FW/vasm" -quiet -wdc02 -wfail -dotdir -ignore-mult-inc -esc "$@"; }

if [ "$board" = wendy ]; then
  rom="$FW/boards/wendy2/upload_and_run_eeprom_wendy2c.s"
  vasm -Fbin -o "$work/program.bin" "$program"
  python3 "$HERE/wendy2_upload.py" "$work/program.bin" -o "$work/program.upload"
  machine=wendy2c
else
  rom="$FW/boards/michael/michael_rom.s"
  vasm -Fsrec -s19 -exec=start -o "$work/program.s19" "$program"
  python3 "$ROOT/tools/upload/upload_frame.py" "$work/program.s19" "$work/program.upload"
  machine=michael
fi
vasm -Fbin -o "$work/rom.bin" "$rom" >/dev/null

exec "$HERE/emulator.out" "$work/rom.bin" --machine "$machine" --serial-input "$work/program.upload" \
  $mode "${options[@]}"
