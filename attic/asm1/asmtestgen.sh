#!/bin/bash

shopt -s extglob

rm -f !(emulator|sidebyside).out &&
  make --quiet &&
  ./emulator.out asm4v.out 2000 asm4b.asm asm4b.out &&
  ./emulator.out asm4b.out 2000 asm4b2.asm asm4b2.out &&
  ./emulator.out asm4b2.out 2000 asm4b3.asm asm4b3.out &&
  ./emulator.out asm4b3.out 2000 asm4b4.asm asm4b4.out &&
  ./emulator.out asm4b4.out 2000 asm4b5.asm asm4b5.out &&
  ./emulator.out asm4b5.out 2000 instgen.asm instgen.out &&
  ./emulator.out instgen.out 2000 /dev/null inst.asm.out &&
  cat inst.asm.out asm4b6.asm > asm4b6c.asm.out &&
  ./emulator.out asm4b5.out 2000 asm4b6c.asm.out asm4b6c.out &&
  cat inst.asm.out asm4b7.asm > asm4b7c.asm.out &&
  ./emulator.out asm4b6c.out 2000 asm4b7c.asm.out asm4b7c.out &&
  cat inst.asm.out asm4b8.asm > asm4b8c.asm.out &&
  ./emulator.out asm4b7c.out 2000 asm4b8c.asm.out asm4b8c.out &&
  cat inst.asm.out asm4b9.asm > asm4b9c.asm.out &&
  ./emulator.out asm4b8c.out 2000 asm4b9c.asm.out asm4b9c.out &&
  ./emulator.out asm4b9c.out 2000 instgen10.asm instgen10.out &&
  ./emulator.out instgen10.out 2000 /dev/null inst10.asm.out &&
  ./emulator.out asm4b9c.out 2000 asm4b10.asm asm4b10.out &&
  ./emulator.out asm4b10.out 2000 asm4b11.asm asm4b11.out &&
  ./emulator.out asm4b11.out 2000 /dev/null /dev/null instgen12.asm instgen12.out &&
  ./emulator.out instgen12.out 2000 /dev/null inst12.asm.out &&
  ./emulator.out asm4b11.out 2000 /dev/null /dev/null asm4b12.asm asm4b12.out &&
  ./emulator.out asm4b12.out 2000 /dev/null /dev/null asm4b12.asm asm4b12_2.out &&
  ./emulator.out asm4b12.out 2000 /dev/null /dev/null instgen13.asm instgen13.out &&
  ./emulator.out instgen13.out 2000 /dev/null inst13.asm.out &&
  ./emulator.out asm4b12.out 2000 /dev/null /dev/null asm4b13.asm asm4b13.out &&
  ./emulator.out asm4b13.out 2000 /dev/null /dev/null asm4b13.asm asm4b13_2.out &&
  diff <(hexdump -C asm4b13.out) <(hexdump -C asm4b13_2.out) &&
  hexdump -C asm4b13_2.out | ./sidebyside.out

if [ $? -eq 0 ]; then
  echo "OK"
  ./emulator.out asm4b13_2.out 2000 /dev/null /dev/null test.asm test.out &&
  hexdump -C test.out &&
  echo "Assembled"
  if [ $? -eq 0 ]; then
    ./emulator.out test.out 1000 /dev/null - arg1 "arg 2"
  else
    echo "Did not assemble"
  fi
else
  echo "!!!Failed!!!"
fi
