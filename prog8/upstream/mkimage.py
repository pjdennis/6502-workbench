#!/usr/bin/env python3
"""Wrap a prog8 RAW binary (loaded at $0200) into the emulator's image format:
a $0200..$FFFF image whose $FFFC reset vector points at the entry ($0200)."""
import sys
LOAD = 0x0200
prog = open(sys.argv[1], "rb").read()
img = bytearray(0x10000 - LOAD)
assert len(prog) <= len(img), "program too big"
img[:len(prog)] = prog
img[0xFFFC - LOAD] = LOAD & 0xff
img[0xFFFD - LOAD] = LOAD >> 8
open(sys.argv[2], "wb").write(img)
