#!/usr/bin/env python3
"""Build the editor for Michael: the define:direct_io define:michael build, which runs from
LOAD on the services of the Michael ROM (firmware/boards/michael/michael_rom.s).

    python3 editor/michael_image.py OUT     (from toolchain/asm2)

writes the editor binary, for tools/upload/transfer.py --format=2 --load-address=0200 (which
loads it at $0200 and runs it there). Needs the emulator and asm17 built; building the ROM needs vasm6502_oldstyle.
"""
import re
import subprocess
import sys
from pathlib import Path

ASM2 = Path(__file__).resolve().parents[1]
ROOT = ASM2.parents[1]
EMULATOR = ROOT / "emulator" / "emulator.out"
ASSEMBLER = ASM2 / "17" / "out" / "asm.out"
ROM_SOURCE = ROOT / "firmware" / "boards" / "michael" / "michael_rom.s"
MEMORY_MAP = ASM2 / "editor" / "memory_map.asm"
LOAD = 0x0200

sys.path.insert(0, str(ROOT / "tools" / "upload"))
import upload_frame  # noqa: E402


def memory_map_address(name):
    """An address the define:michael memory map gives name."""
    michael = MEMORY_MAP.read_text().split(".ifdef michael", 1)[1].split(".else", 1)[0]
    return int(re.search(r"^%s\s*=\s*\$([0-9A-F]+)" % name, michael, re.M).group(1), 16)


def assemble_editor(out, *defines):
    """Assemble editor/editor.asm to out with asm17; returns its bytes."""
    subprocess.run([EMULATOR, ASSEMBLER, "--no-dump", "editor/editor.asm", out, *defines],
                   check=True, capture_output=True, cwd=ASM2)
    return Path(out).read_bytes()


def build(out):
    """Write the Michael editor to out: its code from LOAD, without the entry point the
    emulator's builds end with (LOAD holds jmp editor_main)."""
    out = Path(out)
    out.write_bytes(assemble_editor(out, "define:direct_io", "define:michael")[:-2])
    return out


def build_rom(out):
    """Assemble the Michael ROM to out."""
    subprocess.run([ROOT / "firmware" / "vasm", "-quiet", "-wdc02", "-wfail", "-Fbin", "-dotdir",
                    "-ignore-mult-inc", "-esc", "-o", out, ROM_SOURCE],
                   check=True, capture_output=True, cwd=ROOT)
    return Path(out)


def write_upload(binary, out):
    """Write the format 2 upload of binary (loaded at LOAD and run there) to out, as it goes on
    the wire, e.g. for the emulator's --serial-input."""
    Path(out).write_bytes(upload_frame.format_2([(LOAD, Path(binary).read_bytes())]))
    return Path(out)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    build(sys.argv[1])
