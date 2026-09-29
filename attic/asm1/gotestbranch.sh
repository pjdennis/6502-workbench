#!/bin/bash
trap exit SIGINT
clear && ./runbranchtest.sh
echo "Waiting for file change..."

while fswatch -1 --event Updated --latency 0.1 emulator.c asm4v.asm asm4b.asm asm4b2.asm asm4b3.asm asm4b4.asm asm4b5.asm asm4b6.asm instgen.asm branch-test-forward-out-of-range.asm runbranchtest.sh branch-test.asm branch-test-backward-out-of-range.asm > /dev/null
do
    clear && ./runbranchtest.sh
    echo "Waiting for file change..."
done
