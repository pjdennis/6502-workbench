#!/bin/zsh
clear && ./asmtestprg2.sh
echo "Waiting for file change..."

while fswatch -1 emulator.c asm4v.asm asm4b.asm asm4b2.asm asm4b3.asm asm4b4.asm asm4b5.asm asm4b6.asm asmprg2.asm asmtestprg2.sh > /dev/null
do
    clear && ./asmtestprg2.sh
    echo "Waiting for file change..."
done
