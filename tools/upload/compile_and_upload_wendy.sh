#!/bin/sh
# Usage: compile_and_upload_wendy.sh <program.s>   (writes a.out in the current directory)
# Wendy has no DTR reset, so the port is opened directly rather than through the serial daemon.
exec "$(dirname "$0")/compile_and_upload.sh" --baudrate=115200 --direct --noreset "$@"
