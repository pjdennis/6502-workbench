"""The linker's build for a 32K BBC Model B (lathe/src/linker-bbc.env with `define RAM32 1`;
lathe/docs/bbc.md, "The linker on a 32K BBC"): no sideways RAM, every table in main RAM, the
capacities of LKSMALL 2, in the eight-bank ROM beside the compiler.

- The build: in the eight-bank ROM form, with the DFS's names (BBCFS 1) and without them, the map
  puts nothing in a sideways RAM slot and nothing outside $1900-$7BFF and $0401-$06FF, its banks
  fit as judged, and the image of both tools fits the 128 KB EPROM.
- The capacities (the host linker at them, lk_small.load(2), refuses where the Lathe-written
  build does): the corpus of end-to-end cases and the smaller test programs link as at full
  capacities, every file the same; a program of 16 KB (a mode 4 screen) and one of 25 KB (mode 7)
  link (lk_ram32.py makes them of real programs).
- On the emulated BBC (B+128, whose sideways RAM the 32K build does not name): `*LLINK @LINKARG`
  from the eight-bank image links lextest as the host linker does, every file the same; with
  LATHE_LK_RAM32_ALL=1 also fbuftest, kerneltest and the 25 KB programs, and with
  LATHE_LK_RAM32_REPORT=1 their cycles.
"""
import os
import re
import shutil
import tempfile
import unittest

import src_support as support
import lk_ram32

ALL = os.environ.get('LATHE_LK_RAM32_ALL') == '1'
REPORT = os.environ.get('LATHE_LK_RAM32_REPORT') == '1'
HAVE_TOOLS = os.path.isfile(support.EMULATOR) and os.path.isfile(support.build.COMPILER)

# Real programs and programs made of them: (pieces, the screen mode they fit with).
MODE4 = (('fbuftest',), 4)                    # 16,447 bytes
MODE7 = (('lextest', 'errtest', 'copytest', 'e2e_compare'), 7)      # 25,034 bytes
MORE = [(('kerneltest',), 7), (('kerneltest', 'copytest', 'e2e_compare'), 7), MODE4, MODE7]
QUICK_CASES = ('hello', 'calls', 'rec_tree', 'reg_args', 'compare', 'record_copy')
LARGER = ((('lextest', 'errtest', 'copytest', 'e2e_compare', 'e2e_reg_args', 'e2e_record_copy', 'e2e_control'),
           'link error 11'),
          (('srctest', 'typetest', 'copytest', 'errtest'), 'link error 11'))
# Test mains of 344 fix-ups each, more than a run of the 32K build holds (278).
LONG = ('e2e_record_copy', 'e2e_arith_ops', 'e2e_bigarray_pages')


