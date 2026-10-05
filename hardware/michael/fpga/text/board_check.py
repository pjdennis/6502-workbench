#!/usr/bin/env python3
"""Checks text mode on the board, without anyone looking at the display: draws a screen through the bus
design's debug port, then reads the cells back out of the ILI9341's memory with the display-probe design,
which loads without resetting the display, and compares them with the model (text_screen.py). Then it
loads the bus design again and redraws the screen, so the display shows it as before.

  board_check.py [--all] [--fpga-port DEV]

Michael is put in the idle program first. A cell takes about a second to read; by default the check reads a
sample (the first and last rows, and the first columns of the others), --all reads all 400.
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FPGA = os.path.join(HERE, '..')
sys.path[:0] = [HERE, FPGA, os.path.join(FPGA, 'bus'), os.path.join(FPGA, 'display-probe'),
                os.path.join(FPGA, '..', '..', '..', 'tools')]
import board  # noqa: E402
import debug  # noqa: E402
import font_12x16  # noqa: E402
from text_screen import ScreenPort  # noqa: E402

WORDS = font_12x16.fpga_words(font_12x16.read_source())
CASET, PASET, RAMRD = 0x2A, 0x2B, 0x2E


def load(design):
    subprocess.run(['make', '-s', '-C', os.path.join(FPGA, design), 'prog'], check=True, stdout=subprocess.DEVNULL)


def expected(screen, row, col, cursor_shown):
    char, reverse = screen.cell(row, col)
    code = ord(char)   # every code the grid holds has its glyph
    cursor = cursor_shown and screen.cursor and (row, col) == (screen.row, screen.col)
    return [WORDS[code << 4 | x] ^ (0xFFFF if reverse else 0) ^ (0xC000 if cursor else 0) for x in range(12)]


def read_cell(p, row, col):
    """The memory cell's 12 columns of 16 pixels (top in bit 0), lit or not, read with RAMRD: a dummy byte,
    then three bytes (red, green, blue) a pixel, in the order they were written. (The hardware scroll decides
    which memory row a text row is drawn in: screen.memory_row.)"""
    y0, x0 = row * 16, col * 12
    p.command(CASET, y0 >> 8, y0 & 0xFF, (y0 + 15) >> 8, (y0 + 15) & 0xFF)
    p.command(PASET, x0 >> 8, x0 & 0xFF, (x0 + 11) >> 8, (x0 + 11) & 0xFF)
    p.ctrl(cs=0, dc=0)
    p.write([RAMRD])
    p.ctrl(cs=0, dc=1)
    p.read_bits(8)
    pixels = p.read_bits(192 * 24)
    p.ctrl(cs=1)
    lit = [(pixels >> (24 * (191 - i) + 16)) & 0xFC != 0 for i in range(192)]
    return [sum(lit[x * 16 + y] << y for y in range(16)) for x in range(12)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--all', action='store_true', help='read every cell (about 7 minutes)')
    ap.add_argument('--fpga-port', help="the Cmod's serial port (default: auto-detect)")
    args = ap.parse_args()

    model = ScreenPort()
    debug.text_demo(model)
    screen = model.screen
    cells = [(r, c) for r in range(20) for c in range(20)] if args.all else \
        [(r, c) for r in (0, 19) for c in range(20)] + [(r, c) for r in range(1, 19) for c in range(4)]

    uart = board.serial_module()
    port_name = args.fpga_port or uart.find_port()
    board.idle()
    load('bus')
    with uart.Serial(port_name) as ser:
        ser.flush_input()
        debug.text_demo(debug.DebugPort(ser))
    load('display-probe')
    wrong = []
    with uart.Serial(port_name) as ser:
        ser.flush_input()
        p = debug_probe(ser)
        for row, col in cells:
            got = read_cell(p, screen.memory_row(row), col)
            if got not in (expected(screen, row, col, True), expected(screen, row, col, False)):   # blinking
                wrong.append((row, col))
                print(f'cell ({row}, {col}), {screen.cell(row, col)[0]!r}: got {[hex(w) for w in got]}', flush=True)
    load('bus')
    with uart.Serial(port_name) as ser:
        ser.flush_input()
        debug.text_demo(debug.DebugPort(ser))
    if wrong:
        sys.exit(f'FAIL: {len(wrong)} of {len(cells)} cells differ from the model')
    print(f'PASS: all {len(cells)} cells read back as the model has them')


def debug_probe(ser):
    import probe
    p = probe.Probe(ser)
    p.sync()
    p.speed(6)   # 1 MHz: reads are slower than writes
    return p


if __name__ == '__main__':
    main()
