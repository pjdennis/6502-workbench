#!/usr/bin/env python3
"""Checks the ILI9341 display and its wiring through the display-probe FPGA design (`make probe`).

Resets the display and reads its status and ID registers back over SDO (normal wiring, then with MOSI and SCK
swapped). Then initialises it exactly as Michael's driver does (gd_prepare_vertical, with INIT_COMMANDS read
from graphics_display.inc) and cycles the screen through red, green, blue, black and white, 3 s each.
All from the FPGA, without Michael.

  probe.py [--cycles N] [--speed HALF]
"""
import argparse
import os
import re
import sys
import time

KIT = os.environ.get("FPGA_KIT") or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                 "..", "..", "..", "..", "..", "fpga-toolchain-research")
sys.path.insert(0, os.path.join(KIT, "scripts"))
import uart_check  # noqa: E402


class Probe:
    def __init__(self, ser):
        self.ser, self.swap = ser, False

    def _reply(self):
        line = self.ser.readline(time.monotonic() + 3).decode(errors="replace").strip()
        return line[line.find("K") if "K" in line else line.find("R"):]

    def sync(self):
        self.ser.write(b"\x06")
        if self._reply() != "K00000000":
            raise RuntimeError("no sync reply from the display-probe design (is it loaded?)")

    def ctrl(self, cs=1, dc=1, reset=1, backlight=1):
        self.ser.write(bytes([3, cs | dc << 1 | reset << 2 | backlight << 3 | self.swap << 4]))

    def speed(self, half):
        self.ser.write(bytes([4, half]))

    def write(self, data):
        for i in range(0, len(data), 255):
            chunk = data[i:i + 255]
            self.ser.write(bytes([1, len(chunk)]) + bytes(chunk))

    def read_bits(self, n):
        value = 0
        while n:
            k = min(n, 32)
            self.ser.write(bytes([2, k]))
            value = value << k | int(self._reply()[1:], 16)
            n -= k
        return value

    def command(self, cmd, *data):
        self.ctrl(cs=0, dc=0); self.write([cmd])
        if data:
            self.ctrl(cs=0, dc=1); self.write(list(data))
        self.ctrl(cs=1)

    def read_register(self, cmd, nbits):
        self.ctrl(cs=0, dc=0); self.write([cmd])
        self.ctrl(cs=0, dc=1)
        value = self.read_bits(nbits)
        self.ctrl(cs=1)
        return value

    def fill(self, count, b1, b0):
        self.ser.write(bytes([5, count >> 16 & 0xFF, count >> 8 & 0xFF, count & 0xFF, b1, b0]))

    def hardware_reset(self):
        self.ctrl(reset=0); self.sync(); time.sleep(0.02)
        self.ctrl(reset=1); self.sync(); time.sleep(0.15)


DRIVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..",
                      "firmware", "lib", "graphics", "graphics_display.inc")


def _driver_lines():
    with open(DRIVER) as f:
        return [line.split(";")[0].strip() for line in f]


def _number(tok):
    return int(tok[1:], 16) if tok[0] == "$" else int(tok[1:], 2) if tok[0] == "%" else int(tok)


def driver_constants():
    """NAME = value definitions from the display driver (graphics_display.inc)."""
    names = {}
    for line in _driver_lines():
        m = re.match(r"(\w+)\s*=\s*(\$[0-9a-fA-F]+|%[01]+|\d+)$", line)
        if m:
            names[m[1]] = _number(m[2])
    return names


def michael_init_commands():
    """The driver's INIT_COMMANDS table as (command, parameters, delay after) tuples, read as gd_initialize
    reads it: command, then a count whose bit 7 asks for a 150 ms delay, then the parameters."""
    names, data, inside = driver_constants(), [], False
    for line in _driver_lines():
        if line.startswith("INIT_COMMANDS:"):
            inside = True
        elif inside and line.startswith(".byte"):
            for tok in line[5:].split(","):
                tok = tok.strip()
                data.append(names[tok] if tok in names else _number(tok))
        elif inside and line:
            break
    cmds, i = [], 0
    while data[i] != 0:
        cmd, count = data[i], data[i + 1]
        n = count & 0x7F
        cmds.append((cmd, data[i + 2:i + 2 + n], bool(count & 0x80)))
        i += 2 + n
    return cmds


