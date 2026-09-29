#!/usr/bin/env bash
# Usage: compile_and_upload.sh [--srec] [transfer.py options] <program.s>
# Assembles a program for a board's RAM loader, then sends it with transfer.py and the given
# options. Options may come before or after the program; give their values with = (--port=DEVICE).
# It assembles to a.out in the current directory, or with --srec to S-records in a.s19 (for upload
# format 3: its addresses, and its start address from its start label, which it must have). The
# compile_and_upload_<board>.sh scripts call this with each board's settings.
HERE="$(cd "$(dirname "$0")" && pwd)"

options=()
program=
format=(-Fbin)
out=a.out
for arg in "$@"; do
  case "$arg" in
    --srec) format=(-Fsrec -s19 -exec=start); out=a.s19 ;;
    -*) options+=("$arg") ;;
    *)  [ -z "$program" ] || { echo "Only one program may be given" >&2; exit 2; }
        program="$arg" ;;
  esac
done
[ -n "$program" ] || { echo "Usage: $(basename "$0") [--noreset] [transfer.py options] <program.s>" >&2; exit 2; }

"$HERE/../../firmware/vasm" -quiet -wdc02 -wfail "${format[@]}" -dotdir -ignore-mult-inc -esc -o "$out" "$program" &&
  python3 "$HERE/transfer.py" "${options[@]}" "$out"
