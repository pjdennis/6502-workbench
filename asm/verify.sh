#!/bin/bash
# The assembler's whole check: builds the chain 00..17 (each stage assembles the next, 17 assembles
# itself) and runs the in-assembler tests. The editor's tests are in editor/verify.sh.

set -e
cd "$(dirname "$0")"

./asmtestgen.sh
