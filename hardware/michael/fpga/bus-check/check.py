#!/usr/bin/env python3
"""Checks the Michael FPGA bus's reads end to end (stage 1 of docs/michael-fpga-bus-plan.md).

With the bus-check design loaded in the FPGA (`make check` does that first), this uploads
firmware/programs/michael/michael_fpga_bus_check.s to Michael. The program echoes bytes through the FPGA,
reads them back and compares them, and reports through the FPGA's serial port. Its last part does the same
with the keyboard on: hold a key down when asked, so that keyboard interrupts land in the middle of reads
and exercise the SOEB interlock. The FPGA's counts then say how many reads were paused that way.

  check.py [--michael-port DEV] [--fpga-port DEV] [--timeout S]
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import board  # noqa: E402

PROGRAM = os.path.join(board.REPO, "firmware", "programs", "michael", "michael_fpga_bus_check.s")
START, HOLD, DONE = "FPGA BUS CHECK", "HOLD A KEY", "DONE"
# The program's report, in order, with how to judge each line
STEPS = [(START, "exact"), ("ID", "ok"), ("ECHO BAD", "count"), ("UNDERFLOW", "ok"), (HOLD, "exact"),
         ("KEYBOARD BAD", "count"), ("KEYS", "keys"), (DONE, "exact")]


def program_constant(name):
    with open(PROGRAM) as f:
        return int(re.search(rf"^{name}\s*=\s*(\d+)", f.read(), re.M)[1])


def expected_counts(report, rounds):
    """The transfers a complete, successful run makes, as the FPGA counts them (writes, reads; modulo 65536):
    ID and RESET, ECHO passes of 256 bytes each with a status read, the underflow's three reads, and the
    report, each line one SERIAL_SEND per say_string call (two for KEYS) plus one for its CR LF."""
    passes = program_constant("ECHO_PASSES") + rounds * program_constant("KEYBOARD_ROUND_PASSES")
    reads = 4 + 1 + passes * 257 + 3
    writes = 2 + passes * 257 + sum(len(line) + 2 + (3 if line.startswith("KEYS") else 2) for line in report)
    return writes % 65536, reads % 65536


def difference(got, expected, what):
    d = (got - expected + 32768) % 65536 - 32768
    return f"{abs(d)} {'more' if d > 0 else 'fewer'} {what} than the program made: the FPGA counted {got}, " \
           f"expected {expected} (modulo 65536)" if d else None


def assess(lines, counts):
    """Judges the program's report (the lines from the FPGA) and the FPGA's counts line
    ("C wwww rrrr pppp ssss gggg", or None). Returns the problems found and the number of reads the SOEB interlock paused (or None)."""
    starts = [i for i, line in enumerate(lines) if line == START]
    if not starts:
        return ["The program never started: no 'FPGA BUS CHECK' arrived from the FPGA"], None
    report = lines[starts[-1]:]
    problems, keys, rounds = [], None, None
    for i, (name, kind) in enumerate(STEPS):
        if i >= len(report):
            problems.append(f"The program stopped after '{report[-1]}': '{name}' never came")
            break
        line = report[i]
        if kind == "exact" and line != name:
            problems.append(f"Expected '{name}', got '{line}'")
        elif kind == "ok" and line != f"{name} OK":
            problems.append(f"{name}: got '{line}'" + (" (the ID reply or the status after it was wrong)"
                                                         if name == "ID" else
                                                         " (an empty reply queue must read $00, set UNDERFLOW, "
                                                         "and one status read must clear it)"))
        elif kind in ("count", "keys"):
            if not line.startswith(name + " "):
                problems.append(f"Expected '{name} nnnn', got '{line}'")
                continue
            n = int(line.split()[1 if kind == "keys" else -1], 16)
            if kind == "keys":
                keys, rounds = n, int(line.split()[3], 16)
                if n == 0:
                    problems.append("no keys arrived during the keyboard part: hold a key down from "
                                    f"'{HOLD}' until '{DONE}'")
            elif n:
                where = "with the keyboard interrupting" if name.startswith("KEYBOARD") else "in the echo passes"
                problems.append(f"{n} bytes read back wrong (or status errors) {where}")
    if counts is None:
        problems.append("No counts from the FPGA (its reply to '?')")
        return problems, None
    writes, reads, pauses, soeb_falls, _ = (int(field, 16) for field in counts.split()[1:])
    if keys and not soeb_falls:
        problems.append(f"the FPGA never saw SOEB fall, though the keyboard driver read {keys} keys: check PA4 "
                        "(VIA pin 6) to the control buffer's B6 (pin 13), and its A6 (pin 7) to Cmod pin 18")
    elif keys and not pauses:
        problems.append("no read was paused by a keyboard interrupt, so the interlock wasn't exercised: "
                        "run again, holding the key down until DONE")
    if rounds is not None and not problems:   # a complete, clean run: every transfer is accounted for
        exp_writes, exp_reads = expected_counts(report[:len(STEPS)], rounds)
        problems += [p for p in (difference(writes, exp_writes, "writes"), difference(reads, exp_reads, "reads")) if p]
    return problems, pauses


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--michael-port", help="Michael's serial port (default: as the upload tools choose it)")
    ap.add_argument("--fpga-port", help="the Cmod's serial port (default: auto-detect)")
    ap.add_argument("--timeout", type=float, default=60, help="seconds to wait for each part of the program")
    args = ap.parse_args()

    uart_check = board.serial_module()
    counts_lines = lambda lines: [line for line in lines if line.startswith("C ")]  # noqa: E731

    with uart_check.Serial(args.fpga_port or uart_check.find_port()) as ser:
        ser.flush_input()
        reader = board.LineReader(ser, "CFIEUHKD")
        ser.write(b"?")
        if not reader.wait_for(lambda lines: counts_lines(lines), 1.0):
            sys.exit("No reply from the FPGA: is the bus-check design loaded (make prog)?")

        rc = board.upload(PROGRAM, args.michael_port)
        if rc:
            sys.exit(f"Upload failed ({rc})")
        if reader.wait_for(lambda lines: HOLD in lines, args.timeout):
            print("Now hold a key down on Michael's keyboard (a letter), until the program says DONE ...")
            if reader.wait_for(lambda lines: DONE in lines, args.timeout):
                print("Done: you can let go of the key.")
        before = len(counts_lines(reader.snapshot()))
        ser.write(b"?")
        reader.wait_for(lambda lines: len(counts_lines(lines)) > before, 2.0)
        got = reader.snapshot()

    counts = counts_lines(got)[before] if len(counts_lines(got)) > before else None
    program = [line for line in got if not line.startswith("C ")]
    problems, pauses = assess(program, counts)
    if counts:
        _, writes, reads, _, soeb_falls, glitches = counts.split()
        print(f"The FPGA counted {int(writes, 16)} writes and {int(reads, 16)} reads (both modulo 65536), "
              f"{int(soeb_falls, 16)} falls of SOEB, {pauses} reads paused by the SOEB interlock, and "
              f"{int(glitches, 16)} glitches on E (filtered out).")
    if problems:
        print(f"FAIL: {len(problems)} problem(s):")
        print("\n".join("  " + p for p in problems))
        if START not in program:
            print("If Michael's LCD shows 'Ready', the upload didn't reach it: try\n"
                  "  python3 tools/upload/transfer.py --daemon stop   (then rerun)")
        print("Everything the program reported:")
        print("\n".join("  " + line for line in program[-12:]))
        sys.exit(1)
    print(f"PASS: every byte read back right, with and without the keyboard interrupting; {pauses} reads "
          "were paused by a keyboard interrupt and resumed correctly.")


if __name__ == "__main__":
    main()
