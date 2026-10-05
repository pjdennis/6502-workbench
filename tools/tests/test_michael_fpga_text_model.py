"""The emulator's model of the FPGA's text mode (emulator/chips/fpga_text.c, behind fpga_bus.c) against the
text mode's own model (hardware/michael/fpga/text/text_screen.py, which the RTL is tested against): random
sequences of text commands, sent by a Michael program through fpga_bus.inc, must leave the same grid,
reverse cells and cursor in the emulator's report as in the model.

Run from the repo root:  python3 -m unittest discover -s tools/tests -v
"""
import os
import random
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import michael_emulator  # noqa: E402
sys.path.insert(0, os.path.join(michael_emulator.ROOT, 'hardware', 'michael', 'fpga', 'text'))
from test_text_grid import apply, random_ops  # noqa: E402
from text_screen import TextScreen  # noqa: E402

ARGUMENTS = {2: 2, 3: 1, 6: 1, 7: 1, 8: 2, 10: 1, 11: 1, 12: 1, 13: 1, 14: 1, 15: 1}   # op (code - $20): bytes


def program(ops):
    lines = []
    for op, a, b in ops:
        lines += [f'  lda #${0x20 + op:02x}', '  jsr fb_command']
        lines += [f'  lda #${v:02x}\n  jsr fb_data' for v in (a, b)[:ARGUMENTS.get(op, 0)]]
    return '\n'.join(['  .include base_config_v2.inc', '  .org PROGRAM_LOAD_ADDRESS', 'start:', '  ldx #$ff',
                      '  txs', '  jsr fb_initialize'] + lines + ['  stp', '  .include fpga_bus.inc'])


def report_screen(report):
    lines = report.split('\n')
    i = next(n for n, line in enumerate(lines) if line.startswith('michael: fpga text:'))
    head = lines[i].split()
    row, col = (int(v) for v in head[5].split(','))
    text = [line.strip()[1:-1] for line in lines[i + 1:i + 21]]
    reverse = [' ' * 20] * 20
    if i + 21 < len(lines) and lines[i + 21].startswith('michael: fpga text-reverse:'):
        reverse = [line.strip()[1:-1] for line in lines[i + 22:i + 42]]
    return text, reverse, (row, col, head[6] == 'shown')


@unittest.skipUnless(michael_emulator.AVAILABLE, 'vasm6502_oldstyle, gcc and make are needed')
class EmulatorTextModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        michael_emulator.build_emulator()

    def check(self, ops):
        model = TextScreen()
        for op, a, b in ops:
            apply(model, op, a, b)
        _, report = michael_emulator.run(source=program(ops), cycle_cap=20_000_000)
        text, reverse, cursor = report_screen(report)
        shown = lambda ch: ch if ' ' <= ch <= '~' else '?'   # noqa: E731
        self.assertEqual(text, [''.join(shown(model.cell(r, c)[0]) for c in range(20)) for r in range(20)], report)
        self.assertEqual(reverse, [''.join('#' if model.cell(r, c)[1] else ' ' for c in range(20)) for r in range(20)])
        self.assertEqual(cursor, (model.row, model.col, model.cursor))

    def test_a_full_screen_then_each_operation(self):
        """Written straight through: every row wraps, and the bottom row stops past its end."""
        fill = [(0, 0, 0)] + [(3, 0x41 + i % 26, 0) for i in range(405)]
        for ops in ([], [(2, 4, 7), (6, 3, 0)], [(2, 4, 7), (7, 3, 0)], [(2, 4, 7), (5, 0, 0)],
                    [(8, 3, 15), (10, 2, 0)], [(8, 3, 15), (11, 2, 0)], [(2, 6, 1), (12, 2, 0)],
                    [(2, 6, 1), (13, 2, 0)], [(15, 1, 0), (2, 0, 0), (3, 0x7A, 0)], [(14, 1, 0)], [(4, 0, 0)]):
            with self.subTest(ops=ops):
                self.check(fill + ops)

    def test_random_sequences(self):
        for seed in range(30):
            with self.subTest(seed=seed):
                self.check(random_ops(random.Random(seed), 300))


if __name__ == '__main__':
    unittest.main()
