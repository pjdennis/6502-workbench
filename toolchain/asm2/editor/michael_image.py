#!/usr/bin/env python3
"""Build the editor for Michael: the define:direct_io define:michael build
and the Michael services (firmware/programs/michael/michael_editor_services.s)
as one RAM image, to load at LOAD.

    python3 editor/michael_image.py OUT     (from toolchain/asm2)

Needs the emulator and asm17 built, and vasm6502_oldstyle on PATH.
"""
import re
import subprocess
import sys
from pathlib import Path

ASM2 = Path(__file__).resolve().parents[1]
ROOT = ASM2.parents[1]
EMULATOR = ROOT / "emulator" / "emulator.out"
ASSEMBLER = ASM2 / "17" / "out" / "asm.out"
SERVICES = ROOT / "firmware" / "programs" / "michael" / "michael_editor_services.s"
LAYOUT = ROOT / "firmware" / "boards" / "michael" / "michael_editor_layout.inc"
LOAD = 0x0400


def layout_address(name):
    return int(re.search(r'^%s\s*=\s*\$([0-9a-fA-F]+)' % name, LAYOUT.read_text(), re.M).group(1), 16)


def assemble_editor(out, *defines):
    """Assemble editor/editor.asm to out with asm17; returns its bytes."""
    subprocess.run([EMULATOR, ASSEMBLER, "--no-dump", "editor/editor.asm", out, *defines],
                   check=True, capture_output=True, cwd=ASM2)
    return Path(out).read_bytes()


def build(out):
    """Write the image to out (next to it, the parts it is made of)."""
    out = Path(out)
    editor = assemble_editor(out.with_suffix(".editor"), "define:direct_io", "define:michael")[:-2]
    services_bin = out.with_suffix(".services")
    subprocess.run([ROOT / "firmware" / "vasm", "-quiet", "-wdc02", "-wfail", "-Fbin", "-dotdir",
                    "-ignore-mult-inc", "-esc", "-o", services_bin, SERVICES],
                   check=True, capture_output=True, cwd=ROOT)
    services_at = layout_address("MICHAEL_ENV_BASE") + 6
    if LOAD + len(editor) > services_at:
        raise SystemExit(f"the editor (${LOAD:04X}-${LOAD + len(editor) - 1:04X}) runs into "
                         f"the services at ${services_at:04X}")
    out.write_bytes(editor + bytes(services_at - LOAD - len(editor)) + services_bin.read_bytes())
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    build(sys.argv[1])
