#!/bin/sh
# Usage: compile_and_upload_michael.sh [--noreset] <program.s>   (writes a.s19 in the current directory)
# Michael's ROM (firmware/boards/michael/michael_rom.s) takes upload format 3, built from
# S-records: the program loads at its .org and starts at its start label, which it must have
exec "$(dirname "$0")/compile_and_upload.sh" --baudrate=57600 --format=3 --srec "$@"
