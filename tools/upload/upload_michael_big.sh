#!/bin/sh
# Usage: upload_michael_big.sh [transfer.py options] <program.bin>
# Uploads a program too big for Michael's ROM loader, which takes programs at $0900 and no further
# than the interrupt page: it resets the board and sends the second-stage loader
# (firmware/programs/michael/michael_second_stage_loader.s) through the ROM's loader, then sends the
# program through that, without a reset, to $0400, where it runs. Options (e.g. --port=DEVICE) go
# to both transfers.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"

options=
program=
for arg in "$@"; do
  case "$arg" in
    -*) options="$options $arg" ;;
    *)  [ -z "$program" ] || { echo "Only one program may be given" >&2; exit 2; }
        program="$arg" ;;
  esac
done
[ -n "$program" ] || { echo "Usage: $(basename "$0") [transfer.py options] <program.bin>" >&2; exit 2; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
"$HERE/../../firmware/vasm" -quiet -wdc02 -wfail -Fbin -dotdir -ignore-mult-inc -esc \
  -o "$work/loader.bin" "$HERE/../../firmware/programs/michael/michael_second_stage_loader.s"

python3 "$HERE/transfer.py" --baudrate=57600 --wait $options "$work/loader.bin"
# The ROM's loader checks the second-stage loader and starts it; give it time to get ready
sleep "${MICHAEL_LOADER_START_SECONDS:-1}"
python3 "$HERE/transfer.py" --baudrate=57600 --noreset $options "$program"
