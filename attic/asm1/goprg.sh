#!/bin/zsh
clear && ./asmtestprg.sh
echo "Waiting for file change..."

while fswatch -1 emulator.c asm4v.asm asm4b.asm asm4b2.asm asm4b3.asm asm4b4.asm asm4b5.asm asmprg.asm asmtestprg.sh > /dev/null
do
    clear && ./asmtestprg.sh
    echo "Waiting for file change..."
done
