"""Error cases: every cases/err/NAME.lth starts with `; error N LINE COL`, and the compiler
must report exactly that error at exactly that place, and end with status 1. A line
`; options ...` before the `module` line gives the compiler those options.

A case may `import host`: the interface of lathe/rt/host.lth is compiled first.
"""
import glob
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lathec_support as support  # noqa: E402

CASES = sorted(glob.glob(os.path.join(support.CASES, 'err', '*.lth')))
FIRST_LINE = re.compile(r'; error (\d+) (\d+) (\d+)\n')


class ErrorCasesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        host = os.path.join(support.LATHE, 'rt', 'host.lth')
        assert support.run_lathec(host, cls.tmp.name) == (0, '')

    def test_there_are_cases(self):
        self.assertGreater(len(CASES), 50)

    def test_each_case_reports_the_error_its_first_line_names(self):
        for path in CASES:
            with self.subTest(case=os.path.basename(path)):
                with open(path) as f:
                    expected = FIRST_LINE.fullmatch(f.readline())
                self.assertIsNotNone(expected, 'the first line must be "; error N LINE COL"')
                number, line, col = expected.groups()
                options = []
                with open(path) as f:
                    for text in f:
                        if text.startswith('module'):
                            break
                        if text.startswith('; options '):
                            options += text[len('; options '):].split()
                status, errors = support.run_lathec(*options, path, self.tmp.name)
                self.assertEqual(status, 1)
                self.assertEqual(errors.count('\n'), 1, errors)
                self.assertTrue(errors.startswith('%s:%s:%s: error %s: ' % (path, line, col, number)),
                                errors)


if __name__ == '__main__':
    unittest.main()
