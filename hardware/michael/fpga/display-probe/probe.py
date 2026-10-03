#!/usr/bin/env python3
"""Checks the ILI9341 display and its wiring through the display-probe FPGA design (`make probe`).

Resets the display, reads its status and ID registers back over SDO (normal wiring, then with MOSI and SCK
swapped), then initialises it and fills the screen red, all from the FPGA, without Michael.
"""
import os
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


def read_all(p):
    p.hardware_reset()
    r = {"04 RDDID (dummy + 24 bits)": f"{p.read_register(0x04, 25):07X}",
         "09 RDDST (dummy + 32 bits)": f"{p.read_register(0x09, 33):09X}",
         "0A RDDPM (9 bits)": f"{p.read_register(0x0A, 9):03X}",
         "0C RDPIXFMT (9 bits)": f"{p.read_register(0x0C, 9):03X}"}
    id4 = []
    for i in (1, 2, 3):
        p.command(0xD9, 0x10 + i)
        id4.append(f"{p.read_register(0xD3, 8):02X}")
    r["D3 ID4 via D9 (expect 00 93 41)"] = " ".join(id4)
    return r


def main():
    with uart_check.Serial(uart_check.find_port()) as ser:
        ser.flush_input()
        p = Probe(ser)
        p.sync()
        p.speed(6)  # 1 MHz
        for swap in (False, True):
            p.swap = swap
            print(f"\nRegisters read back, {'MOSI and SCK swapped' if swap else 'wiring as documented'}:")
            for name, value in read_all(p).items():
                print(f"  {name:34s} {value}")
        p.swap = False
        print("\nAll ones means SDO stays high (no reply); all zeros means it stays low. An ILI9341 after reset")
        print("typically reads 0A as 08 (or 010 with a dummy bit), and ID4 as 00 93 41.")

        print("\nInitialising the display and filling it red (2 MHz SPI, wiring as documented) ...")
        p.hardware_reset()
        p.speed(3)
        p.command(0x01); p.sync(); time.sleep(0.15)          # software reset
        p.command(0x11); p.sync(); time.sleep(0.15)          # sleep out
        p.command(0x3A, 0x55)                                # 16-bit pixels
        p.command(0x36, 0x48)                                # memory access control
        p.command(0x29); p.sync(); time.sleep(0.02)          # display on
        p.command(0x2A, 0x00, 0x00, 0x00, 0xEF)              # columns 0-239
        p.command(0x2B, 0x00, 0x00, 0x01, 0x3F)              # rows 0-319
        p.ctrl(cs=0, dc=0); p.write([0x2C]); p.ctrl(cs=0, dc=1)
        p.fill(240 * 320, 0xF8, 0x00)                        # red
        p.ctrl(cs=1)
        p.sync()
        p.speed(6)
        print(f"Done. 0A RDDPM now reads {p.read_register(0x0A, 9):03X} (an initialised display: 9C, or 138 with a dummy bit).")
        print("The screen should be solid red.")


if __name__ == "__main__":
    main()
