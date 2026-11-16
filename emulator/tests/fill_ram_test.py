#!/usr/bin/env python3
"""End-to-end tests of --fill-ram (make fill-ram; no vasm needed).

On the default machine, the memory dump at exit shows RAM filled with bytes
that are not 0, and the program, the stubs, the arguments, the ports and the
vectors as the loader leaves them; without the option memory is 0 as before.
On the BBC B+128, *SAVE of main RAM shows the same, a program loaded over
it runs, and the module's RAM form is filled and a ROM image is not. The
fill (fill_ram.c) is tested byte by byte in test_fill_ram.c. Run from the
repository root.
"""

import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EMU = os.path.join(ROOT, "emulator", "emulator.out")

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


# At $1000: LDA #0, STA $F003 (the exit port), and the reset vector ($1000)
# as the program's last two bytes, which the default machine copies to $FFFC.
PROGRAM = bytes([0xA9, 0x00, 0x8D, 0x03, 0xF0, 0x00, 0x10])


def default_machine(work, fill):
    prog = os.path.join(work, "prog.bin")
    with open(prog, "wb") as f:
        f.write(PROGRAM)
    dump = os.path.join(work, "dump.bin")
    args = [EMU, prog, "--load", "1000", "--dump", dump] + (["--fill-ram"] if fill else []) + ["ARGUMENT"]
    p = subprocess.run(args, capture_output=True, timeout=30)
    with open(dump, "rb") as f:
        return p.returncode, f.read()


def bbc(*args):
    p = subprocess.run([EMU, "--machine", "bbcbplus", "--bbc-strict", *args], capture_output=True, timeout=30)
    return p.returncode, p.stdout, p.stderr.decode(errors="replace")


def main():
    if not os.path.exists(EMU):
        sys.exit("fill_ram_test: build emulator/emulator.out first (make)")
    work = tempfile.mkdtemp(prefix="fill_ram_test_")
    try:
        run_tests(work)
    finally:
        shutil.rmtree(work)
    if failures:
        print(f"fill-ram: {len(failures)} failed: {', '.join(failures)}")
        sys.exit(1)
    print("fill-ram: all passed")


def run_tests(work):
    print("fill-ram: the default machine")
    rc, plain = default_machine(work, False)
    check("without the option the program runs", rc == 0)
    check("without the option RAM is 0", plain[0x2000:0xF000] == bytes(0xF000 - 0x2000))
    rc, mem = default_machine(work, True)
    check("with it the program runs", rc == 0)
    ram = mem[:0x1000] + mem[0x1000 + len(PROGRAM):0xF000]
    check("with it RAM below $F000 has no zero byte", 0 not in ram)
    check("not one repeated byte", len(set(ram)) == 255)
    check("the program is as loaded", mem[0x1000:0x1000 + len(PROGRAM)] == PROGRAM)
    end = 0xF006 + len(plain[0xF006:0xFE00].rstrip(b"\0"))
    check("the stubs are as without it", end > 0xF020 and mem[0xF006:end] == plain[0xF006:end])
    check("RAM after the stubs is filled", 0 not in mem[end + 1:0xFE00])
    check("the argument is at $FE00", mem[0xFE00:0xFE09] == b"ARGUMENT\0")
    check("the ports and vectors are as without it", mem[0xFFE0:] == plain[0xFFE0:]
          and mem[0xF000:0xF006] == plain[0xF000:0xF006])
    rc, again = default_machine(work, True)
    check("the same bytes every run", again == mem)

    print("fill-ram: the BBC B+128")
    disk = os.path.join(work, "disk")
    os.makedirs(disk)
    rc, out, err = bbc("--disk", disk, "--bbc-command", "SAVE PLAIN 0 +8000")
    check("without the option main RAM is 0 but for the MOS's", rc == 0 and
          open(os.path.join(disk, "PLAIN"), "rb").read()[0x0800:0x7FFF] == bytes(0x7FFF - 0x0800), err)
    rc, out, err = bbc("--disk", disk, "--fill-ram", "--bbc-command", "SAVE MAIN 0 +8000")
    main_ram = open(os.path.join(disk, "MAIN"), "rb").read()
    check("with it main RAM from $0800 has no zero byte", rc == 0 and 0 not in main_ram[0x0800:], err)
    check("the command line is at $0700", main_ram[0x0700:0x0712] == b"SAVE MAIN 0 +8000\r")
    plain = open(os.path.join(disk, "PLAIN"), "rb").read()
    check("the vectors are the MOS's", main_ram[0x0200:0x0236] == plain[0x0200:0x0236])
    # A program loaded over the fill: LDA #'A', JSR OSWRCH, RTS
    prog = os.path.join(work, "a.bin")
    with open(prog, "wb") as f:
        f.write(bytes([0xA9, 0x41, 0x20, 0xEE, 0xFF, 0x60]))
    p = subprocess.run([EMU, prog, "--machine", "bbcbplus", "--load", "1900", "--fill-ram", "--bbc-strict"],
                       capture_output=True, timeout=30)
    check("a program loaded over it runs", p.returncode == 0 and p.stdout == b"A", p.stderr)
    # The module (slot 4) seen through the window: COPY selects the slot and copies $8000-$80FF
    # to $3000, which *SAVE then writes
    copy = bytes([0xA9, 0x04, 0x85, 0xF4, 0x8D, 0x30, 0xFE,           # select slot 4 ($F4 and ROMSEL)
                  0xA2, 0x00, 0xBD, 0x00, 0x80, 0x9D, 0x00, 0x30,      # LDX #0: LDA $8000,X: STA $3000,X
                  0xE8, 0xD0, 0xF7,                                    # INX: BNE
                  0xA9, 0x0F, 0x85, 0xF4, 0x8D, 0x30, 0xFE, 0x60])     # slot 15 again, RTS
    with open(os.path.join(disk, "COPY"), "wb") as f:
        f.write(copy)
    with open(os.path.join(disk, "COPY.inf"), "w") as f:
        f.write("COPY 00001900 00001900\n")
    for form, extra in (("RAM", ["--bbc-module-ram"]), ("ROM", ["--bbc-module", prog])):
        rc, out, err = bbc("--disk", disk, "--fill-ram", "--bbc-module-scheme", "direct16", *extra,
                           "--bbc-command", "RUN COPY", "--bbc-command", "SAVE WIN" + form + " 3000 +100")
        window = open(os.path.join(disk, "WIN" + form), "rb").read()
        if form == "RAM":
            check("the module's RAM form is filled", rc == 0 and 0 not in window, err)
        else:
            check("a ROM image is not", rc == 0 and window == prog_bytes(prog) + b"\xff" * (256 - 6), err)


def prog_bytes(path):
    with open(path, "rb") as f:
        return f.read()


if __name__ == "__main__":
    main()
