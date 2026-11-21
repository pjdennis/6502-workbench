"""Image A (test_bbc_adapt.py) on the emulator's Master-like machine (`--bbc-model master`:
emulator/README.md; lathe/docs/bbc.md, "Image A on a Master-like machine"): PAGE $0E00, sideways
RAM in slots 4 to 7, the module in slot 8, stand-ins for the MOS's own ROMs in 9 to 15 (in the
ROM type table, so the placer's probe skips them), the emulator's 65C02 core, mode 7 (HIMEM
$7C00) or a shadow mode ($8000); `--bbc-strict` on filled memory.

By default: *LATHE and *LLINK start and place every table where the placer's model
(places.plan, places.apply) says, each capacity variable what it says, in mode 7 and in a shadow
mode, on the 65C02 core and the NMOS one (main RAM read back with --bbc-ram-dump); the compiler's
OUTTAB and the linker's LKNODES go below $1F00; hello and calls compiled, linked and run, every
file the host tools'; three modules of the self-compile, every file the host compiler's.
LATHE_BBC_MASTER_SELFHOST=1: all 18 modules. LATHE_BBC_MASTER_SELFLINK=1: the linker links the
compiler. LATHE_BBC_MASTER_NMOS=1: those runs on the NMOS core (the B+'s), to compare cycles.
Capacities on the Master beside the other machines: test_bbc_rooms.py.
"""
import dataclasses
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_bbc_rom128 as rom128  # noqa: E402
import test_bbc_adapt  # noqa: E402
import boards  # noqa: E402
import places  # noqa: E402

SELFHOST = os.environ.get('LATHE_BBC_MASTER_SELFHOST') == '1'
SELFLINK = os.environ.get('LATHE_BBC_MASTER_SELFLINK') == '1'
NMOS = os.environ.get('LATHE_BBC_MASTER_NMOS') == '1'
MASTER = ('--bbc-model', 'master') + (('--cpu', 'nmos') if NMOS else ())
PAGE = 0x0E00
SLOTS = (4, 5, 6, 7)            # the Master's sideways RAM
MODULE_SLOT = 8                 # the emulator's slot for the module on the Master
HIMEM = {False: 0x7C00, True: 0x8000}


def placement(tool, ram, himem, slots=SLOTS):
    """The placer's model for `tool` (test_bbc_adapt.build_image's) on the Master at `himem` with
    free sideways RAM in `slots`, and
    how main RAM `ram` (as the tool left it) differs from it at each place of the tool's list
    (high bytes and blocks' banks: places.apply) and in each capacity variable: (the plan by
    region name, [differences])."""
    p, names = places.of_tool(*tool[1:4])
    done = places.plan(p, PAGE, himem, slots)
    with open(tool[1], 'rb') as f:
        image = f.read()
    model = places.apply(image, p.code_lo, p, {i: d.where for i, d in done.items()},
                         {i: d.slot for i, d in done.items() if d.slot is not None},
                         module_slot=MODULE_SLOT, steps={i: d.steps for i, d in done.items()})
    differ = []
    for i, r in enumerate(p.regions):
        for a in r.highs + r.banks:
            if ram[a] != model[a - p.code_lo]:
                differ.append((names[i], '$%04X' % a, ram[a], model[a - p.code_lo]))
        if r.room and i in done:
            got = ram[r.room] | ram[r.room + 1] << 8
            if got != done[i].room:
                differ.append((names[i], 'capacity', got, done[i].room))
    return {names[i]: d for i, d in done.items()}, differ


