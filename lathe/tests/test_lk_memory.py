"""The linker's tables, laid out as the Lathe linker will lay them out, stay within a ceiling
that only comes down (lk_memory_report.py: CEILING now, BUDGET the goal)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lk_memory_report  # noqa: E402


class Memory(unittest.TestCase):
    def test_tables_stay_within_the_ceiling(self):
        rows, total = lk_memory_report.table_bytes()
        self.assertLessEqual(total, lk_memory_report.CEILING,
                             '\n'.join('%s %d' % (name, size) for name, size, _ in rows))

    def test_the_ceiling_is_never_above_where_it_was(self):
        self.assertLessEqual(lk_memory_report.CEILING, 53118)
        self.assertGreaterEqual(lk_memory_report.CEILING, lk_memory_report.BUDGET)


if __name__ == '__main__':
    unittest.main()
