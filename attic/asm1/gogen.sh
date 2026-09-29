#!/bin/bash
trap exit SIGINT

while true
do
    clear && ./asmtestgen.sh
    echo "Waiting for file change..."
    fswatch -1 --event Updated --latency 0.1 asmtestgen.sh emulator.c sidebyside.cpp asm4v.asm asm4b.asm asm4b2.asm asm4b3.asm asm4b4.asm asm4b5.asm asm4b6.asm asm4b7.asm asm4b8.asm asm4b9.asm asm4b10.asm asm4b11.asm instgen.asm instgen10.asm environment.asm common10.asm asm4b12.asm instgen12.asm common12.asm to_decimal.asm hash_table.asm file_stack.asm instgen13.asm common13.asm hash_table13.asm asm4b13.asm test.asm test_inc.asm > /dev/null

    sleep 0.1
done
