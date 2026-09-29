#!/bin/zsh

gcc -o emulator.out emulator.c && vasm6502_oldstyle -quiet -wfail -Fbin -dotdir -esc -o asm3v.out asm3v.asm && ./emulator.out asm3v.out 2000 asm3b.asm asm3b.out && hexdump -C asm3b.out && diff <(hexdump -C asm3v.out) <(hexdump -C asm3b.out) && echo "OK"