@unittest.skipUnless(rom128.HAVE_TOOLS, 'compiler or emulator missing')
class OnTheMaster(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-bbc-master-')
        cls.tools, cls.account, cls.image, cls.listing = test_bbc_adapt.build_image(cls.dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def setUp(self):
        if self.image is None:
            self.skipTest('Image A does not fit: ' + self.account.summary())

    def test_the_tools_place_their_tables_as_the_model_says(self):
        """With its four banks and with two (4 and 5: as if 6 and 7 held ROM images), in mode 7
        and a shadow mode, on either core: every place and capacity as the model has it, the
        compiler's OUTTAB and the linker's LKNODES below $1F00, the rest in the slots."""
        base = boards.BOARDS['bbc']
        for tool, text in zip(self.tools, (b'usage: lathec', b'usage: link')):
            for slots in (SLOTS, (4, 5)):
                for shadow in (False, True):
                    for cpu in ((), ('--cpu', 'nmos')):
                        with self.subTest(tool=tool[0], slots=slots, shadow=shadow, cpu=cpu), rom128.scheme(), \
                                tempfile.TemporaryDirectory() as d:
                            dump = os.path.join(d, 'ram.bin')
                            options = ('--bbc-model', 'master', '--bbc-ram-dump', dump,
                                       '--bbc-sideways-ram', ','.join(map(str, slots))) + cpu + \
                                (('--bbc-shadow',) if shadow else ())
                            board = dataclasses.replace(base, options=base.options + options)
                            code, out, err, cycles = boards.run_module(board, self.image, d, tool[0], raw=True)
                            self.assertIn(text, out)
                            self.assertIn(b'module: slot 8,', err)
                            self.assertIn(b'mos-memory-writes=0  romsel-mismatches=0  screen-writes=0', err)
                            with open(dump, 'rb') as f:
                                ram = f.read()
                            done, differ = placement(tool, ram, HIMEM[shadow], slots)
                            self.assertEqual(differ, [])
                            below = sorted(n for n, p in done.items() if p.slot is None)
                            self.assertEqual(below, ['outtab'] if tool[0] == 'LATHE' else ['lknodes'])
                            for n in below:
                                self.assertTrue(PAGE <= done[n].where < 0x1F00, (n, hex(done[n].where)))
                            used = sorted({p.slot for p in done.values()} - {None})
                            self.assertEqual(used, list(slots) if tool[0] == 'LLINK' or len(slots) == 2
                                             else [4, 5, 6])
                            print('\n*%s on the Master, sideways RAM %s%s%s: %d cycles to the usage line' % (
                                tool[0], ','.join(map(str, slots)), ', shadow mode' if shadow else '',
                                ' (NMOS core)' if cpu else '', cycles))

    def test_the_tool_chain(self):
        """hello and calls compiled by *LATHE, linked by *LLINK and run on the Master, every file
        the host tools'."""
        import test_bbc_toolchain as chain
        with test_bbc_adapt.machine('0E00', model=MASTER), rom128.scheme():
            for case in [c for c in chain.corpus() if c[0] in ('hello', 'calls')]:
                name, source, _, _, banked = case
                with self.subTest(program=name):
                    disk, compiles, link, files, said, load = chain.prepare(case, os.path.join(self.dir, 'chain-' + name))
                    lines = chain.bbc_lines(compiles, link, load, len(files[link[2]]))
                    status, out, mos, written, cycles, traffic = chain.bbc_run(self.image, disk, lines)
                    self.assertEqual((status, mos), (0, b''))
                    with open(os.path.splitext(source)[0] + '.expected.out', 'rb') as f:
                        self.assertEqual(out, f.read())
                    self.assertEqual(sorted(written), sorted(files))
                    for f in files:
                        self.assertTrue(written[f] == files[f], f + ' differs')

    def test_the_compiler_compiles_itself(self):
        import test_src_selfhost
        modules = rom128.selfhost_modules() if SELFHOST else test_src_selfhost.QUICK[:3]
        with test_bbc_adapt.machine('0E00', model=MASTER):
            cycles = rom128.compile_modules(self, self.image, ('rom',), modules)
        print('\nImage A on the Master%s: %d compiles, %d cycles' % (
            ' (NMOS core)' if NMOS else '', len(cycles), sum(c['rom'] for c in cycles.values())))

    @unittest.skipUnless(SELFLINK, 'LATHE_BBC_MASTER_SELFLINK=1 has the linker link the compiler')
    def test_the_linker_links_the_compiler(self):
        import test_bbc_selflink as selflink
        import test_bbc_toolchain as chain
        with test_bbc_adapt.machine('0E00', model=MASTER), rom128.scheme():
            name, source, env = selflink.TOOLS[0]
            work = os.path.join(self.dir, 'link-' + name)
            disk, compiles, link, files = selflink.prepare(name, source, env, work)
            for f in files:
                if f.endswith('.lo'):
                    shutil.copy(os.path.join(work, 'host', f), disk)
            lines = [boards.module_command('LLINK', ['@' + selflink.COMMAND_FILE])]
            status, out, mos, written, cycles, traffic = chain.bbc_run(self.image, disk, lines)
            self.assertEqual((status, out, mos), (0, b'', b''))
            print('\nImage A on the Master%s: the linker links the compiler in %d cycles' % (
                ' (NMOS core)' if NMOS else '', cycles))
            expected = selflink.link_outputs(files)
            self.assertEqual(sorted(written), sorted(expected))
            for f in expected:
                self.assertTrue(written[f] == expected[f], f + ' differs')


if __name__ == '__main__':
    unittest.main()
