#!/bin/zsh

vasm6502_oldstyle -quiet -wfail -Fbin -dotdir -esc asm2v.asm && gcc -o emulator.out emulator.c && ./emulator.out a.out 2000 asmbare2.asm asmout.out && ./emulator.out asmout.out 2000 asmbare2.asm asmoutout.out && hexdump -C asmoutout.out && diff <(hexdump -C a.out) <(hexdump -C asmoutout.out) && echo "OK"
