"""The text mode's model (text_screen.py): each rule of the ROM's LCD screen (lcd_screen.inc) that it
mirrors."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from text_screen import TextScreen, BS, LF, CR  # noqa: E402


def screen(rows=4, cols=5):
    return TextScreen(rows, cols)


def write(s, text):
    for ch in text:
        s.put(ord(ch))


class TextScreenTest(unittest.TestCase):
    def assertRows(self, s, *rows):
        self.assertEqual([s.text(r) for r in range(s.rows)], list(rows))

    def test_starts_blank_with_the_cursor_home_and_hidden(self):
        s = screen()
        self.assertRows(s, '     ', '     ', '     ', '     ')
        self.assertEqual((s.row, s.col, s.cursor, s.reverse, s.top, s.bottom), (0, 0, False, False, 0, 3))

    def test_writing_wraps_to_the_next_row_at_once(self):
        s = screen()
        write(s, 'abcde')
        self.assertEqual((s.row, s.col), (1, 0))
        write(s, 'f')
        self.assertRows(s, 'abcde', 'f    ', '     ', '     ')

    def test_the_bottom_row_stops_past_its_end_and_drops_what_follows(self):
        s = screen()
        s.goto(3, 3)
        write(s, 'xyz!')
        self.assertRows(s, '     ', '     ', '     ', '   xy')
        self.assertEqual((s.row, s.col), (3, 5))

    def test_bs_cr_and_lf(self):
        s = screen()
        s.goto(1, 3)
        s.put(BS)
        self.assertEqual(s.col, 2)
        s.put(CR)
        self.assertEqual(s.col, 0)
        s.put(BS)
        self.assertEqual(s.col, 0)
        s.goto(2, 4)
        s.put(LF)
        self.assertEqual((s.row, s.col), (3, 0))
        s.goto(3, 4)
        s.put(LF)
        self.assertEqual((s.row, s.col), (3, 0))       # the bottom row: no scroll

    def test_other_control_codes_are_dropped(self):
        s = screen()
        for code in (0x00, 0x07, 0x09, 0x1B, 0x1F):
            s.put(code)
        self.assertEqual((s.row, s.col), (0, 0))
        self.assertRows(s, '     ', '     ', '     ', '     ')

    def test_goto_limits(self):
        s = screen()
        s.goto(9, 9)
        self.assertEqual((s.row, s.col), (3, 5))

    def test_reverse_video_is_kept_per_cell(self):
        s = screen()
        write(s, 'a')
        s.video(1)
        write(s, 'b')
        s.video(0)
        write(s, 'c')
        self.assertEqual([s.cell(0, c) for c in range(3)], [('a', False), ('b', True), ('c', False)])

    def test_clear_eol_insert_and_delete_within_the_row(self):
        s = screen()
        write(s, 'abcde')
        s.goto(0, 1)
        s.insert(2)
        self.assertEqual((s.text(0), s.col), ('a  bc', 1))
        s.delete(3)
        self.assertEqual(s.text(0), 'ac   ')
        s.goto(0, 1)
        s.clear_eol()
        self.assertEqual(s.text(0), 'a    ')
        s.insert(9)                                    # limited to the row
        self.assertEqual(s.text(0), 'a    ')

    def test_shifts_reach_the_end_of_a_full_row(self):
        s = screen()
        for op, expected in ((s.clear_eol, 'ab   '), (lambda: s.delete(9), 'ab   '), (lambda: s.insert(9), 'ab   ')):
            s.goto(0, 0)
            write(s, 'abcde')
            s.goto(0, 2)
            op()
            self.assertEqual(s.text(0), expected)

    def test_past_the_end_shifts_nothing(self):
        s = screen()
        s.goto(3, 0)
        write(s, 'abcde')
        s.insert(1)
        s.delete(1)
        s.clear_eol()
        self.assertEqual(s.text(3), 'abcde')

    def test_counts_of_zero_do_nothing(self):
        s = screen()
        write(s, 'abcdefgh')
        s.goto(0, 0)
        for op in (s.insert, s.delete, s.scroll_up, s.scroll_down, s.insert_lines, s.delete_lines):
            op(0)
        self.assertRows(s, 'abcde', 'fgh  ', '     ', '     ')

    def test_region_and_scrolling_within_it(self):
        s = screen()
        for r, t in enumerate('0123'):
            s.goto(r, 0)
            write(s, t)
        s.goto(2, 2)
        s.region(1, 2)
        self.assertEqual((s.row, s.col, s.top, s.bottom), (0, 0, 1, 2))
        s.scroll_up(1)
        self.assertRows(s, '0    ', '2    ', '     ', '3    ')
        s.scroll_down(5)                               # limited to the region
        self.assertRows(s, '0    ', '     ', '     ', '3    ')

    def test_a_region_of_one_row_is_ignored(self):
        s = screen()
        s.goto(2, 2)
        s.region(2, 2)
        s.region(3, 1)
        self.assertEqual((s.row, s.col, s.top, s.bottom), (2, 2, 0, 3))
        s.region(2, 9)                                 # the bottom is limited to the last row
        self.assertEqual((s.top, s.bottom), (2, 3))

    def test_insert_and_delete_lines_from_the_cursors_row(self):
        s = screen()
        for r, t in enumerate('0123'):
            s.goto(r, 0)
            write(s, t)
        s.goto(1, 3)
        s.insert_lines(1)
        self.assertRows(s, '0    ', '     ', '1    ', '2    ')
        self.assertEqual((s.row, s.col), (1, 0))
        s.delete_lines(2)
        self.assertRows(s, '0    ', '2    ', '     ', '     ')

    def test_lines_outside_the_region_do_nothing(self):
        s = screen()
        write(s, 'abcdefghij')
        s.region(2, 3)
        s.goto(0, 3)
        s.insert_lines(1)
        s.delete_lines(1)
        self.assertRows(s, 'abcde', 'fghij', '     ', '     ')
        self.assertEqual((s.row, s.col), (0, 3))

    def test_clear_keeps_the_region_and_text_on_resets_everything(self):
        s = screen()
        s.region(1, 2)
        s.set_cursor(1)
        s.video(1)
        write(s, 'x')
        s.clear()
        self.assertEqual((s.top, s.bottom, s.cursor, s.reverse), (1, 2, True, True))
        s.text_on()
        self.assertEqual((s.top, s.bottom, s.cursor, s.reverse), (0, 3, False, False))


if __name__ == '__main__':
    unittest.main()
