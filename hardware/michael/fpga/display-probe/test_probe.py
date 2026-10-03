import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import probe  # noqa: E402


class InitCommandsTest(unittest.TestCase):
    """probe.py replays Michael's own initialisation, read from graphics_display.inc."""

    def test_reads_the_driver_table(self):
        cmds = probe.michael_init_commands()
        self.assertEqual(cmds[0], (0xEF, [0x03, 0x80, 0x02], False))
        self.assertIn((0xC0, [0x23], False), cmds)                   # ILI9341_PWCTR1, by name
        self.assertIn((0x36, [0x48], False), cmds)                   # ILI9341_MADCTL
        gamma = next(c for c in cmds if c[0] == 0xE0)                # ILI9341_GMCTRP1 spans three lines
        self.assertEqual(len(gamma[1]), 15)
        self.assertEqual(gamma[1][-1], 0x00)
        self.assertEqual(cmds[-2:], [(0x11, [], True), (0x29, [], False)])  # SLPOUT then a delay; DISPON

    def test_constants(self):
        names = probe.driver_constants()
        self.assertEqual(names["ILI9341_TFTHEIGHT"], 320)
        self.assertEqual(names["ILI9341_MADCTL_MY"], 0x80)


if __name__ == "__main__":
    unittest.main()
