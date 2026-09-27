#!/bin/sh
# Usage: compile_and_upload_michael.sh [--noreset] <program.s>   (writes a.hex in the current directory)
# Michael's ROM (firmware/boards/michael/michael_rom.s) takes upload format 2, which carries the
# program's own load and start address (its lowest .org)
exec "$(dirname "$0")/compile_and_upload.sh" --baudrate=57600 --format=2 --hex "$@"
