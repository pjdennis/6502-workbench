"""The text grid's RTL (../rtl/text_grid.v) against its model (text_screen.py): sequences of text operations,
directed and random, go through both; the grid, the cursor and the region must match, and every cell that
isn't blank must be marked dirty. Needs Icarus Verilog (iverilog, vvp), as `make test` has it.
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
from text_screen import TextScreen  # noqa: E402

RTL = [os.path.join(HERE, '..', 'rtl', f) for f in ('text_grid.v', 'fifo.v')]
ROWS, COLS = 20, 20
(TEXT_ON, TEXT_OFF, GOTO, PUT, CLEAR, CLEAR_EOL, INSERT, DELETE, REGION, REGION_RESET, SCROLL_UP, SCROLL_DOWN,
 INSERT_LINES, DELETE_LINES, CURSOR, VIDEO) = range(16)


def apply(model, op, a, b):
    calls = {TEXT_ON: lambda: model.text_on(), TEXT_OFF: lambda: None, GOTO: lambda: model.goto(a, b),
             PUT: lambda: model.put(a), CLEAR: model.clear, CLEAR_EOL: model.clear_eol,
             INSERT: lambda: model.insert(a), DELETE: lambda: model.delete(a), REGION: lambda: model.region(a, b),
             REGION_RESET: model.region_reset, SCROLL_UP: lambda: model.scroll_up(a),
             SCROLL_DOWN: lambda: model.scroll_down(a), INSERT_LINES: lambda: model.insert_lines(a),
             DELETE_LINES: lambda: model.delete_lines(a), CURSOR: lambda: model.set_cursor(a),
             VIDEO: lambda: model.video(a)}
    calls[op]()


class Simulator:
    def __init__(self):
        self.dir = tempfile.mkdtemp()
        self.vvp = os.path.join(self.dir, 'tb.vvp')
        subprocess.run(['iverilog', '-g2012', '-o', self.vvp, os.path.join(HERE, 'tb_text_grid.v'), *RTL],
                       check=True, capture_output=True, text=True)

    def run(self, ops):
        ops_file, out_file = os.path.join(self.dir, 'ops'), os.path.join(self.dir, 'out')
        with open(ops_file, 'w') as f:
            f.write(''.join(f'{op:x} {a:02x} {b:02x}\n' for op, a, b in ops))
        subprocess.run(['vvp', '-n', self.vvp, f'+ops={ops_file}', f'+out={out_file}'], check=True,
                       capture_output=True, text=True)
        with open(out_file) as f:
            lines = f.read().split('\n')
        cells = [[int(v, 16) for v in line.split()] for line in lines[:ROWS]]
        info = {line.split()[0]: line.split()[1:] for line in lines[ROWS:] if line}
        return cells, info

    def close(self):
        shutil.rmtree(self.dir)


def random_ops(rng, n):
    ops = [(TEXT_ON, 0, 0)]
    for _ in range(n):
        op = rng.choice([PUT] * 120 + [GOTO] * 10 + list(range(2, 16)) * 2)
        if op == PUT:
            a = rng.choice([0x08, 0x0A, 0x0D, 0x07, 0xC1]) if rng.random() < 0.1 else rng.randrange(0x20, 0x7F)
            ops.append((op, a, 0))
        elif op in (GOTO, REGION):
            ops.append((op, rng.choice([rng.randrange(ROWS), rng.randrange(256)]),
                        rng.choice([rng.randrange(COLS + 1), rng.randrange(256)])))
        elif op in (TEXT_ON, CLEAR) and rng.random() < 0.8:
            continue                                     # rarely, or they wipe everything
        else:
            big = rng.random() < 0.1
            ops.append((op, rng.choice([19, 20, 255]) if big else rng.choice([0, 1, 1, 1, 2, 3]), 0))
    return ops


@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'), 'Icarus Verilog is needed')
class TextGridTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sim = Simulator()

    @classmethod
    def tearDownClass(cls):
        cls.sim.close()

    def check(self, ops):
        model = TextScreen(ROWS, COLS)
        for op, a, b in ops:
            apply(model, op, a, b)
        cells, info = self.sim.run(ops)
        expected = [[ord(model.cell(r, c)[0]) | model.cell(r, c)[1] << 8 for c in range(COLS)] for r in range(ROWS)]
        self.assertEqual(cells, expected)
        self.assertEqual([int(v) for v in info['cursor']], [model.row, model.col, int(model.cursor)])
        self.assertEqual([int(v) for v in info['region']], [model.top, model.bottom])
        marks = info['marks'][0][::-1]   # bit row * COLS + col
        for r in range(ROWS):
            for c in range(COLS):
                if expected[r][c] != 0x20:
                    self.assertEqual(marks[r * COLS + c], '1', f'cell {r},{c} not marked')
        return info

    def test_text_on_writes_and_wraps(self):
        info = self.check([(TEXT_ON, 0, 0)] + [(PUT, ord(ch), 0) for ch in 'Hello, world! ' * 3])
        self.assertEqual(info['mode'], ['1'])

    def test_each_operation(self):
        rows = [(GOTO, r, 0) for r in range(ROWS)]
        fill = [op for r in range(ROWS) for op in [(GOTO, r, 0)] + [(PUT, 0x41 + (r + c) % 26, 0) for c in range(COLS)]]
        for ops in ([(CLEAR_EOL, 0, 0)], [(INSERT, 3, 0)], [(DELETE, 3, 0)], [(SCROLL_UP, 2, 0)],
                    [(SCROLL_DOWN, 2, 0)], [(INSERT_LINES, 2, 0)], [(DELETE_LINES, 2, 0)],
                    [(REGION, 3, 9), (SCROLL_UP, 4, 0)], [(REGION, 3, 9), (GOTO, 5, 2), (DELETE_LINES, 1, 0)],
                    [(VIDEO, 1, 0), (PUT, 0x7A, 0)], [(CURSOR, 1, 0)], [(CLEAR, 0, 0)], [(TEXT_OFF, 0, 0)]):
            with self.subTest(ops=ops):
                self.check([(TEXT_ON, 0, 0)] + fill + [(GOTO, 4, 7)] + ops)

    def test_random_sequences(self):
        for seed in range(25):
            with self.subTest(seed=seed):
                self.check(random_ops(random.Random(seed), 600))


if __name__ == '__main__':
    unittest.main()
