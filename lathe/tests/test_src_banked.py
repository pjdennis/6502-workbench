"""The test programs of the compiler's twins banked on Wendy 2 (lathe/host/README.md, "The
banked build"): outtest, regtest, condtest and gentest built with lathe/src/compiler-bank.env
(the code in three banks, the big tables in two data banks, the full capacities:
lathe/docs/configurations.md, "Measured on the compiler's test programs") by
src_support.build_banked, and run with --disk on Wendy 2 by src_support.run_banked. Each
section of their scripts must give what the Python twins give, as on the default machine
(test_src_out.py and the others): the same comparison, with the host at its own capacities.

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


# The tables the small build makes smaller (script_host.SMALL), as (host module, capacity, bytes
# an element, the array's name in the map) for one array each capacity sizes.
FULL_TABLES = (('kernel', 'NAME_HEAP_SIZE', 1, 'kernel.names'), ('kernel', 'MAX_SYMS', 7, 'kernel.sym_bytes'),
               ('kernel', 'MAX_MEMBERS', 1, 'kernel.member_type'), ('kernel', 'TEXT_SIZE', 1, 'kernel.text'),
               ('kernel', 'TOKEN_SIZE', 1, 'kernel.tokens'), ('fbuf', 'BUFFER_SIZE', 1, 'fbuf.buffer'),
               ('fbuf', 'MAX_LABELS', 1, 'fbuf.label_note'), ('fbuf', 'MAX_WEIGHTS', 1, 'fbuf.weight_slot'),
               ('out', 'MAX_TABLE', 1, 'out.table'), ('out', 'MAX_TABLE_FIXES', 1, 'out.table_fix_kind'),
               ('lex', 'MAX_STRING', 1, 'lex.string'), ('typetab', 'MAX_TYPES', 1, 'typetab.form'))


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
        """The banks of the module's functions in the map: {N, ...}, 0 for fixed; a function of
        a placed module kept in fixed memory (k=N: it has a `with` block) counts as in bank N."""
        found = set()
        for kind, address, size, name, rest in self.map:
            if kind == 'F' and name.split('.')[0] == module:
                b = [int(r[2:]) for r in rest if r.startswith(('b=', 'k='))]
                found.add(b[0] if b else 0)
        return found

    def test_placement(self):
        """The test's main module, script and the other drivers in bank 1; the code generator
        in banks 2, 3 and 5; the lower layers fixed."""
        self.assertEqual(self.bank_of(self.NAME), {1})
        self.assertEqual(self.bank_of('script'), {1})
        for module, bank in (('out', 5), ('reg', 2), ('gen', 2), ('fold', 3), ('cond', 3), ('listing', 1),
                             ('regcmd', 1), ('typetab', 2), ('kernel', 0), ('err', 0), ('fbuf', 0), ('sys', 0),
                             ('disk', 0), ('rt_bank', 0)):
            self.assertIn(self.bank_of(module), (set(), {bank}), module)

    def test_the_tables_have_the_full_capacities(self):
        """compiler-bank.env builds the twins with SMALL 0, and each table the small build makes
        smaller (script_host.SMALL) has its full size in the map: the host's own capacity."""
        import importlib
        import mapenv
        self.assertIn(dict((n.lower(), v) for n, v in mapenv.read_env(support.BANK_ENV).defines)['small'],
                      (0, '0'))
        sizes = {name: size for kind, address, size, name, rest in self.map if kind == 'V'}
        checked = 0
        for module, const, width, table in FULL_TABLES:
            if table in sizes:
                full = getattr(importlib.import_module(module), const)
                self.assertEqual(sizes[table], full * width, table)
                checked += 1
        self.assertGreater(checked, 8)

    def test_the_big_tables_are_in_the_data_banks(self):
        banks = {name: [r for r in rest if r.startswith('b=')] for kind, address, size, name, rest
                 in self.map if kind in 'VD'}
        for table, bank in (('kernel.names', 'b=4'), ('fbuf.buffer', 'b=6'), ('lex.string', 'b=6'),
                            ('kernel.tokens', 'b=6'), ('err.messages_1', 'b=6'),
                            ('out.table_fix_kind', 'b=6')):
            if table in banks:
                self.assertEqual(banks[table], [bank], table)

    def test_out_table_is_in_its_region(self):
        """OUT's constant table and its fix-ups are in the region OUTTAB, bank 6 (until
        2026-11-15 the table followed OUT into bank 5: a table of more than 256 bytes indexed by
        a word, named only by its module's code, goes into its module's bank, its address formed
        only to reach an element, fix-up kinds 7 and 8). GEN fills it through out.table_byte()."""
        banks = {name: [r for r in rest if r.startswith('b=')] for kind, address, size, name, rest
                 in self.map if kind == 'V'}
        if 'out.table' in banks:
            self.assertEqual(banks['out.table'], ['b=6'])      # in the region OUTTAB

    def test_resident_code_is_within_the_goal(self):
        """Fixed code, constant data that is not err's messages, and the stubs."""
        resident = sum(size for kind, address, size, name, rest in self.map
                       if kind in 'FDT' and address < 0x8000 and not any(r.startswith('b=') for r in rest)
                       and not name.startswith(('err.$', 'err.messages_')))
        self.assertLess(resident, RESIDENT_GOAL)


class OutBanked(Banked):
    NAME = 'outtest'

    def test_every_script(self):
        self.assertGreater(script.check_script(self, self.image, test_src_out.main, 'out', self.dir,
                                               outputs=1, banked=True), 3)


class RegBanked(Banked):
    NAME = 'regtest'

    def test_every_script(self):
        self.assertGreater(script.check_script(self, self.image, regcmd_host.main, 'reg', self.dir,
                                               outputs=1, banked=True), 5)


class CondBanked(Banked):
    NAME = 'condtest'

    def test_every_script(self):
        self.assertGreater(script.check_script(self, self.image, test_src_cond.main, 'cond',
                                               self.dir, outputs=1,
                                               extra=test_src_cond.grid_sections(),
                                               banked=True), 5)


class GenBanked(Banked):
    NAME = 'gentest'

    def test_every_script(self):
        last = len(script.sections('gen')) - 1
        chosen = None if ALL else (lambda n: n % 4 == 0 or n == last)
        self.assertGreater(script.check_script(self, self.image, test_src_gen.main, 'gen', self.dir,
                                               outputs=1, banked=True, chosen=chosen),
                           5)


del Banked

if __name__ == '__main__':
    unittest.main()
