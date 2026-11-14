"""The test programs of the compiler's twins banked on Wendy 2 (lathe/host/README.md, "The
banked build"): outtest, regtest, condtest and gentest built with lathe/src/compiler-bank.env
(placement D's fallback E of lathe/docs/configurations.md, the small tables) by
src_support.build_banked, and run with --disk on Wendy 2 by src_support.run_banked. Each
section of their scripts must give what the Python twins give, as on the default machine
(test_src_out.py and the others): the same comparison, with the host at the small capacities.

By default a representative part of each script is run: every section of reg.txt, cond.txt and
out.txt, and every fourth section of gen.txt (its first and last included). LATHE_BANKED_ALL=1
runs every section of gen.txt too."""
import os
import shutil
import tempfile
import unittest

import src_support as support
import script_host as script
import regcmd_host
import test_src_cond
import test_src_gen
import test_src_out

ALL = os.environ.get('LATHE_BANKED_ALL') == '1'
RESIDENT_GOAL = 16 * 1024           # configurations.md: resident code within 16 KB


def read_map(path):
    """[(kind, address, size, name, rest)] of a map's lines."""
    items = []
    with open(path) as f:
        for line in f:
            p = line.split()
            if len(p) >= 4:
                items.append((p[0], int(p[1], 16), int(p[2], 16), p[3], p[4:]))
    return items


class Banked(unittest.TestCase):
    """One program: NAME is built banked in setUpClass."""
    NAME = None

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-src-banked-')
        cls.image = support.build_banked(cls.NAME, cls.dir)
        cls.map = read_map(os.path.join(cls.dir, 'work', cls.NAME + '.map'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def bank_of(self, module):
        """The banks of the module's functions in the map: {N, ...}, 0 for fixed."""
        found = set()
        for kind, address, size, name, rest in self.map:
            if kind == 'F' and name.split('.')[0] == module:
                b = [int(r[2:]) for r in rest if r.startswith('b=')]
                found.add(b[0] if b else 0)
        return found

    def test_placement(self):
        """The test's main module, script and the other drivers in bank 1; the code generator
        in banks 2 and 3; the lower layers fixed."""
        self.assertEqual(self.bank_of(self.NAME), {1})
        self.assertEqual(self.bank_of('script'), {1})
        for module, bank in (('out', 2), ('reg', 2), ('gen', 2), ('cond', 3), ('listing', 1),
                             ('regcmd', 1), ('kernel', 0), ('err', 0), ('fbuf', 0), ('sys', 0),
                             ('disk', 0), ('rt_bank', 0)):
            self.assertIn(self.bank_of(module), (set(), {bank}), module)

    def test_resident_code_is_within_the_goal(self):
        """Fixed code, constant data that is not err's messages, and the stubs."""
        resident = sum(size for kind, address, size, name, rest in self.map
                       if kind in 'FDT' and address < 0x8000 and not any(r.startswith('b=') for r in rest)
                       and not name.startswith('err.$'))
        self.assertLess(resident, RESIDENT_GOAL)


class OutBanked(Banked):
    NAME = 'outtest'

    def test_every_script(self):
        self.assertGreater(script.check_script(self, self.image, test_src_out.main, 'out', self.dir,
                                               outputs=1, small=True, banked=True), 3)


class RegBanked(Banked):
    NAME = 'regtest'

    def test_every_script(self):
        self.assertGreater(script.check_script(self, self.image, regcmd_host.main, 'reg', self.dir,
                                               outputs=1, small=True, banked=True), 5)


class CondBanked(Banked):
    NAME = 'condtest'

    def test_every_script(self):
        self.assertGreater(script.check_script(self, self.image, test_src_cond.main, 'cond',
                                               self.dir, outputs=1,
                                               extra=test_src_cond.grid_sections(), small=True,
                                               banked=True), 5)


class GenBanked(Banked):
    NAME = 'gentest'

    def test_every_script(self):
        last = len(script.sections('gen')) - 1
        chosen = None if ALL else (lambda n: n % 4 == 0 or n == last)
        self.assertGreater(script.check_script(self, self.image, test_src_gen.main, 'gen', self.dir,
                                               outputs=1, small=True, banked=True, chosen=chosen),
                           5)


del Banked

if __name__ == '__main__':
    unittest.main()
