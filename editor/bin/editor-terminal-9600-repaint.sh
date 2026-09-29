#!/bin/bash
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
exec "$ROOT/emulator/emulator.out" "$ROOT/editor/out/editor_terminal_stable.out" --load 0400 --terminal --baud 9600 --mhz 2 --show-repaints "$@"