def items(map_path):
    import test_bbc_selfhost as selfhost
    return selfhost.read_map(map_path)


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class Build(unittest.TestCase):
    """The 32K build in the eight-bank ROM form, beside the compiler."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-lk-ram32-')
        cls.images = {fs: lk_ram32.build_image(os.path.join(cls.dir, 'fs%d' % fs), fs) for fs in (0, 1)}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_it_links_and_both_tools_fit_the_128k_image(self):
        for fs, (image, account, map_path, error) in self.images.items():
            with self.subTest(bbcfs=fs):
                self.assertIsNone(error)
                self.assertTrue(account.fits(), account.summary())
                self.assertIsNotNone(image)

    def test_every_table_is_in_main_ram(self):
        """No `bank` of a sideways slot, no region in one: every variable in $1900-$7BFF or
        $0401-$06FF, the code below them."""
        for fs, (image, account, map_path, error) in self.images.items():
            with self.subTest(bbcfs=fs):
                with open(map_path) as f:
                    text = f.read()
                self.assertEqual(re.findall(r'(?m)^W 8050 0000 .*$', text), [])
                fixed = [i for i in items(map_path) if i[4] is None]
                code = [i for i in fixed if i[0] in 'FTD' and i[1] >= 0x0800]
                data = [i for i in fixed if i[0] == 'V']
                for i in code:
                    self.assertTrue(0x1900 <= i[1] and i[1] + i[2] <= 0x7C00, i)
                for i in data:
                    self.assertTrue(0x0401 <= i[1] and i[1] + i[2] <= 0x0700 or 0x1900 <= i[1] and i[1] + i[2] <= 0x7C00
                                    or i[1] + i[2] <= 0x90, i)
                self.assertFalse([i for i in items(map_path) if i[4] is not None and i[0] == 'V'])
                self.assertLessEqual(max(i[1] + i[2] for i in code), min(i[1] for i in data if i[1] >= 0x1900))
                for name in ('lk_tab.work', 'lk_tab.nodes', 'lk_name.local', 'lk_tab.edge_word', 'lk_tab.slot_sz'):
                    self.assertIn(name, [i[3] for i in data])


class Capacities(unittest.TestCase):
    """The host linker at the 32K build's capacities."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-lk-ram32-cap-')
        cls.cache = os.path.join(cls.dir, 'cache')
        names = list(dict.fromkeys(['e2e_' + c for c in QUICK_CASES] + list(LONG)
                                   + [p for ps, _ in MORE + list(LARGER) for p in ps]))
        if ALL:
            names = None
        cls.built = lk_ram32.build_programs(cls.cache, names)
        cls.env = os.path.join(cls.cache, 'measure.env')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def same_link(self, main, objects):
        """The host linker at full capacities and at the 32K build's: the 32K one's status, and
        whether it wrote what the full one did."""
        import subprocess
        import sys
        outs = []
        for level in (0, 2):
            d = tempfile.mkdtemp(dir=self.dir)
            r = subprocess.run([sys.executable, '-c', 'import sys, lk_small; lk_small.load(%d or False); '
                                'import env, link; env.start(sys.argv[1:]); link.main()' % level, self.env,
                                main, os.path.join(d, 'o.bin'), os.path.join(d, 'o.map')] + objects,
                               cwd=lk_ram32.HERE, capture_output=True)
            files = {f: lk_ram32.read_bytes(os.path.join(d, f)) for f in os.listdir(d)}
            outs.append((r.returncode, files))
        return outs[1][0], outs[0] == outs[1]

    def test_the_corpus_links_as_at_full_capacities(self):
        chosen = [n for n in self.built if n.startswith('e2e_') or n in ('errtest', 'srctest', 'lextest')]
        refused = {'e2e_for_ranges': 12}
        for name in chosen:
            with self.subTest(program=name):
                status, same = self.same_link(*lk_ram32.program(self.cache, name))
                if name in refused:
                    self.assertEqual(status, 1)
                else:
                    self.assertEqual(status, 0)
                    self.assertTrue(same)

    def test_programs_for_mode_4_and_mode_7_link(self):
        for pieces, mode in (MODE4, MODE7):
            with self.subTest(pieces=pieces):
                main, objects = lk_ram32.glue(self.cache, pieces, tempfile.mkdtemp(dir=self.dir))
                status, error, use, size = lk_ram32.host_link(2, self.env, main, objects)
                self.assertEqual((status, error), (0, ''))
                self.assertTrue(lk_ram32.fits(size, mode), size)
                # As large as the screen leaves room for: 16 KB, or too large for mode 4.
                self.assertTrue(size[0] + size[1] >= 16000 if mode == 4 else not lk_ram32.fits(size, 4), size)
                status, same = self.same_link(main, objects)
                self.assertTrue(same)

    def test_generated_programs_of_25_kb_link(self):
        """gen_program's programs for mode 7 (lathe/docs/bbc.md, "Capacities retuned"): 8 modules of
        26 functions of the usual shape (125 bytes, 2.8 calls a function: 24.6 KB) and of 21 of the
        tools' (157 bytes, 3.7 calls: 24.7 KB), which ask the calls most of all. (25.0 and 24.9 KB
        until the compiler's source refactorings made its code 2 to 3 % smaller.)"""
        import test_gen_program as tg
        for modules, functions, calls in ((8, 26, 2.0), (8, 21, 3.5)):
            with self.subTest(functions=functions, calls=calls):
                work = tempfile.mkdtemp(dir=self.dir)
                main, env, size, p = tg.make(work, modules, functions, 7, calls=calls)
                self.assertIsNotNone(env, size)
                self.assertGreater(size[0] + size[1], 24500)
                link = tg.recorded(main, env, os.path.join(work, 'steps'))[-1]
                status, said, use, linked = lk_ram32.host_link(2, link[1], link[2], list(link[3]))
                self.assertEqual((status, said), (0, ''))

    def test_what_stops_a_larger_program(self):
        """A program of 31 KB, more than a 32K BBC holds: too many functions (310; 601 symbols in
        object files too, until the texts left err); and one made of small functions: too many functions (srctest, typetest and copytest alone, 297
        functions until the texts of the errors left err on 2026-11-18, are 296 now and link)."""
        for pieces, error in LARGER:
            with self.subTest(pieces=pieces):
                main, objects = lk_ram32.glue(self.cache, pieces, tempfile.mkdtemp(dir=self.dir))
                status, said, use, size = lk_ram32.host_link(2, self.env, main, objects)
                self.assertEqual(status, 1)
                self.assertTrue(said.startswith(error), said)


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class OnTheBBC(unittest.TestCase):
    """`*LLINK @LINKARG` from the eight-bank image with the 32K build of the linker."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-lk-ram32-bbc-')
        cls.image = lk_ram32.build_image(os.path.join(cls.dir, 'image'))[0]
        cls.cache = os.path.join(cls.dir, 'cache')
        cls.chosen = [(('lextest',), 7), ((LONG[0],), 7)] + (MORE + [((p,), 7) for p in LONG[1:]] if ALL else [])
        lk_ram32.build_programs(cls.cache, [p for ps, _ in cls.chosen for p in ps])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_it_links_as_the_host_linker_does(self):
        if REPORT:
            print('\nthe 32K build of the linker on the BBC:')
        for pieces, mode in self.chosen:
            with self.subTest(pieces=pieces):
                work = tempfile.mkdtemp(dir=self.dir)
                main, objects = lk_ram32.glue(self.cache, pieces, os.path.join(work, 'objects'))
                self.link_both(pieces, mode, main, objects, work)

    def test_a_function_of_a_thousand_fix_ups(self):
        """test_lk_fixup_runs.py's function of 1,006 fix-ups, in two contexts: four runs of the
        32K build's, read again for each, and for the copy of the interrupt context."""
        import test_lk_fixup_runs as runs
        o, n = runs.program(220)
        self.assertGreater(n, 3 * 278)
        work = tempfile.mkdtemp(dir=self.dir)
        path = os.path.join(work, 'BIG.lo')
        with open(path, 'wb') as f:
            f.write(o.to_bytes())
        self.link_both(('a thousand fix-ups',), 7, 't', [path], work)

    def test_more_weights_waiting_than_the_table_holds(self):
        """gen_program's 6 modules of 12 functions in build.py's order, rt_math last, which every
        module calls: more weights wait for it than the 32K build's table holds (16), which was
        link error 41; they are read again (test_lk_weights.py)."""
        import test_bbc_toolchain as toolchain
        import test_gen_program as tg
        work = tempfile.mkdtemp(dir=self.dir)
        p = tg.gen_program.Program(6, 12, 2.0, 1, None)
        main = p.write(os.path.join(work, 'src'))
        link = toolchain.recorded(main, tg.measure_env(os.path.join(work, 'm.env')), os.path.join(work, 'steps'))[-1]
        self.assertEqual(os.path.basename(link[3][-1]), 'rt_math.lo')
        self.assertGreater(lk_ram32.host_link(0, link[1], link[2], list(link[3]))[2]['pending weights'], 16)
        self.link_both(('weights waiting',), 7, link[2], list(link[3]), work)

    def link_both(self, pieces, mode, main, objects, work):
        """Link on the BBC and by the host linker: every file the same."""
        status, error, use, size = lk_ram32.host_link(0, os.path.join(self.cache, 'measure.env'), main, objects)
        env_path = lk_ram32.target_env(os.path.join(work, 'PROG.env'), size[0], size[1], mode)
        said, written, (host_status, expected), cycles, traffic = lk_ram32.bbc_link(
            self.image, objects, main, env_path, work)
        self.assertEqual((said, host_status), ((0, b'', b''), 0))
        self.assertEqual(sorted(written), sorted(expected))
        for f in expected:
            self.assertTrue(written[f] == expected[f], f + ' differs')
        if REPORT:
            print('  %-40s %2d objects %6d bytes: code %5d, variables %5d; %11d cycles, %.2f minutes at '
                  '2 MHz; files opened %d, bytes read %d, written %d' % (
                      '+'.join(pieces), len(objects), lk_ram32.object_bytes(objects), size[0], size[1],
                      cycles, cycles / 2e6 / 60, *traffic))


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class UnderTheDfs(unittest.TestCase):
    """The same under the DFS's names and limits (--bbc-fs dfs), the image built with BBCFS 1:
    the build for a real disc."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-lk-ram32-dfs-')
        cls.image = lk_ram32.build_image(os.path.join(cls.dir, 'image'), 1)[0]
        cls.cache = os.path.join(cls.dir, 'cache')
        cls.chosen = [(('lextest',), 7)] + ([MODE7] if ALL else [])
        lk_ram32.build_programs(cls.cache, [p for ps, _ in cls.chosen for p in ps])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_it_links_as_the_host_linker_does(self):
        for pieces, mode in self.chosen:
            with self.subTest(pieces=pieces):
                work = tempfile.mkdtemp(dir=self.dir)
                main, objects = lk_ram32.glue(self.cache, pieces, os.path.join(work, 'objects'))
                size = lk_ram32.host_link(0, os.path.join(self.cache, 'measure.env'), main, objects)[3]
                env_path = lk_ram32.target_env(os.path.join(work, 'PROG.env'), size[0], size[1], mode)
                said, written, (host_status, expected), cycles, most = lk_ram32.bbc_link(
                    self.image, objects, main, env_path, work, dfs=True)
                self.assertEqual((said, host_status), ((0, b'', b''), 0))
                self.assertEqual(sorted(written), sorted(expected))
                for f in expected:
                    self.assertTrue(written[f] == expected[f], f + ' differs')
                self.assertLessEqual(most[0], 5)
                if REPORT:
                    print('\n  DFS: %-40s %11d cycles; at most %d files open, %d for writing'
                          % ('+'.join(pieces), cycles, *most))


if __name__ == '__main__':
    unittest.main()
