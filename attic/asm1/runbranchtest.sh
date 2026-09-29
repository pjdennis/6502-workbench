#!/bin/bash

gcc -o emulator.out emulator.c &&
  vasm6502_oldstyle -quiet -wfail -Fbin -dotdir -esc -o asm4v.out asm4v.asm &&
  ./emulator.out asm4v.out 2000 asm4b.asm asm4b.out &&
  ./emulator.out asm4b.out 2000 asm4b2.asm asm4b2.out &&
  ./emulator.out asm4b2.out 2000 asm4b3.asm asm4b3.out &&
  ./emulator.out asm4b3.out 2000 asm4b4.asm asm4b4.out &&
  ./emulator.out asm4b4.out 2000 asm4b5.asm asm4b5.out &&
  ./emulator.out asm4b5.out 2000 instgen.asm instgen.out &&
  ./emulator.out instgen.out 2000 /dev/null inst.asm.out &&
  cat inst.asm.out asm4b6.asm > asm4b6c.asm.out &&
  ./emulator.out asm4b5.out 2000 asm4b6c.asm.out asm4b6c.out &&
  ./emulator.out asm4b6c.out 2000 asm4b6c.asm.out asm4b6c_2.out &&
  diff <(hexdump -C asm4b6c.out) <(hexdump -C asm4b6c_2.out) &&
  ./emulator.out asm4b6c_2.out 2000 branch-test.asm branch-test.out &&
  hexdump -C branch-test.out &&
  echo "Did not fail"
