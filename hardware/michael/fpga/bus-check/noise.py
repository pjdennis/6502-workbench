#!/usr/bin/env python3
"""Measures switching noise on the FPGA bus's E: runs firmware/programs/michael/michael_fpga_bus_noise.s
(port B switching between $00 and $FF, E held low) and counts, per second, the glitches on E (which the
bus's filter rejects) and the writes (noise that got through it, since Michael makes none), first with the
data buffer working as usual, then held off ('1' to the bus-check design), so that only Michael's side of
the buffer switches. Leaves Michael in the idle program. Needs the bus-check design loaded (make noise).

  noise.py [--seconds S] [--michael-port DEV] [--fpga-port DEV]
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import board  # noqa: E402
from check import request_counts  # noqa: E402

PROGRAM = os.path.join(board.REPO, "firmware", "programs", "michael", "michael_fpga_bus_noise.s")


def counts(ser, reader):
    """From the design's counts: the glitches (bounces and glitches together) and the writes."""
    c = request_counts(ser, reader)
    if c is None:
        sys.exit("No counts from the FPGA: is the bus-check design loaded (make prog)?")
    return c["glitches"] + c["bounces"], c["writes"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seconds", type=float, default=5, help="how long to count in each setting")
    ap.add_argument("--michael-port", help="Michael's serial port (default: as the upload tools choose it)")
    ap.add_argument("--fpga-port", help="the Cmod's serial port (default: auto-detect)")
    args = ap.parse_args()

    uart_check = board.serial_module()
    with uart_check.Serial(args.fpga_port or uart_check.find_port()) as ser:
        ser.flush_input()
        reader = board.LineReader(ser, "C")
        ser.write(b"0")
        counts(ser, reader)
        if board.upload(PROGRAM, args.michael_port, wait=True):
            sys.exit("Upload failed")
        time.sleep(board.IDLE_START)
        for setting, label in ((b"0", "buffer working"), (b"1", "buffer held off"), (b"0", "buffer working"),
                               (b"1", "buffer held off")):
            ser.write(setting)
            start = counts(ser, reader)
            time.sleep(args.seconds)
            glitches, writes = ((end - begin) % 65536 / args.seconds for begin, end in zip(start, counts(ser, reader)))
            print(f"  {label:16s} {glitches:8.0f} glitches on E and {writes:5.1f} writes per second", flush=True)
        ser.write(b"0")
    board.idle(args.michael_port)


if __name__ == "__main__":
    main()
