"""The linker's tables, laid out as the Lathe linker will lay them out, stay within a ceiling
that only comes down (lk_memory_report.py: CEILING now, BUDGET the goal), but for the function
limit's raise from 800 to 896, which raised it by exactly what it costs."""
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
        # 54,144 until the function limit went from 800 to 896 (2026-11-15), at 7 bytes a function
        # (fn_flags, fn_ctx, fn_class, fn_slot, fn_edge): 672 bytes more.
        self.assertLessEqual(lk_memory_report.CEILING, 54144 + 96 * 7)
        self.assertGreaterEqual(lk_memory_report.CEILING, lk_memory_report.BUDGET)

    def test_the_compiler_has_room_for_more_functions(self):
        # The compiler links 799 functions (lathec.lth with lathe/src/lathec-bbc.env, 2026-11-15).
        import lk_tab
        self.assertEqual(lk_tab.MAX_FUNCS, 896)


if __name__ == '__main__':
    unittest.main()
