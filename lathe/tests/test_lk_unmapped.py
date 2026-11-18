"""Link error 62: code that names a variable or constant of a region the environment puts in a bank,
in a function that has mapped no bank holding it (lathe/docs/bbc.md, "The linker on a 32K BBC").

The compiler maps a region's bank with a `with` block, whose first instruction is `LDA #bank` (a
fix-up of kind 6), and allows a region's variables and constants only inside one; but told that a
region is in fixed memory (`-fREGION`), it compiles the block to its body alone. An object so
compiled and linked where the region is in a bank would read and write whatever is in the window:
the linker refuses it. A fix-up of a function's code that names a variable or constant of a
region in bank B is good only after a kind 6 fix-up of the same function that names one in bank
B (in the order of the code). Constant data may hold such an address (a pointer into a region,
used inside a block elsewhere), and a function may reach a region through a pointer it is given:
neither names the region's symbols in code, and neither is checked.

The objects are made by hand (test_lk_support), with the environment of test_lk_windows's
regions: `work` in bank 4, `text` in bank 5. A Lathe program compiled for a region in fixed
memory (fixedblk.lth with fixedblk_fixed.env, -ffwork) and linked with the region in a bank
(fixedblk_banks.env) is refused by the host linker and by the Lathe-written one; the two
combinations that are harmless (blocks compiled, the region fixed; and the compiler told, the
region fixed) are configurations of tests/cases/e2e-config/fixedblk.lth.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_lk_support import Obj, link, string, NEVER, NOBODY  # noqa: E402
from test_lk_windows import REGIONS, farcall_with  # noqa: E402

import src_support as support  # noqa: E402

ERROR = 'link error 62: code uses a region in a bank where it maps none: '


def module(blocks, uses, name='t'):
    """Module t: v in region work (bank 4), k in text (bank 5), w in work too; main maps the bank
    of each symbol of `blocks` (LDA #bank, JSR rt_with.map) and then uses each of `uses`."""
    t = Obj(name)
    for s, d in (('v', False), ('k', True), ('w', False)):
        t.d(s) if d else t.v(s)
    t.raw(16, string('work'))
    t.var('v', 2, NEVER)
    t.raw(16, string('work'))
    t.var('w', 2, NEVER)
    t.raw(16, string('text'))
    t.data('k', b'\x11\x22\x33')
    c = t.code()
    calls = []
    for s in blocks:
        c.byte(0xA9, 6, t.d(s) if s == 'k' else t.v(s))
        c.abs(0x20, t.f('rt_with.map'))
        calls.append((t.f('rt_with.map'), 0, NOBODY))
    for s in uses:
        if s == 'k':
            c.abs(0xAD, t.d('k'))
        elif s == '<v':
            c.byte(0xA9, 2, t.v('v'))           # LDA #<v: an address formed is a use too
        else:
            c.abs(0x8D, t.v(s))
    c.raw(0x60)
    t.func('main', c, calls=calls)
    return t


class Unmapped(unittest.TestCase):
    def link(self, blocks, uses, env=REGIONS):
        return link([module(blocks, uses), farcall_with()], env)

    def test_a_use_after_a_block_of_its_bank_links(self):
        for blocks, uses in ((['v'], ['v']), (['v'], ['w']), (['v', 'k'], ['v', 'k']), (['k'], ['k'])):
            with self.subTest(blocks=blocks, uses=uses):
                r = self.link(blocks, uses)
                self.assertEqual((r.status, r.errors), (0, ''))

    def test_a_use_with_no_block_of_its_bank_is_refused(self):
        for blocks, uses, sym in (([], ['v'], 't.v'), ([], ['k'], 't.k'), (['v'], ['k'], 't.k'),
                                  (['k'], ['w'], 't.w'), ([], ['<v'], 't.v')):
            with self.subTest(blocks=blocks, uses=uses):
                r = self.link(blocks, uses)
                self.assertEqual((r.status, r.errors), (1, ERROR + sym + ', t.main\n'))

    def test_a_region_in_fixed_memory_needs_no_block(self):
        flat = Obj('rt_with')
        flat.func('map', b'\x60')
        flat.func('unmap', b'\x60')
        env = 'cpu 6502\nzeropage $00 $FF\ncode $0200 $7FFF\ndata $C000 $EFFF\nexit return\n'
        for extra in ('', 'region work fixed\nregion text fixed\n'):
            with self.subTest(env=extra):
                r = link([module([], ['v', 'k']), flat], env + extra)
                self.assertEqual((r.status, r.errors), (0, ''))

    def test_a_constant_table_may_hold_the_address_of_a_region_s_variable(self):
        t = module(['v'], ['v'])
        t.data('ptrs', b'\0\0', fixes=[(0, 1, t.v('w'), 0xFF, 0)])
        c = t.code()
        c.abs(0xAD, t.d('ptrs'))
        c.raw(0x60)
        t.func('other', c)
        m = t.code()
        r = link([t, farcall_with()], REGIONS)
        self.assertEqual((r.status, r.errors), (0, ''))
        del m


@unittest.skipUnless(os.path.isfile(support.EMULATOR) and os.path.isfile(support.build.COMPILER),
                     'emulator or compiler missing')
class CompiledForFixed(unittest.TestCase):
    """fixedblk.lth compiled with the region fwork in fixed memory and the compiler told
    (fixedblk_fixed.env: -ffwork), linked with fwork in a bank (fixedblk_banks.env): refused by
    the host linker and by the Lathe-written one (Wendy 2, the small build, lk_banked.py)."""

    @classmethod
    def setUpClass(cls):
        import test_bbc_toolchain as chain
        cls.dir = tempfile.mkdtemp(prefix='lathe-lk-unmapped-')
        cases = os.path.join(support.LATHE, 'tests', 'cases', 'e2e-config')
        steps = chain.recorded(os.path.join(cases, 'fixedblk.lth'), os.path.join(cases, 'fixedblk_fixed.env'),
                               os.path.join(cls.dir, 'fixed'))
        compiles = [st for st in steps if st[0] == 'compile']
        cls.told = any('-ffwork' in st[1] for st in compiles)
        _, _, cls.main, cls.objects = [st for st in steps if st[0] == 'link'][0]
        cls.env = os.path.join(cases, 'fixedblk_banks.env')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def args(self, d):
        return [self.env, self.main, os.path.join(d, 'o.bin'), os.path.join(d, 'o.map')] + self.objects

    def test_the_host_linker_refuses_it(self):
        self.assertTrue(self.told)
        d = tempfile.mkdtemp(dir=self.dir)
        r = subprocess.run([sys.executable, os.path.join(support.LATHE, 'host', 'link.py')] + self.args(d),
                           capture_output=True)
        self.assertEqual(r.returncode, 1)
        self.assertTrue(r.stderr.decode().startswith(ERROR + 'libfixb.'), r.stderr)

    def test_the_lathe_written_linker_refuses_it_too(self):
        import lk_banked
        d = tempfile.mkdtemp(dir=self.dir)
        image = lk_banked.build_linker(d)
        files = {'env': open(self.env, 'rb').read()}
        names = []
        for i, path in enumerate(self.objects):
            with open(path, 'rb') as f:
                files['o%d.lo' % i] = f.read()
            names.append('o%d.lo' % i)
        status, errors, written, cycles = lk_banked.run(image, files, ['env', self.main, 'o.bin', 'o.map'] + names)
        r = subprocess.run([sys.executable, os.path.join(support.LATHE, 'host', 'link.py')] + self.args(d),
                           capture_output=True)
        self.assertEqual((status, errors), (1, r.stderr))


if __name__ == '__main__':
    unittest.main()
