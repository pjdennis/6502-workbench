"""The compiler's test programs that are built banked on Wendy 2 (test_src_banked.py: outtest,
regtest, condtest and gentest), banked on the emulated BBC Model B+128 in the small build:
lathe/src/compiler-bbc-bank.env, with their code over five banks of the module (16 KB each,
the developer's form, RAM) and their big tables in the four sideways RAM slots
(bbc_support.build_banked), run with *RUN through the MOS with --bbc-strict
(bbc_support.run(..., banked=True)). Each section of their scripts must give what the Python
twin gives at the small build's capacities, with the error output joined to the output as on
the BBC (bbc_support.host_run); the files written must be the same.

Every section is run. Each program is also built at the full capacities (SMALL 0), with the
split between fixed code and fixed variables moved for each (FULL_SPLIT), and its script run
against the twin at its own capacities: since the symbol table, OUT's table and DECL's import
rows are in regions (slots 0 and 1), all four fit (lathe/docs/bbc.md, "Step 3, as built").
gentest is built a third time, at the full capacities, with kernel, lex, src, fbuf and err
placed in banks 4 and 5 too, the functions of theirs that have a `with` block or run inside one
kept in fixed memory by the linker (bbc_support.KEPT_PLACES). All of it takes about 30
seconds."""
import concurrent.futures
import os
import shutil
import tempfile
import unittest

import src_support as support
import bbc_support as bbc
import script_host as script
import regcmd_host
import test_src_cond
import test_src_gen
import test_src_out

# Where the fixed variables start at the full capacities: just above each program's fixed code.
FULL_SPLIT = {'outtest': 0x3C30, 'regtest': 0x4080, 'condtest': 0x4130, 'gentest': 0x4870,
              'gentest kept': 0x43B0}
HAVE_TOOLS = os.path.isfile(support.EMULATOR) and os.path.isfile(support.build.COMPILER)
TOP = 0x7C00                        # HIMEM in mode 7


def read_map(path, mark='b='):
    """[(kind, address, size, name, bank or None)] of a map's lines; with mark='k=', the bank
    of a function kept in fixed memory (None for the others)."""
    items = []
    with open(path) as f:
        for line in f:
            p = line.split()
            if len(p) >= 4 and len(p[0]) == 1:
                bank = [int(r[2:]) for r in p[4:] if r.startswith(mark)]
                items.append((p[0], int(p[1], 16), int(p[2], 16), p[3], bank[0] if bank else None))
    return items


