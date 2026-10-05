"""The text mode's renderer (../rtl/text_render.v), with the grid and the display queue as the bus design has
them: operations go in, the display's SPI bytes come out, and a model panel (ili9341.py) turns them into
pixels. Every cell on the panel must show what the model (text_screen.py) holds: its character from the font,
inverted for reverse video, with the cursor's bottom two rows inverted where it shows. A full screen takes
about 18 s to simulate, so most tests use a grid of 6 rows of 8; one uses the real 20 by 20. Needs Icarus
Verilog, as `make test` has it (which also generates the font, build/font_12x16.vh).
"""
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', '..', '..', '..', 'tools'))
import font_12x16  # noqa: E402
from ili9341 import Panel, MADCTL, VSCRSADD  # noqa: E402
from text_screen import TextScreen  # noqa: E402
from test_text_grid import (TEXT_ON, TEXT_OFF, GOTO, PUT, CLEAR, CLEAR_EOL, INSERT, DELETE, REGION,  # noqa: E402
                            REGION_RESET, SCROLL_UP, SCROLL_DOWN, INSERT_LINES, DELETE_LINES, CURSOR, VIDEO,
                            apply, random_ops)
from ili9341 import RAMWR  # noqa: E402

RTL_DIR = os.path.join(HERE, '..', 'rtl')
RTL = [os.path.join(RTL_DIR, f) for f in ('text_grid.v', 'text_render.v', 'display_spi.v', 'fifo.v')]
FONT_VH = os.path.join(HERE, '..', 'build', 'font_12x16.vh')
SMALL = (6, 8)
WAIT = 0x10   # the testbench waits until everything is idle
WORDS = font_12x16.fpga_words(font_12x16.read_source())


def expected_cell(model, row, col):
    char, reverse = model.cell(row, col)
    code = ord(char) if ord(char) < 0x80 else 0
    cursor = model.cursor and (row, col) == (model.row, model.col)
    return [WORDS[code << 4 | x] ^ (0xFFFF if reverse else 0) ^ (0xC000 if cursor else 0) for x in range(12)]


class Simulator:
    def __init__(self, rows, cols):
        self.rows, self.cols = rows, cols
        self.dir = tempfile.mkdtemp()
        self.vvp = os.path.join(self.dir, 'tb.vvp')
        subprocess.run(['iverilog', '-g2012', '-I', RTL_DIR, f'-Ptb_text_render.ROWS={rows}',
                        f'-Ptb_text_render.COLS={cols}', '-o', self.vvp, os.path.join(HERE, 'tb_text_render.v'),
                        *RTL], check=True, capture_output=True, text=True)

    def run(self, ops):
        ops_file, spi_file = os.path.join(self.dir, 'ops'), os.path.join(self.dir, 'spi')
        with open(ops_file, 'w') as f:
            f.write(''.join(f'{op:x} {a:02x} {b:02x}\n' for op, a, b in ops))
        subprocess.run(['vvp', '-n', self.vvp, f'+ops={ops_file}', f'+spi={spi_file}'], check=True,
                       capture_output=True, text=True)
        panel = Panel()
        panel.cells_drawn = 0
        with open(spi_file) as f:
            for line in f:
                dc, byte = line.split()
                panel.receive(int(dc), int(byte, 16))
                panel.cells_drawn += line == f'0 {RAMWR:02x}\n'
        return panel

    def close(self):
        shutil.rmtree(self.dir)


@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp') and os.path.exists(FONT_VH),
                     'Icarus Verilog and the generated font (make test) are needed')
class TextRenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sim, cls.full = Simulator(*SMALL), Simulator(20, 20)

    @classmethod
    def tearDownClass(cls):
        cls.sim.close()
        cls.full.close()

    def check(self, ops, sim=None):
        sim = sim or self.sim
        model = TextScreen(sim.rows, sim.cols)
        for op, a, b in ops:
            if op != WAIT:
                apply(model, op, a, b)
        panel = sim.run(ops)
        wrong = [(r, c) for r in range(sim.rows) for c in range(sim.cols)
                 if panel.cell(r, c, shown=True) != expected_cell(model, r, c)
                 or panel.cell(model.memory_row(r), c) != expected_cell(model, r, c)]   # where board_check.py reads
        self.assertEqual(wrong, [], f'cells that differ (row, column); the model has {model.text(wrong[0][0])!r} '
                                    f'in row {wrong[0][0]}' if wrong else '')
        return panel

    def test_text_on_sets_the_orientation_and_draws_every_cell(self):
        """At the real size, 20 by 20: rows past 255 pixels need the window's high bytes."""
        panel = self.check([(TEXT_ON, 0, 0)] + [(PUT, ord(ch), 0) for ch in 'Hello, world!' * 30] +
                           [(GOTO, 19, 17), (PUT, ord('Z'), 0)], self.full)
        self.assertEqual(panel.registers[MADCTL], [0xA8])
        self.assertEqual(panel.registers[VSCRSADD], [0x00, 0x00])

    def test_reverse_video_and_the_cursor(self):
        self.check([(TEXT_ON, 0, 0), (PUT, ord('a'), 0), (VIDEO, 1, 0), (PUT, ord('b'), 0), (VIDEO, 0, 0),
                    (PUT, ord('c'), 0), (GOTO, 5, 7), (CURSOR, 1, 0), (GOTO, 6, 8)])

    def test_a_full_screen_then_shifts(self):
        rows, cols = SMALL
        fill = [op for r in range(rows) for op in [(GOTO, r, 0)] + [(PUT, 0x41 + (r + c) % 26, 0) for c in range(cols)]]
        self.check([(TEXT_ON, 0, 0)] + fill + [(GOTO, 1, 2), (INSERT, 3, 0), (GOTO, 2, 2), (DELETE, 4, 0),
                                               (GOTO, 3, 5), (CLEAR_EOL, 0, 0), (REGION, 1, 4), (SCROLL_UP, 2, 0),
                                               (GOTO, 2, 1), (INSERT_LINES, 1, 0), (CURSOR, 1, 0)])

    def test_region_scrolls_move_the_picture(self):
        """The hardware scroll moves the region's picture, so a scroll draws only the rows that come in blank
        (and the cursor's cells), not the whole region."""
        rows, cols = SMALL
        fill = [op for r in range(rows) for op in [(GOTO, r, 0)] + [(PUT, 0x41 + (r * 3 + c) % 26, 0) for c in range(cols)]]
        start = [(TEXT_ON, 0, 0)] + fill + [(REGION, 1, 4), (WAIT, 0, 0)]
        drawn = self.check(start).cells_drawn
        for ops, most in (([(SCROLL_UP, 1, 0)], cols), ([(SCROLL_DOWN, 2, 0)], 2 * cols),
                          ([(SCROLL_UP, 1, 0), (SCROLL_UP, 2, 0), (SCROLL_DOWN, 1, 0)], 4 * cols),
                          ([(GOTO, 1, 0), (DELETE_LINES, 1, 0)], cols), ([(GOTO, 1, 0), (INSERT_LINES, 1, 0)], cols)):
            with self.subTest(ops=ops):
                self.assertLessEqual(self.check(start + ops).cells_drawn - drawn, most + 2)

    def test_only_cells_that_change_are_drawn(self):
        """A cell written with what it already holds, or a blank moved onto a blank, isn't drawn again; nor are
        the cells a hidden cursor passes."""
        rows, cols = SMALL
        text = [[0x41 + (r * 7 + c) % 26 for c in range(cols)] for r in range(3)]   # rows 3 on stay blank
        fill = [op for r in range(3) for op in [(GOTO, r, 0)] + [(PUT, ch, 0) for ch in text[r]]]
        start = [(TEXT_ON, 0, 0)] + fill + [(WAIT, 0, 0)]
        drawn = self.check(start).cells_drawn
        for ops, most in (([(GOTO, 1, 0)] + [(PUT, ch, 0) for ch in text[1]], 0),
                          ([(GOTO, 1, 0), (INSERT_LINES, 1, 0)], 3 * cols),   # rows 1-3 change; 4 and 5 stay blank
                          ([(GOTO, 0, 0), (DELETE_LINES, 1, 0)], 3 * cols)):  # rows 0-2 change
            with self.subTest(ops=ops):
                self.assertLessEqual(self.check(start + ops).cells_drawn - drawn, most)

    def test_changing_the_region_after_a_scroll(self):
        rows, cols = SMALL
        fill = [op for r in range(rows) for op in [(GOTO, r, 0)] + [(PUT, 0x61 + (r * 5 + c) % 26, 0) for c in range(cols)]]
        self.check([(TEXT_ON, 0, 0)] + fill + [(REGION, 1, 4), (SCROLL_UP, 2, 0), (REGION, 2, 5), (SCROLL_DOWN, 1, 0),
                                               (REGION_RESET, 0, 0), (SCROLL_UP, 1, 0), (CURSOR, 1, 0), (GOTO, 3, 3)])

    def test_text_off_stops_drawing(self):
        panel = self.sim.run([(TEXT_ON, 0, 0), (TEXT_OFF, 0, 0)] + [(PUT, ord('x'), 0)] * 5)
        written = sum(p is not None for page in panel.pixels for p in page)
        self.assertLess(written, SMALL[0] * SMALL[1] * 12 * 16)   # not every cell: TEXT_OFF stopped it

    def test_random_sequences(self):
        for seed in range(6):
            with self.subTest(seed=seed):
                self.check(random_ops(random.Random(seed), 200, *SMALL))


if __name__ == '__main__':
    unittest.main()
