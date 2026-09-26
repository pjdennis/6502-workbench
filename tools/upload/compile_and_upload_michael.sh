#!/bin/sh
# Usage: compile_and_upload_michael.sh <program.s>   (writes a.out in the current directory)
HERE="$(cd "$(dirname "$0")" && pwd)"

"$HERE/../../firmware/vasm" -quiet -wdc02 -wfail -Fbin -dotdir -ignore-mult-inc -esc $1 && python3 "$HERE/transfer.py" --baudrate=57600 a.out
