#!/bin/bash
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
exec "$ROOT/emulator/emulator.out" "$ROOT/editor/out/editor_stable.out" --load 0400 --console --mhz 0.5 "$@"
