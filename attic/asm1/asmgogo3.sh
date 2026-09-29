#!/bin/zsh

vasm6502_oldstyle -quiet -wfail -Fbin -dotdir -esc asm3v.asm && gcc -o emulator.out emulator.c && ./emulator.out a.out 2000 asmbare3.asm asmout.out && ./emulator.out asmout.out 2000 asmbare3.asm asmoutout.out && hexdump -C asmoutout.out && diff <(hexdump -C asmout.out) <(hexdump -C asmoutout.out) && echo "OK"
