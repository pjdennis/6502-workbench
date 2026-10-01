#!/bin/bash
# ATTIC NOTE: parked. Watches the old assembler2/emulator.c, which no longer exists (see attic/asm1/emulator.c and emulator/).
trap exit SIGINT

while true
do
    clear && ./asmtestgen.sh && ./run_tests.py
    echo "Waiting for file change..."
    fswatch -1 --event Updated --latency 0.1 \
        asmtestgen.sh emulator.c sidebyside.cpp 00/asm.c \
        00/asm.asm 01/asm.asm 02/asm.asm 03/asm.asm 04/asm.asm 05/asm.asm \
        06/asm.asm 06/instgen.asm 07/asm.asm 07/instgen.asm 08/asm.asm 08/instgen.asm \
        09/asm.asm 09/instgen.asm 09/environment.asm 09/common.asm \
        10/asm.asm 10/instgen.asm 10/environment.asm 10/common.asm 10/hash_table.asm 10/file_stack.asm 10/to_decimal.asm \
        11/asm.asm 11/instgen.asm 11/environment.asm 11/common.asm 11/hash_table.asm 11/file_stack.asm 11/to_decimal.asm test16.asm \
        12/asm.asm 12/instgen.asm 12/environment.asm 12/common.asm 12/hash_table.asm 12/file_stack.asm 12/to_decimal.asm \
        13/asm.asm 13/instgen.asm 13/environment.asm 13/common.asm 13/hash_table.asm 13/file_stack.asm 13/to_decimal.asm 13/errors.asm 13/fwdref.asm \
        14/asm.asm 14/instgen.asm 14/environment.asm 14/common.asm 14/hash_table.asm 14/file_stack.asm 14/to_decimal.asm 14/errors.asm 14/fwdref.asm \
        15/asm.asm 15/instgen.asm 15/environment.asm 15/common.asm 15/hash_table.asm 15/file_stack.asm 15/to_decimal.asm 15/errors.asm 15/fwdref.asm 15/label_scope.asm \
        16/asm.asm 16/instgen.asm 16/environment.asm 16/common.asm 16/hash_table.asm 16/file_stack.asm 16/to_decimal.asm 16/errors.asm 16/fwdref.asm 16/label_scope.asm 16/macros.asm \
        17/asm.asm 17/instgen.asm 17/environment.asm 17/common.asm 17/hash_table.asm 17/file_stack.asm 17/to_decimal.asm 17/errors.asm 17/fwdref.asm 17/label_scope.asm 17/macros.asm \
        test19.asm test_inc19.asm \
	run_tests.py 17/tests/file_stack/file_stack_test.asm 17/tests/file_stack/file_stack_tests.txt 17/tests/asm/*.txt
        > /dev/null

    sleep 0.1
done
