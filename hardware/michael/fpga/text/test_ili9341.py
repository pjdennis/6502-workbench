"""The model panel's hardware scroll (ili9341.py), against what Michael's graphic driver does on the board:
gd_scroll_up keeps the whole screen as the scroll area, draws row r at (r + scrolled) mod 20, and sets
VSCRSADD to (20 - scrolled) * 16; the rows then show in order. Then a scroll region between fixed areas."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ili9341 import Panel, CASET, PASET, RAMWR, VSCRDEF, VSCRSADD  # noqa: E402


def draw_row(panel, memory_row, value):
    """A one-pixel-wide mark: the cell (memory_row, 0)'s first pixel column, all 16 pixels, as value."""
    y = memory_row * 16
    panel.receive(0, CASET)
    for b in (y >> 8, y & 0xFF, (y + 15) >> 8, (y + 15) & 0xFF):
        panel.receive(1, b)
    panel.receive(0, PASET)
    for b in (0, 0, 0, 0):
        panel.receive(1, b)
    panel.receive(0, RAMWR)
    for _ in range(16):
        panel.receive(1, value >> 8)
        panel.receive(1, value & 0xFF)


def command(panel, cmd, *words):
    panel.receive(0, cmd)
    for w in words:
        panel.receive(1, w >> 8)
        panel.receive(1, w & 0xFF)


def shown_rows(panel):
    return [panel.pixels[0][panel.shown_column(r * 16)] for r in range(20)]


class PanelScrollTest(unittest.TestCase):
    def test_the_graphic_drivers_whole_screen_scroll(self):
        for scrolled in range(20):
            with self.subTest(scrolled=scrolled):
                panel = Panel()
                for r in range(20):
                    draw_row(panel, (r + scrolled) % 20, r)
                command(panel, VSCRSADD, (20 - scrolled) % 20 * 16)
                self.assertEqual(shown_rows(panel), list(range(20)))

    def test_a_region_scrolls_between_fixed_areas(self):
        """Rows 3-17 scroll; rows 0-2 and 18-19 stay. The top fixed area is the rows below the region."""
        panel = Panel()
        for r in range(20):
            draw_row(panel, r, r)
        command(panel, VSCRDEF, (19 - 17) * 16, (17 - 3 + 1) * 16, 3 * 16)
        command(panel, VSCRSADD, (19 - 17) * 16 + 14 * 16)   # the region's offset: content up a row
        self.assertEqual(shown_rows(panel), [0, 1, 2] + list(range(4, 18)) + [3] + [18, 19])


if __name__ == '__main__':
    unittest.main()
