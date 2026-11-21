#!/usr/bin/env python3
"""End-to-end tests of --machine bbcbplus (make bbcbplus-goldens).

Builds the programs in emulator/tests/bbcbplus/ with build.py (the
repository's own assembler, asm/pyasm.py; no vasm needed) and runs them
on emulator/emulator.out, all with --bbc-strict so that a write to MOS
memory or a ROMSEL unlike $F4 at a MOS call would fail them:

  - a program that prints through OSWRCH;
  - *COPY, a file copied through OSFIND/OSBGET/OSBPUT, and its error for a
    missing file;
  - a module image (both switching schemes) whose service handler claims
    *HELLO and prints from bank 3 through a trampoline in main RAM;
  - the same image loaded bank by bank into the module's RAM form by a
    loader run from disk.

It also checks that the MOS ROM header regenerates from its source byte
for byte, and the batch-only refusals. Run from the repository root.
"""

import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EMU = os.path.join(ROOT, "emulator", "emulator.out")
BUILD = os.path.join(ROOT, "emulator", "tests", "bbcbplus", "build.py")

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


def emu(*args, code=None, stdin=b""):
    """Run the machine; a code file goes first, as the command line has it"""
    first = [code] if code else []
    p = subprocess.run([EMU, *first, "--machine", "bbcbplus", "--bbc-strict", "--exit-report", *args],
                       input=stdin, capture_output=True, timeout=60)
    return p.returncode, p.stdout, p.stderr.decode(errors="replace")


def report_line(err, key):
    for line in err.splitlines():
        if key in line:
            return line
    return ""


def main():
    if not os.path.exists(EMU):
        sys.exit("bbcbplus_test: build emulator/emulator.out first (make)")
    work = tempfile.mkdtemp(prefix="bbcbplus_test_")
    try:
        build = os.path.join(work, "build")
        subprocess.run([sys.executable, BUILD, build], check=True)
        run_tests(work, build)
    finally:
        shutil.rmtree(work)
    if failures:
        print(f"bbcbplus: {len(failures)} failed: {', '.join(failures)}")
        sys.exit(1)
    print("bbcbplus: all passed")


