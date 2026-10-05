"""michael_graphic_text.s: types on the FPGA's text mode (stage 3 of docs/michael-fpga-bus-plan.md). Run on
the emulator with keys typed, its bus transfers (decoded into text operations and run on the text mode's model,
hardware/michael/fpga/text/text_screen.py) must make the screen the keys ask for: a reverse title on row 0;
characters inserted where typed, the region (rows 1-19) scrolling when they run off the bottom; Enter opening a
line below, or scrolling the region at the bottom; Backspace deleting; Delete deleting the line; the arrows
moving; Tab toggling reverse video; Esc clearing the region; Page Up and Page Down stepping the backlight's
brightness (BACKLIGHT, $13) up and down, halving it at each step down.

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
UP, DOWN, RIGHT, LEFT, ESC, DELETE = b'\x1b[A', b'\x1b[B', b'\x1b[C', b'\x1b[D', b'\x1b', b'\x1b[3~'
PAGE_UP, PAGE_DOWN = b'\x1b[5~', b'\x1b[6~'
TITLE = ' MICHAEL TEXT MODE  '
ARGUMENTS = {0x22: 2, 0x26: 1, 0x27: 1, 0x28: 2, 0x2A: 1, 0x2B: 1, 0x2C: 1, 0x2D: 1, 0x2E: 1, 0x2F: 1}


def backlight_levels(log):
    """The levels BACKLIGHT ($13) was sent."""
    lines, levels = [line.split() for line in log.split('\n') if line], []
    for (kind, value, *_), following in zip(lines, lines[1:]):
        if (kind, int(value, 16)) == ('C', 0x13) and following[0] == 'D':
            levels.append(int(following[1], 16))
    return levels


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
        s, report, _ = self.type_with_log(keys)
        return s, report

    def type_with_log(self, keys):
        log, report = michael_emulator.run(program=PROGRAM, keys=keys, cycle_cap=60_000_000, key_interval=30)
        return screen_from(log), report, log

    def test_the_title_and_typing(self):
        s, report = self.type(b'Hi there\rsecond\x08\x08ND\r' + UP + b'X' + b'\tR\tn')
        self.assertEqual(s.text(0), TITLE)
        self.assertTrue(all(s.cell(0, c)[1] for c in range(20)), 'the title in reverse video')
        self.assertEqual([s.text(r).rstrip() for r in (1, 2, 3)], ['Hi there', 'XRnsecoND', ''])   # typed in front
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
        s, _ = self.type(b'x' * 25 + UP * 5 + LEFT * 30 + b'<' + DOWN * 30 + RIGHT * 30)
        self.assertEqual(s.text(1), '<' + 'x' * 19)
        self.assertEqual(s.text(2).rstrip(), 'xxxxx')
        self.assertEqual((s.row, s.col), (19, 19))

    def test_typing_inserts_and_the_end_of_the_line_drops_off(self):
        s, _ = self.type(b'abcdef' + LEFT * 3 + b'XY\r' + b'y' * 20 + UP + b'Z')
        self.assertEqual([s.text(r).rstrip() for r in (1, 2)], ['abcXYdef', 'Z' + 'y' * 19])

    def test_typing_off_the_bottom_scrolls_the_region(self):
        s, _ = self.type(b'top' + DOWN * 30 + LEFT * 3 + b'y' * 25)
        self.assertEqual(s.text(0), TITLE)
        self.assertEqual([s.text(r).rstrip() for r in (1, 18, 19)], ['', 'y' * 20, 'y' * 5])
        self.assertEqual((s.row, s.col), (19, 5))

    def test_enter_opens_a_line_below(self):
        s, _ = self.type(b'one\rthree' + UP + b'\rtwo')
        self.assertEqual([s.text(r).rstrip() for r in (1, 2, 3, 4)], ['one', 'two', 'three', ''])

    def test_delete_deletes_the_line(self):
        s, _ = self.type(b'one\rtwo\rthree\rfour' + UP * 2 + DELETE + UP + DELETE + b'X')
        self.assertEqual([s.text(r).rstrip() for r in (1, 2, 3)], ['Xthree', 'four', ''])
        self.assertEqual((s.row, s.col), (1, 1))

    def test_esc_clears_the_region(self):
        s, _ = self.type(b'one\rtwo' + ESC + b'three')
        self.assertEqual(s.text(0), TITLE)
        self.assertEqual([s.text(r).rstrip() for r in (1, 2)], ['three', ''])

    def test_page_up_and_down_step_the_brightness(self):
        s, _, log = self.type_with_log(PAGE_UP + PAGE_DOWN * 3 + PAGE_UP + PAGE_DOWN * 9 + b'b')
        # Fully on at the start; no further than 255 or 0
        self.assertEqual(backlight_levels(log), [255, 127, 63, 31, 63, 31, 15, 7, 3, 1, 0])
        self.assertEqual(s.text(1).rstrip(), 'b', 'the keys type nothing')


if __name__ == '__main__':
    unittest.main()
