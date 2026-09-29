#!/bin/zsh

gcc -o emulator.out emulator.c && vasm6502_oldstyle -quiet -wfail -Fbin -dotdir -esc -o asm3v.out asm3v.asm && vasm6502_oldstyle -quiet -wfail -Fbin -dotdir -esc -o testv.out testv.asm && ./emulator.out asm3v.out 2000 testb.asm testb.out && hexdump -C testb.out && diff <(hexdump -C testv.out) <(hexdump -C testb.out) && echo "OK"
