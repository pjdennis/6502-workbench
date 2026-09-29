#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$SCRIPT_DIR/../../emulator/emulator.out" "$SCRIPT_DIR/editor/out/editor_stable.out" --load 0400 --console --mhz 2 "$@"
