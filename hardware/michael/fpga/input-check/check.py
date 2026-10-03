#!/usr/bin/env python3
"""Checks the spi-display interface's inputs from Michael end to end.

With the input-check design loaded in the FPGA (`make check` does that first), this uploads
firmware/programs/michael/michael_fpga_input_check.s to Michael, collects the FPGA's report from the
Cmod's USB serial port, and compares it with what the program does, naming any signal that differs.

  check.py [--michael-port DEV] [--fpga-port DEV] [--timeout S]
"""
import argparse
import os
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
PROGRAM = os.path.join(REPO, "firmware", "programs", "michael", "michael_fpga_input_check.s")
UPLOAD = os.path.join(REPO, "tools", "upload", "compile_and_upload_michael.sh")

IDLE = "01101"  # E low, CSB high, RSTB high, DC low, backlight high
START = [f"S C3 {IDLE}", f"S 3C {IDLE}", f"S 00 {IDLE}"]
END = [f"S E7 {IDLE}", f"S 7E {IDLE}", f"S 00 {IDLE}"]

# The 13 reported bits, most significant first, as named on the wiring sheet
SIGNALS = [f"PB{i} (Cmod {i + 1})" for i in range(7, -1, -1)] + [
    "E/PA0 (Cmod 9)", "CSB/PA1 (Cmod 10)", "RSTB/PA2 (Cmod 11)", "DC/PA5 (Cmod 12)", "backlight/B5 (Cmod 13)"]


def expected_lines():
    """The report michael_fpga_input_check.s should produce, from its start marker to its end marker."""
    lines, last = [], None

    def state(portb, ctrl):
        nonlocal last
        line = f"S {portb:02X} {ctrl}"
        if line != last:  # the FPGA reports a settled state only when it changes
            lines.append(line)
        last = line

    def byte(value, dc):
        lines.append(f"B {value:02X} 101{dc}1")

    for v in (0xC3, 0x3C, 0x00):
        state(v, IDLE)
    for v in [1 << i for i in range(8)] + [0xFF, 0x55, 0xAA, 0x00]:
        state(v, IDLE)
    for ctrl in ("11101", "00101", "01001", "01111"):  # E high, CSB low, RSTB low, DC high; each then back
        state(0, ctrl)
        state(0, IDLE)
    state(0, "00111")  # gd_select: DC high, CSB low
    byte(0x2A, 0)
    for v in range(256):
        byte(v, 1)
    byte(0x2C, 0)
    for _ in range(64):
        byte(0x00, 1)
    state(0, "00111")  # after the fill: unchanged, so not reported again
    state(0, IDLE)     # gd_unselect
    for v in (0xE7, 0x7E, 0x00):
        state(v, IDLE)
    return lines


def find_start(lines):
    for i in range(len(lines) - len(START) + 1):
        if lines[i:i + len(START)] == START:
            return i
    return None


def bits(line):
    return int(line[2:4], 16) << 5 | int(line[5:10], 2)


def describe(step, exp, got):
    msg = f"step {step}: expected '{exp}', got '{got}'"
    if got[:1] in "SB" and len(got) == 10:
        if exp[0] != got[0]:
            msg += f" ({'a byte' if got[0] == 'B' else 'a state'} instead of {'a byte' if exp[0] == 'B' else 'a state'})"
        diff = bits(exp) ^ bits(got)
        named = [f"{name} expected {bits(exp) >> (12 - n) & 1}, got {bits(got) >> (12 - n) & 1}"
                 for n, name in enumerate(SIGNALS) if diff >> (12 - n) & 1]
        if named:
            msg += ": " + "; ".join(named)
    return msg


def compare(expected, got):
    problems = []
    if any(line.startswith("!") for line in got):
        problems.append("The FPGA's event buffer overflowed, so events were lost")
        got = [line for line in got if not line.startswith("!")]
    problems += [describe(i, e, g) for i, (e, g) in enumerate(zip(expected, got)) if e != g]
    if len(got) < len(expected):
        problems.append(f"{len(expected) - len(got)} lines missing, from step {len(got)}: '{expected[len(got)]}'")
    elif len(got) > len(expected):
        problems.append(f"{len(got) - len(expected)} unexpected lines after the end, from '{got[len(expected)]}'")
    return problems


def serial_module():
    kit = os.environ.get("FPGA_KIT") or os.path.join(REPO, "..", "fpga-toolchain-research")
    sys.path.insert(0, os.path.join(kit, "scripts"))
    import uart_check
    return uart_check


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--michael-port", help="Michael's serial port (default: as the upload tools choose it)")
    ap.add_argument("--fpga-port", help="the Cmod's serial port (default: auto-detect)")
    ap.add_argument("--timeout", type=float, default=30, help="seconds to wait for the end marker")
    args = ap.parse_args()

    uart_check = serial_module()
    lines, lock = [], threading.Lock()

    with uart_check.Serial(args.fpga_port or uart_check.find_port()) as ser:
        def reader():
            while True:
                raw = ser.readline(deadline=None).decode(errors="replace")
                # Junk can precede the first line (the serial line settling as the FPGA starts up)
                starts = [raw.find(c) for c in "SB!" if c in raw]
                line = raw[min(starts):].strip() if starts else raw.strip()
                with lock:
                    lines.append(line)

        ser.flush_input()
        threading.Thread(target=reader, daemon=True).start()
        ser.write(b"?")
        for _ in range(10):
            time.sleep(0.1)
            with lock:
                if lines:
                    break
        with lock:
            if not lines:
                sys.exit("No report from the FPGA: is the input-check design loaded (make prog)?")
            print(f"Inputs before the test: {lines[-1]}  (port B; E, CSB, RSTB, DC, backlight)")

        print(f"Uploading {os.path.relpath(PROGRAM, REPO)} to Michael ...")
        port = [f"--port={args.michael_port}"] if args.michael_port else []
        with tempfile.TemporaryDirectory() as tmp:  # the upload script writes a.s19 in its working directory
            r = subprocess.run([UPLOAD, *port, PROGRAM], cwd=tmp)
        if r.returncode:
            sys.exit(f"Upload failed ({r.returncode})")

        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            with lock:
                if lines[-len(END):] == END and find_start(lines) is not None:
                    break
            time.sleep(0.1)
        time.sleep(0.2)  # catch anything unexpected after the end marker
        with lock:
            got = list(lines)

    start = find_start(got)
    if start is None:
        print("The start marker never arrived. If Michael's LCD shows 'Ready', the upload didn't reach it: try\n"
              "  python3 tools/upload/transfer.py --daemon stop   (then rerun)\n"
              "Everything the FPGA reported:")
        print("\n".join(got[-40:]))
        sys.exit(1)
    expected = expected_lines()
    problems = compare(expected, got[start:])
    if problems:
        print(f"FAIL: {len(problems)} problem(s); the first ones:")
        print("\n".join("  " + p for p in problems[:15]))
        sys.exit(1)
    print(f"PASS: all {len(expected)} steps matched: each of the 13 inputs reaches its FPGA pin, "
          f"and all {sum(e[0] == 'B' for e in expected)} bytes were latched with the right DC.")


if __name__ == "__main__":
    main()
