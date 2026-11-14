"""The memory the compiler's tables take (lathe/tests/memory_report.py, lathe/docs/architecture.md,
"What stays in memory"): within the budget, counted the way the Lathe twins lay the tables out."""
import os
import re
import unittest

import memory_report as report

TWINS = ('err', 'kernel', 'src', 'lex', 'typetab', 'fold', 'fbuf', 'out', 'reg', 'cond')
VAR = re.compile(r'^(?:pub )?var (\w+): \[[^\]]+\](\^?\w+)', re.M)
# Arrays of a twin that are not arrays of its host module, and why.
CEILING = 42023             # the total of lathe/docs/architecture.md, "What stays in memory"
TWIN_ONLY = {('kernel', 'text'): 'the text memory, which the host keeps in env.mem'}


def twin_arrays(module):
    """{name: bytes per element} of the module-level arrays of lathe/src/MODULE.lth."""
    with open(os.path.join(report.LATHE, 'src', module + '.lth')) as f:
        text = f.read()
    return {name: 1 if t in ('byte', 'sbyte', 'bool') else 2 for name, t in VAR.findall(text)}


class MemoryTest(unittest.TestCase):
    def test_each_twin_lays_out_its_arrays_as_the_host_counts_them(self):
        for module in TWINS:
            host = {name: width for name, n, width in report.arrays(module)}
            twin = twin_arrays(module)
            for name, width in twin.items():
                with self.subTest(array=module + '.' + name):
                    if (module, name) in TWIN_ONLY:
                        continue
                    self.assertIn(name, host)
                    self.assertEqual(width, host[name])
            for name in host:
                with self.subTest(array=module + '.' + name):
                    self.assertIn(name, twin)

    @unittest.expectedFailure
    def test_the_tables_fit_the_budget(self):
        """Not yet: lathe/docs/architecture.md, "What stays in memory", says what is left."""
        self.assertLessEqual(report.total(), report.BUDGET)

    def test_the_tables_take_no_more_than_they_did(self):
        self.assertLessEqual(report.total(), CEILING)

    def test_every_module_of_the_corpus_compiles_at_these_capacities(self):
        import tempfile
        import shutil
        work = tempfile.mkdtemp(prefix='lathe-memory-')
        try:
            peaks, where, failed = report.run_corpus(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)
            report.unwatch()
        self.assertEqual(failed, [])


if __name__ == '__main__':
    unittest.main()
