#!/usr/bin/env bash
# Usage: compile_and_upload.sh [--hex] [transfer.py options] <program.s>
# Assembles a program for a board's RAM loader, then sends it with transfer.py and the given
# options. Options may come before or after the program; give their values with = (--port=DEVICE).
# It assembles to a.out in the current directory, or with --hex to Intel HEX in a.hex (for upload
# format 2, where the program's addresses go with it). The compile_and_upload_<board>.sh scripts
# call this with each board's settings.
HERE="$(cd "$(dirname "$0")" && pwd)"

options=()
program=
format=(-Fbin)
out=a.out
for arg in "$@"; do
  case "$arg" in
    --hex) format=(-Fihex); out=a.hex ;;
    -*) options+=("$arg") ;;
    *)  [ -z "$program" ] || { echo "Only one program may be given" >&2; exit 2; }
        program="$arg" ;;
  esac
done
[ -n "$program" ] || { echo "Usage: $(basename "$0") [--noreset] [transfer.py options] <program.s>" >&2; exit 2; }

"$HERE/../../firmware/vasm" -quiet -wdc02 -wfail "${format[@]}" -dotdir -ignore-mult-inc -esc -o "$out" "$program" &&
  python3 "$HERE/transfer.py" "${options[@]}" "$out"
