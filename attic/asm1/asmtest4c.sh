#!/bin/zsh

gcc -o emulator.out emulator.c &&
  vasm6502_oldstyle -quiet -wfail -Fbin -dotdir -esc -o asm4v.out asm4v.asm &&
  ./emulator.out asm4v.out 2000 asm4b.asm asm4b.out &&
  ./emulator.out asm4b.out 2000 asm4b2.asm asm4b2.out &&
  ./emulator.out asm4b2.out 2000 asm4b3.asm asm4b3.out &&
  ./emulator.out asm4b3.out 2000 asm4b4.asm asm4b4.out &&
  ./emulator.out asm4b4.out 2000 asm4b6.asm asm4b6.out &&
#  ./emulator.out asm4b5.out 2000 asm4b6.asm asm4b6.out &&
  ./emulator.out asm4b6.out 2000 asm4b6.asm asm4b6_2.out &&
  diff <(hexdump -C asm4b6.out) <(hexdump -C asm4b6_2.out) &&
  hexdump -C asm4b6_2.out &&
  echo "OK"
