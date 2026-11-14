"""src.py: the source stack gives one character at a time, with its line and column."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lathec_support as support  # noqa: E402
import err  # noqa: E402
import kernel  # noqa: E402
import src  # noqa: E402


def open_text(text, address=support.TEXT):
    start, end = support.put_text(text, address)
    src.open_memory(start, end)


def rest():
    """Every remaining character of the top source as (character, line, column)."""
    seen = []
    while not src.eof:
        seen.append((chr(src.ch), src.line, src.col))
        src.advance()
    return seen


class SourceTest(unittest.TestCase):
    def setUp(self):
        support.fresh()
        err.init()
        kernel.init()
        src.init()

    def test_characters_come_with_line_and_column(self):
        open_text(b'ab\nc')
        self.assertEqual(rest(), [('a', 1, 1), ('b', 1, 2), ('\n', 1, 3), ('c', 2, 1)])

    def test_the_end_stays_the_end_and_keeps_its_position(self):
        open_text(b'a\n')
        rest()
        src.advance()
        self.assertTrue(src.eof)
        self.assertEqual((src.ch, src.line, src.col), (0, 2, 1))

    def test_an_empty_source_is_at_its_end_at_once(self):
        open_text(b'')
        self.assertTrue(src.eof)
        self.assertEqual((src.line, src.col), (1, 1))

    def test_a_file_is_read_and_named_in_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'x.lth')
            with open(path, 'wb') as f:
                f.write(b'hi')
            name, _ = support.put_text(path.encode())
            self.assertTrue(src.open_file(name))
            self.assertEqual(err.file, name)
            self.assertEqual([c for c, _, _ in rest()], ['h', 'i'])
            src.close()

    def test_line_and_column_stop_counting_at_65535(self):
        # Source may be any length, but a position is two bytes on the target.
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'long.lth')
            with open(path, 'wb') as f:
                f.write(b'\n' * 70000 + b'x' * 70000)
            name, _ = support.put_text(path.encode())
            src.open_file(name)
            while not src.eof:
                src.advance()
            self.assertEqual((src.line, src.col), (65535, 65535))

    def test_a_missing_file_does_not_open(self):
        name, _ = support.put_text(b'/nonexistent/x.lth')
        self.assertFalse(src.open_file(name))
        self.assertEqual(src.depth, 0)

    def test_closing_a_source_goes_back_to_the_one_below(self):
        open_text(b'ab\ncd')
        src.advance()
        src.advance()
        src.advance()                               # at 'c', line 2
        open_text(b'XY', support.TEXT + 0x100)
        self.assertEqual(rest(), [('X', 1, 1), ('Y', 1, 2)])
        src.close()
        self.assertEqual(rest(), [('c', 2, 1), ('d', 2, 2)])

    def test_sources_nested_too_deeply_are_error_81(self):
        with self.assertRaises(SystemExit):
            for _ in range(src.MAX_SOURCES + 1):
                open_text(b'x')
        self.assertIn('error 81:', support.error_text())


if __name__ == '__main__':
    unittest.main()
