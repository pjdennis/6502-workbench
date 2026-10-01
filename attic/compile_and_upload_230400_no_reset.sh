#!/bin/sh
# ATTIC NOTE: parked. Assumes ./vasm6502_oldstyle and transfer*.py in the repo root (old layout). Live: tools/upload/compile_and_upload*.sh

./vasm6502_oldstyle -wdc02 -wfail -Fbin -dotdir -ignore-mult-inc -esc $1 && python3 transfer_230400.py --noreset a.out
