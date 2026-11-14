"""lathe/src/reg.lth against lathe/host/reg.py: lathe/src/regtest.lth runs each section of
lathe/tests/scripts/reg.txt, which push operands, load, store, spill, test, branch and join and
finish the function, and prints what each gives and the function's code, fix-ups and frame;
regcmd_host.main() does the same with reg.py, command for command. The outputs, error reports,
exit statuses and the object files written must be identical. The program is built with the
compiler's tables at their full size (lathe/src/compiler.env)."""
import shutil
import tempfile
import unittest

import script_host as script
import regcmd_host


class RegTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-src-reg-')
        cls.image = script.support.build_program('regtest', cls.dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_every_script(self):
        self.assertGreater(script.check_script(self, self.image, regcmd_host.main,
                                               'reg', self.dir, outputs=1), 5)


if __name__ == '__main__':
    unittest.main()
