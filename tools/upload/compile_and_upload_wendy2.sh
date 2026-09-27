#!/bin/sh
# Usage: compile_and_upload_wendy2.sh [--noreset] <program.s>   (writes a.out in the current directory)
exec "$(dirname "$0")/compile_and_upload.sh" --baudrate=115200 "$@"
