"""The linker's tables, laid out as the Lathe linker will lay them out, stay within a ceiling
that only comes down (lk_memory_report.py: CEILING now, BUDGET the goal), but for the function
limit's raise from 800 to 896, the command file's words and the environment file's defines,
which raised it by exactly what they cost."""
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
        # (fn_flags, fn_ctx, fn_class, fn_slot, fn_edge): 672 bytes more; and 512 for the words
        # of a command file (lk_file.arg_text, 2026-11-16), which the compiler's link on the BBC
        # needs: its command line is longer than the 239 bytes the module copies; and 48 for the
        # environment file's defines, which `when` and `unless` read (lk_envf.define_name and
        # define_word, 16 of them, 2026-11-17); and 16 for what each copy of a function loses
        # before the run of its fix-ups held (lk_fix.run_lost, a word a context, 2026-11-18), so
        # that no function is refused for its number of fix-ups; and 64 for each region's capacity
        # variable (lk_envf.region_room, lk_name.room_def, a word each of 16 regions, 2026-11-20),
        # with which a placer sets a table's size as the program starts; and 128 for the
        # environment's text that holds their names (lk_envf.TEXT_SIZE, 384 to 512, with LKDYN 1);
        # and 32 for each bank's `top`, the last address of its variables (lk_envf.bank_top, a word
        # each of 16 banks, 2026-11-20), which puts a dynamic region's block on a page.
        self.assertLessEqual(lk_memory_report.CEILING,
                             54144 + 96 * 7 + 512 + 16 * 3 + 2 * 8 + 2 * 2 * 16 + 128 + 2 * 16)
        self.assertGreaterEqual(lk_memory_report.CEILING, lk_memory_report.BUDGET)

    def test_the_compiler_has_room_for_more_functions(self):
        # The compiler links 799 functions (lathec.lth with lathe/src/lathec-bbc.env, 2026-11-15).
        import lk_tab
        self.assertEqual(lk_tab.MAX_FUNCS, 896)


if __name__ == '__main__':
    unittest.main()
