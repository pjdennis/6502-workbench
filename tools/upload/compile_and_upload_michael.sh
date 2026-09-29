#!/bin/sh
# Usage: compile_and_upload_michael.sh [--noreset] <program.s>   (writes a.out in the current directory)
exec "$(dirname "$0")/compile_and_upload.sh" --baudrate=57600 "$@"
