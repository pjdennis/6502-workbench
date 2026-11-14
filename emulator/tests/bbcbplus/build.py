#!/usr/bin/env python3
"""Build the bbcbplus test programs into a directory.

Usage: emulator/tests/bbcbplus/build.py OUT_DIR

Assembles the sources here with the repository's own assembler (its
Python work-alike, asm/pyasm.py) and writes:

  hello.bin                       hello.asm, at $1900 (run with --load 1900)
  COPY, COPY.inf                  copy.asm, load and exec $1900
  module-cc128.rom                module.asm's banks 0 and 3 in a 128 KB image,
  module-direct16.rom             switched as the scheme named (define:DIRECT16)
  LOADER-cc128, LOADER-direct16   loader.asm (with .inf files), load and exec $1900

The other banks of a module image are $FF, as an erased EPROM.
"""

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "asm"))
import pyasm  # noqa: E402

BANK = 0x4000


def assemble(name, defines=()):
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.bin")
        pyasm.Assembler(os.path.join(HERE, name), out, defines=list(defines)).run()
        with open(out, "rb") as f:
            return f.read()


def write(out_dir, name, data, load=None):
    with open(os.path.join(out_dir, name), "wb") as f:
        f.write(data)
    if load is not None:
        with open(os.path.join(out_dir, name + ".inf"), "w") as f:
            f.write(f"{name} {load:08X} {load:08X} {len(data):08X}\n")


def module_image(scheme_defines):
    banks = [b"\xFF" * BANK] * 8
    for n in (0, 3):
        bank = assemble("module.asm", [f"BANK{n}", *scheme_defines])
        assert len(bank) == BANK, (n, len(bank))
        banks[n] = bank
    return b"".join(banks)


def build(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    write(out_dir, "hello.bin", assemble("hello.asm"))
    write(out_dir, "COPY", assemble("copy.asm"), load=0x1900)
    write(out_dir, "module-cc128.rom", module_image(["CC128"]))
    write(out_dir, "module-direct16.rom", module_image(["DIRECT16"]))
    write(out_dir, "LOADER-cc128", assemble("loader.asm", ["CC128"]), load=0x1900)
    write(out_dir, "LOADER-direct16", assemble("loader.asm", ["DIRECT16"]), load=0x1900)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    build(sys.argv[1])