def michael_prepare(p, half):
    """gd_prepare_vertical, step for step: gd_reset, gd_initialize, MADCTL, gd_clear_screen."""
    names = driver_constants()
    p.ctrl(reset=1); p.sync(); time.sleep(0.01)
    p.ctrl(reset=0); p.sync(); time.sleep(0.01)
    p.ctrl(reset=1); p.sync(); time.sleep(0.12)
    p.speed(half)
    for cmd, params, delay in michael_init_commands():
        p.command(cmd, *params)
        if delay:
            p.sync(); time.sleep(0.15)
    p.command(names["ILI9341_MADCTL"],
              names["ILI9341_MADCTL_MY"] | names["ILI9341_MADCTL_MV"] | names["ILI9341_MADCTL_BGR"])
    p.command(names["ILI9341_DISPOFF"])
    fill_screen(p, 0x00, 0x00)
    p.command(names["ILI9341_DISPON"])
    p.sync()


def fill_screen(p, b1, b0):
    """Landscape, as gd_prepare_vertical leaves it: 320 columns by 240 rows."""
    p.command(0x2A, 0x00, 0x00, 0x01, 0x3F)
    p.command(0x2B, 0x00, 0x00, 0x00, 0xEF)
    p.ctrl(cs=0, dc=0); p.write([0x2C]); p.ctrl(cs=0, dc=1)
    p.fill(320 * 240, b1, b0)
    p.ctrl(cs=1)
    p.sync()


def read_all(p):
    p.hardware_reset()
    r = {"04 RDDID (dummy + 24 bits)": f"{p.read_register(0x04, 25):07X}",
         "09 RDDST (dummy + 32 bits)": f"{p.read_register(0x09, 33):09X}",
         "0A RDDPM": f"{p.read_register(0x0A, 9) >> 1:02X}",
         "0C RDPIXFMT": f"{p.read_register(0x0C, 9) >> 1:02X}"}
    id4 = []
    for i in (1, 2, 3):
        p.command(0xD9, 0x10 + i)
        id4.append(f"{p.read_register(0xD3, 8):02X}")
    r["D3 ID4 via D9 (expect 00 93 41)"] = " ".join(id4)
    return r


COLOURS = (("red", 0xF8, 0x00), ("green", 0x07, 0xE0), ("blue", 0x00, 0x1F), ("black", 0, 0), ("white", 0xFF, 0xFF))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", type=int, default=2, help="times through the colour cycle (3 s per colour)")
    ap.add_argument("--speed", type=int, default=1, help="SCK half period in 12 MHz clocks (1 = 6 MHz, as Michael)")
    args = ap.parse_args()
    with uart_check.Serial(uart_check.find_port()) as ser:
        ser.flush_input()
        p = Probe(ser)
        p.sync()
        p.speed(6)  # reads at 1 MHz
        for swap in (False, True):
            p.swap = swap
            print(f"\nRegisters read back, {'MOSI and SCK swapped' if swap else 'wiring as documented'}:")
            for name, value in read_all(p).items():
                print(f"  {name:34s} {value}")
        p.swap = False
        print("\nAll ones means SDO stays high (no reply); all zeros means it stays low. After reset an ILI9341")
        print("reads 0A as 08 and ID4 as 00 93 41.")

        print(f"\nInitialising exactly as Michael's gd_prepare_vertical does ({12 / (2 * args.speed):g} MHz SPI) ...")
        michael_prepare(p, args.speed)
        p.speed(6)
        print(f"Done: power mode {p.read_register(0x0A, 9) >> 1:02X} (9C = awake, display on); the screen is cleared to black.")
        for _ in range(args.cycles):
            for name, b1, b0 in COLOURS:
                p.speed(args.speed)
                fill_screen(p, b1, b0)
                print(f"  {time.strftime('%T')} {name}", flush=True)
                time.sleep(3)


if __name__ == "__main__":
    main()