def run_tests(work, build):
    print("bbcbplus: the MOS ROM")
    header = os.path.join(work, "mos.h")
    subprocess.run([sys.executable, os.path.join(ROOT, "emulator", "bbc_mos_to_c.py"),
                    os.path.join(ROOT, "emulator", "bbc_mos_rom.asm"), "-o", header], check=True)
    with open(header) as a, open(os.path.join(ROOT, "emulator", "bbc_mos_rom_generated.h")) as b:
        check("the checked-in header is what the source assembles to", a.read() == b.read())

    print("bbcbplus: OSWRCH")
    rc, out, err = emu("--load", "1900", code=os.path.join(build, "hello.bin"))
    check("hello prints its line", out == b"Hello, B+\n\r", repr(out))
    check("hello returns: status 0", rc == 0, err)
    check("hello: no check failed", "mos-memory-writes=0  romsel-mismatches=0" in err, err)
    check("hello: cycles reported", "cpu_cycles=" in report_line(err, "exit"), err)

    print("bbcbplus: *COPY through OSFIND/OSBGET/OSBPUT")
    disk = os.path.join(work, "disk")
    os.makedirs(disk)
    for name in ("COPY", "COPY.inf"):
        shutil.copy(os.path.join(build, name), disk)
    data = bytes(range(256)) * 3 + b"the end\r"
    with open(os.path.join(disk, "SRC"), "wb") as f:
        f.write(data)
    rc, out, err = emu("--disk", disk, "--bbc-command", "COPY SRC DST")
    with open(os.path.join(disk, "DST"), "rb") as f:
        copied = f.read()
    check("*COPY SRC DST copies the file", rc == 0 and copied == data, err)
    check("*COPY: the report counts the file traffic",
          f"files: opened=2  bytes-read={len(data)}  bytes-written={len(data)}" in err, err)
    rc, out, err = emu("--disk", disk, "--bbc-command", "*RUN COPY  SRC   DST2")
    check("*RUN COPY with a tail copies it too", rc == 0 and open(os.path.join(disk, "DST2"), "rb").read() == data, err)
    rc, out, err = emu("--disk", disk, "--bbc-command", "COPY NONE X")
    check("a missing file: File not found, status 1", rc == 1 and err.startswith("File not found\n"), err)
    check("a missing file: no output file", not os.path.exists(os.path.join(disk, "X")))
    rc, out, err = emu("--disk", disk, "--bbc-command", "NOSUCH")
    check("an unknown command: Bad command, status 1", rc == 1 and err.startswith("Bad command\n"), err)

    for scheme in ("cc128", "direct16"):
        print(f"bbcbplus: the module ({scheme}), *HELLO")
        image = os.path.join(build, f"module-{scheme}.rom")
        rc, out, err = emu("--bbc-module", image, "--bbc-module-scheme", scheme, "--bbc-command", "HELLO")
        check(f"{scheme}: *HELLO prints from bank 3", out == b"Hello from bank 3\n\r", repr(out) + err)
        check(f"{scheme}: status 0", rc == 0, err)
        check(f"{scheme}: two bank switches", "bank 0, bank switches 2" in report_line(err, "module:"), err)
        check(f"{scheme}: no check failed", "mos-memory-writes=0  romsel-mismatches=0" in err, err)
        rc, out, err = emu("--bbc-module", image, "--bbc-module-scheme", scheme, "--bbc-module-slot", "7",
                           "--bbc-command", "HELLO")
        check(f"{scheme}: in slot 7 too", out == b"Hello from bank 3\n\r" and rc == 0, err)

        print(f"bbcbplus: the module's RAM form ({scheme}), loaded from disk")
        ramdisk = os.path.join(work, f"ram-{scheme}")
        os.makedirs(ramdisk)
        shutil.copy(image, os.path.join(ramdisk, "MODULE"))
        shutil.copy(os.path.join(build, f"LOADER-{scheme}"), os.path.join(ramdisk, "LOADER"))
        with open(os.path.join(ramdisk, "LOADER.inf"), "w") as f:
            f.write("LOADER 00001900 00001900\n")
        rc, out, err = emu("--bbc-module-ram", "--bbc-module-scheme", scheme, "--disk", ramdisk,
                           "--bbc-command", "LOADER")
        check(f"{scheme} RAM: *LOADER loads the banks and *HELLO prints from bank 3",
              out == b"Hello from bank 3\n\r" and rc == 0, repr(out) + err)
        check(f"{scheme} RAM: the report names the RAM form", f"{scheme} RAM" in report_line(err, "module:"), err)
        check(f"{scheme} RAM: no check failed", "mos-memory-writes=0  romsel-mismatches=0" in err, err)
        rc, out, err = emu("--bbc-module-ram", "--bbc-module-scheme", scheme, "--bbc-command", "HELLO")
        check(f"{scheme} RAM: empty, *HELLO is a bad command", rc == 1 and err.startswith("Bad command"), err)

    print("bbcbplus: the machine each model is, as a program sees it")
    romtab = os.path.join(build, "romtab.bin")
    for model, line in ((None, b"219 ................"), ("b", b"119 ................"),
                        ("master", b"30E .........SSSSSSS")):
        rc, out, err = emu("--load", "1900", *(("--bbc-model", model) if model else ()), code=romtab)
        check(f"{model or 'bplus'}: OSBYTE 0, PAGE and the ROM type table", out == line + b"\n\r" and rc == 0,
              repr(out) + err)
    dump = os.path.join(work, "ram.bin")
    rc, out, err = emu("--load", "1900", "--bbc-model", "master", "--bbc-ram-dump", dump, code=romtab)
    with open(dump, "rb") as f:
        ram = f.read()
    check("--bbc-ram-dump: main RAM at the end, the program's pointer to the table in it",
          len(ram) == 0x8000 and ram[0x70:0x72] == b"\xA1\x02" and ram[0x2AD] == 0x82, (len(ram), ram[0x70:0x72]))
    rc, out, err = emu("--load", "1900", "--bbc-model", "master", "--cpu", "nmos", code=romtab)
    check("master --cpu nmos: the same", out == b"30E .........SSSSSSS\n\r" and rc == 0, repr(out) + err)
    print("bbcbplus: --bbc-model master, the module in its socket (slot 8)")
    image = os.path.join(build, "module-cc128.rom")
    rc, out, err = emu("--bbc-model", "master", "--bbc-module", image, "--bbc-command", "HELLO")
    check("master: *HELLO prints from bank 3", out == b"Hello from bank 3\n\r" and rc == 0, repr(out) + err)
    check("master: the module is in slot 8", "module: slot 8, cc128 ROM" in report_line(err, "module:"), err)
    check("master: no check failed", "mos-memory-writes=0  romsel-mismatches=0" in err, err)
    rc, out, err = emu("--bbc-model", "master", "--bbc-module", image, "--bbc-module-slot", "4",
                       "--bbc-command", "HELLO")
    check("master: slot 4 is sideways RAM, refused for the module", rc == 1 and "sideways RAM" in err, err)

    print("bbcbplus: batch only, and the cycle cap")
    p = subprocess.run([EMU, "--machine", "bbcbplus", "--bbc-command", "X", "--live"], capture_output=True)
    check("--live is refused", p.returncode == 1 and b"batch only" in p.stderr, p.stderr)
    p = subprocess.run([EMU, "--machine", "bbcbplus", "--bbc-command", "X", "--web"], capture_output=True)
    check("--web is refused", p.returncode == 1 and b"batch only" in p.stderr, p.stderr)
    spin = os.path.join(work, "spin.bin")
    with open(spin, "wb") as f:
        f.write(bytes([0x4C, 0x00, 0x19]))   # JMP $1900
    rc, out, err = emu("--load", "1900", "--cycle-cap", "5000", code=spin)
    check("the cycle cap ends the run with status 2", rc == 2 and "(cycle cap)" in err, err)


if __name__ == "__main__":
    main()
