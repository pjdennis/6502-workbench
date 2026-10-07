#!/usr/bin/env python3
"""Build the editor for Michael: the define:direct_io define:michael build, which runs from
LOAD on the services of the Michael ROM (firmware/boards/michael/michael_rom.s).

    python3 editor/michael_image.py OUT     (from the repository root)
    python3 editor/michael_image.py --graphic OUT OUT.s19   (the editor to OUT, and with its graphic
                                            launcher as S-records to OUT.s19, for transfer.py)

writes the editor binary, for tools/upload/transfer.py --format=3 --load-address=0200 (which
loads it at $0200 and runs it there). Needs the emulator and asm17 built (tools/build_all.sh); building the ROM needs vasm6502_oldstyle.
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

EDITOR = Path(__file__).resolve().parent
ROOT = EDITOR.parent
EMULATOR = ROOT / "emulator" / "emulator.out"
ASSEMBLER = ROOT / "asm" / "17" / "out" / "asm.out"
ROM_SOURCE = ROOT / "firmware" / "boards" / "michael" / "michael_rom.s"
MEMORY_MAP = EDITOR / "memory_map.asm"
LOAD = 0x0200
LAUNCHER = 0x0010           # where the graphic launcher runs (zero page; not 0, which S-records can not start at)
LAUNCHER_SOURCE = EDITOR / "michael_graphic_launcher.s"

sys.path.insert(0, str(ROOT / "tools" / "upload"))
import upload_frame  # noqa: E402


def memory_map_address(name):
    """An address the define:michael memory map gives name."""
    michael = MEMORY_MAP.read_text().split(".ifdef michael", 1)[1].split(".else", 1)[0]
    return int(re.search(r"^%s\s*=\s*\$([0-9A-F]+)" % name, michael, re.M).group(1), 16)


def assemble_editor(out, *defines):
    """Assemble editor/editor.asm to out with asm17; returns its bytes."""
    subprocess.run([EMULATOR, ASSEMBLER, "--no-dump", "editor/editor.asm", out, *defines],
                   check=True, capture_output=True, cwd=ROOT)
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


def graphic_launcher():
    """The launcher's bytes: it selects the graphic display, sets the scroll region and starts the editor."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "launcher.bin"
        subprocess.run([ROOT / "firmware" / "vasm", "-quiet", "-wdc02", "-wfail", "-Fbin", "-dotdir",
                        "-ignore-mult-inc", "-esc", "-o", out, LAUNCHER_SOURCE],
                       check=True, capture_output=True, cwd=ROOT)
        return out.read_bytes()


def write_upload(binary, out, graphic=False):
    """Write the format 3 upload of binary (loaded at LOAD and run there) to out, as it goes on
    the wire, e.g. for the emulator's --serial-input. With graphic, the launcher runs first."""
    segments = [(LOAD, Path(binary).read_bytes())]
    start = LOAD
    if graphic:
        segments.insert(0, (LAUNCHER, graphic_launcher()))
        start = LAUNCHER
    Path(out).write_bytes(upload_frame.format_3(segments, start=start))
    return Path(out)


def write_srec(binary, out):
    """Write the editor with the graphic launcher as S-records to out (S1 records, an S9 that starts the
    launcher), for tools/upload/transfer.py."""
    def record(kind, address, data=b""):
        body = bytes([len(data) + 3]) + address.to_bytes(2, "big") + data
        return "S%d%s%02X" % (kind, body.hex().upper(), ~sum(body) & 0xff)
    lines = []
    for address, data in ((LAUNCHER, graphic_launcher()), (LOAD, Path(binary).read_bytes())):
        lines += [record(1, address + i, data[i:i + 32]) for i in range(0, len(data), 32)]
    Path(out).write_text("\n".join(lines + [record(9, LAUNCHER)]) + "\n")
    return Path(out)


if __name__ == "__main__":
    if len(sys.argv) == 2:
        build(sys.argv[1])
    elif len(sys.argv) == 4 and sys.argv[1] == "--graphic":
        write_srec(build(sys.argv[2]), sys.argv[3])
    else:
        raise SystemExit(__doc__)
