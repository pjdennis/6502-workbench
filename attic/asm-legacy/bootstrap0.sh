#!/bin/bash
# bootstrap0.sh - Verify minimal bootstrap assembler self-assembly
set -e

echo "=== Bootstrap Level 0 Verification ==="

# Build C bootstrap assembler
echo "Building C bootstrap assembler..."
gcc -O2 -o asm0c.out asm0c.c

# C assembler builds 6502 assembler
echo "C assembler -> 6502 assembler..."
./asm0c.out asm0.asm asm0_from_c.out

# 6502 assembler self-assembles
echo "6502 assembler self-assembling..."
./emulator.out asm0_from_c.out 2000 asm0.asm asm0_self.out

# Verify identical
echo "Comparing outputs..."
cmp asm0_from_c.out asm0_self.out

echo "=== Bootstrap Level 0 SUCCESS ==="