class OnTheBBC:
    """One program, built banked for the BBC in setUpClass (a mixin)."""
    NAME = None
    SCRIPT = None
    SPLIT = None                    # the full capacities, with the fixed variables from here
    KEPT = False                    # the modules of bbc_support.KEPT_PLACES placed too

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-bbc-bank-src-')
        cls.image = bbc.build_banked(cls.NAME, cls.dir, cls.SPLIT, cls.KEPT)
        cls.map = read_map(os.path.join(cls.dir, 'work', cls.NAME + '.map'))
        cls.kept = read_map(os.path.join(cls.dir, 'work', cls.NAME + '.map'), 'k=')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def main(self):
        raise NotImplementedError

    def extra(self):
        return []

    def test_it_fits_page_to_himem(self):
        """Fixed code from $1900 and fixed variables below HIMEM; every bank within the window
        $8000-$BFDF."""
        self.assertLessEqual(0x1900 + os.path.getsize(self.image), TOP)
        for kind, address, size, name, bank in self.map:
            if kind in 'FDTVS' and bank is None and address >= 0x0800:
                self.assertLessEqual(address + size, TOP, name)
            if bank is not None and kind in 'FDV':
                self.assertTrue(0x8000 <= address and address + size <= 0xBFE0, name)

    def test_placement(self):
        """The test's main module and the drivers in bank 1, the code generator in banks 2 to
        5, the big tables in sideways slots 0, 1, 12 and 13, the lower layers fixed. OUT's
        functions with a block of OUTTAB stay in fixed memory, the rest of it in bank 5."""
        banks = {}
        for kind, address, size, name, bank in self.map:
            if kind == 'F':
                banks.setdefault(name.split('.')[0], set()).add(bank)
        expected = {self.NAME: 1, 'script': 1, 'listing': 1, 'regcmd': 1, 'gen': 2, 'reg': 3,
                    'typetab': 3, 'slotview': 3, 'cond': 4, 'fold': 4,
                    'kernel': None, 'err': None, 'fbuf': None, 'sys': None, 'bbc': None,
                    'rt_bbc': None}
        kept = dict(bbc.KEPT_PLACES) if self.KEPT else {}
        kept['out'] = 5
        for module, bank in expected.items():
            if module in kept:
                continue
            self.assertIn(banks.get(module, {bank}), ({bank},), module)
        marked = {name: bank for kind, address, size, name, bank in self.kept if kind == 'F'}
        for kind, address, size, name, bank in self.map:
            module = name.split('.')[0]
            if kind == 'F' and module in kept:
                # In its bank, or kept fixed and marked with it.
                self.assertIn((bank, marked.get(name)), ((kept[module], None), (None, kept[module])),
                              name)
        if any(name == 'out.table_begin' for kind, address, size, name, bank in self.map):
            self.assertEqual(marked['out.table_begin'], 5)     # its block of OUTTAB
        tables = {name: bank for kind, address, size, name, bank in self.map if kind in 'VD'}
        for table, bank in (('kernel.names', 32), ('fbuf.buffer', 33), ('err.messages_1', 33),
                            ('kernel.sym_bytes', 34), ('kernel.member_type', 34)):
            self.assertEqual(tables.get(table), bank, table)
        if self.NAME in ('outtest', 'gentest'):         # the programs that link OUT's table
            self.assertEqual(tables.get('out.table'), 35)

    def test_every_script(self):
        runs = []
        for n, (title, text) in enumerate(script.sections(self.SCRIPT) + list(self.extra())):
            path = os.path.join(self.dir, '%s-%d.txt' % (self.SCRIPT, n))
            with open(path, 'wb') as f:
                f.write(text)
            runs.append((title, text, path, os.path.join(self.dir, '%s-%d-0' % (self.SCRIPT, n))))
        with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
            lathe = list(pool.map(lambda r: bbc.run(self.image, [r[2], r[3] + 'L'], paths=(0, 1),
                                                    banked=True), runs))
        for (title, text, path, made), (status, out, said, _) in zip(runs, lathe):
            with self.subTest(section=title.decode()):
                host = bbc.host_run(self.main(), [os.path.basename(path), os.path.basename(made) + 'P'],
                                    self.dir, small=self.SPLIT is None)
                if out != host[1]:
                    self.fail(script.first_difference(text, out, host[1]))
                self.assertEqual((status, said), (host[0], b''))
                self.assertEqual(os.path.exists(made + 'L'), os.path.exists(made + 'P'))
                if os.path.exists(made + 'P'):
                    with open(made + 'L', 'rb') as a, open(made + 'P', 'rb') as b:
                        self.assertEqual(a.read(), b.read(), 'file %s' % made)
        self.assertGreater(len(runs), 2)


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class OutBanked(OnTheBBC, unittest.TestCase):
    NAME = 'outtest'
    SCRIPT = 'out'

    def main(self):
        return test_src_out.main


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class RegBanked(OnTheBBC, unittest.TestCase):
    NAME = 'regtest'
    SCRIPT = 'reg'

    def main(self):
        return regcmd_host.main


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class CondBanked(OnTheBBC, unittest.TestCase):
    NAME = 'condtest'
    SCRIPT = 'cond'

    def main(self):
        return test_src_cond.main

    def extra(self):
        return test_src_cond.grid_sections()


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class GenBanked(OnTheBBC, unittest.TestCase):
    NAME = 'gentest'
    SCRIPT = 'gen'

    def main(self):
        return test_src_gen.main


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class GenKept(GenBanked):
    """At the full capacities, with the kept functions: fixed code ends below $43B0."""
    KEPT = True
    SPLIT = FULL_SPLIT['gentest kept']


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class OutFull(OutBanked):
    SPLIT = FULL_SPLIT['outtest']


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class RegFull(RegBanked):
    SPLIT = FULL_SPLIT['regtest']


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class CondFull(CondBanked):
    SPLIT = FULL_SPLIT['condtest']


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class GenFull(GenBanked):
    SPLIT = FULL_SPLIT['gentest']


if __name__ == '__main__':
    unittest.main()
