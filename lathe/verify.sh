#!/bin/bash
# Lathe's whole check: every unittest file in lathe/tests, run from the repository root
# (lathe/host/README.md, "Tests"). Builds the emulator first if it is missing.
# Needs python3, and gcc and make for the emulator. Does not need vasm.

set -e
cd "$(dirname "$0")/.."

[ -x emulator/emulator.out ] || make -s

python3 -m unittest discover -s lathe/tests "$@"
