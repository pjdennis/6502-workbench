#!/bin/sh

vasm6502_oldstyle -quiet -wfail -Fbin -dotdir -esc asm2v.asm && gcc -o emulator.out emulator.c && ./emulator.out a.out 2000 asmbare.asm asmout.out && hexdump -C asmout.out
