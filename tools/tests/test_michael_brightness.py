"""michael_graphic_brightness.s: explores the display's backlight brightness (the FPGA bus's BACKLIGHT, $13,
0 off to 255 full, by PWM). Run on the emulator with keys typed, it must send the levels the keys ask for:
up/down by 1, right/left by 16, + and - by 1, digits 0-9 the presets from off to full, never past 0 or 255.

Run from the repo root:  python3 -m unittest discover -s tools/tests -v
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import michael_emulator  # noqa: E402

PROGRAM = os.path.join(michael_emulator.ROOT, 'firmware', 'programs', 'michael', 'michael_graphic_brightness.s')
UP, DOWN, RIGHT, LEFT = b'\x1b[A', b'\x1b[B', b'\x1b[C', b'\x1b[D'


def backlight_levels(log):
    """The levels sent with BACKLIGHT ($13): each "C 13" is followed by its argument, "D hh"."""
    lines, levels = log.split('\n'), []
    for i, line in enumerate(lines):
        if line == 'C 13' and i + 1 < len(lines) and lines[i + 1].startswith('D '):
            levels.append(int(lines[i + 1][2:], 16))
    return levels


@unittest.skipUnless(michael_emulator.AVAILABLE, 'vasm6502_oldstyle, gcc and make are needed')
class BrightnessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        michael_emulator.build_emulator()
        keys = b'5+' + UP + RIGHT + b'-' + DOWN + LEFT + b'0-9+'
        cls.log, cls.report = michael_emulator.run(program=PROGRAM, keys=keys, cycle_cap=30_000_000)

    def test_levels_follow_the_keys(self):
        self.assertEqual(backlight_levels(self.log),
                         [255,                 # full at the start
                          142, 143, 144, 160,  # 5 (a preset), +, up, right
                          159, 158, 142,       # -, down, left
                          0, 0, 255, 255])     # 0 (off), - (stays at 0), 9 (full), + (stays at 255)

    def test_the_lcd_shows_the_level(self):
        """Readable even with the backlight off"""
        self.assertIn('BACKLIGHT 255', self.report)


if __name__ == '__main__':
    unittest.main()
