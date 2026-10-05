"""michael_graphic_text.s: types on the FPGA's text mode (stage 3 of docs/michael-fpga-bus-plan.md). Run on
the emulator with keys typed, its bus transfers (decoded into text operations and run on the text mode's model,
hardware/michael/fpga/text/text_screen.py) must make the screen the keys ask for: a reverse title on row 0;
characters where typed; Enter to the next line, scrolling the region (rows 1-19) at the bottom; Backspace
deleting; the arrows moving; Tab toggling reverse video; Esc clearing the region.

Run from the repo root:  python3 -m unittest discover -s tools/tests -v
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import michael_emulator  # noqa: E402
sys.path.insert(0, os.path.join(michael_emulator.ROOT, 'hardware', 'michael', 'fpga', 'text'))
from text_screen import TextScreen  # noqa: E402

PROGRAM = os.path.join(michael_emulator.ROOT, 'firmware', 'programs', 'michael', 'michael_graphic_text.s')
UP, DOWN, RIGHT, LEFT, ESC = b'\x1b[A', b'\x1b[B', b'\x1b[C', b'\x1b[D', b'\x1b'
TITLE = ' MICHAEL TEXT MODE  '
ARGUMENTS = {0x22: 2, 0x26: 1, 0x27: 1, 0x28: 2, 0x2A: 1, 0x2B: 1, 0x2C: 1, 0x2D: 1, 0x2E: 1, 0x2F: 1}


def screen_from(log):
    """The bus transfers from TEXT_ON on, run on the model."""
    s = TextScreen()
    calls = {0x20: s.text_on, 0x24: s.clear, 0x25: s.clear_eol, 0x29: s.region_reset, 0x22: s.goto, 0x26: s.insert,
             0x27: s.delete, 0x28: s.region, 0x2A: s.scroll_up, 0x2B: s.scroll_down, 0x2C: s.insert_lines,
             0x2D: s.delete_lines, 0x2E: s.set_cursor, 0x2F: s.video}
    cmd, args, on = None, [], False
    for line in log.split('\n'):
        if not line:
            continue
        kind, value = line.split()[0], int(line.split()[1], 16) if len(line.split()) > 1 else None
        if kind == 'C':
            cmd, args = value, []
            on = on or cmd == 0x20
            if on and cmd in calls and ARGUMENTS.get(cmd, 0) == 0:
                calls[cmd]()
        elif kind == 'D' and on:
            if cmd == 0x23:
                s.put(value)
            elif cmd in ARGUMENTS:
                args.append(value)
                if len(args) == ARGUMENTS[cmd]:
                    calls[cmd](*args)
    return s


@unittest.skipUnless(michael_emulator.AVAILABLE, 'vasm6502_oldstyle, gcc and make are needed')
class GraphicTextTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        michael_emulator.build_emulator()

    def type(self, keys):
        log, report = michael_emulator.run(program=PROGRAM, keys=keys, cycle_cap=60_000_000, key_interval=30)
        return screen_from(log), report

    def test_the_title_and_typing(self):
        s, report = self.type(b'Hi there\rsecond\x08\x08ND\r' + UP + b'X' + b'\tR\tn')
        self.assertEqual(s.text(0), TITLE)
        self.assertTrue(all(s.cell(0, c)[1] for c in range(20)), 'the title in reverse video')
        self.assertEqual([s.text(r).rstrip() for r in (1, 2, 3)], ['Hi there', 'XRnoND', ''])
        self.assertEqual([s.cell(2, c)[1] for c in range(3)], [False, True, False], 'Tab toggles reverse video')
        self.assertEqual((s.row, s.col, s.cursor), (2, 3, True))
        self.assertIn('TEXT MODE', report)

    def test_enter_at_the_bottom_scrolls_the_region(self):
        s, _ = self.type(b''.join(b'L%02d\r' % i for i in range(25)))
        self.assertEqual(s.text(0), TITLE)
        # 19 rows: the last 18 lines, then the row the last Enter scrolled in
        self.assertEqual([s.text(r).rstrip() for r in range(1, 20)], ['L%02d' % i for i in range(7, 25)] + [''])
        self.assertEqual((s.row, s.col), (19, 0))

    def test_a_long_line_wraps_and_the_arrows_stop_at_the_edges(self):
        s, _ = self.type(b'x' * 25 + UP * 5 + LEFT * 30 + b'<' + DOWN * 30 + RIGHT * 30 + b'>')
        self.assertEqual(s.text(1), '<' + 'x' * 19)
        self.assertEqual(s.text(2).rstrip(), 'xxxxx')
        self.assertEqual(s.text(19), ' ' * 19 + '>')

    def test_esc_clears_the_region(self):
        s, _ = self.type(b'one\rtwo' + ESC + b'three')
        self.assertEqual(s.text(0), TITLE)
        self.assertEqual([s.text(r).rstrip() for r in (1, 2)], ['three', ''])


if __name__ == '__main__':
    unittest.main()
