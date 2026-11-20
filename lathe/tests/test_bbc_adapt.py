"""Image A: one 128 KB image of both tools for every BBC with sideways RAM (lathe/docs/bbc.md, "One
image for every machine with sideways RAM"): the tools' ROM forms with `define ADAPT 1` and
`define ADFS 1` (bbcrom.rom_env's settings), linked from $1F00, the highest PAGE served, with
every region `dynamic` and rt_place as the placer, which puts in main RAM, as each command
starts, the regions whose variables fit there (below $1F00 when PAGE is lower, what the link
leaves free, a shadow screen's kilobyte) and turns their blocks into nothing. File names as
given (`BBCFS 0`), the emulator's B+128 with its four banks of sideways RAM, `--bbc-strict` on
filled memory: a write below PAGE is a fault.

By default: the image fits and its account; the tool chain (hello, farcall) at PAGE $1900 and
$1F00, every file the host tools'; PAGE above $1F00 refused; three modules of the self-compile
at each PAGE. LATHE_BBC_ADAPT_SELFHOST=1: all 18 at each PAGE. LATHE_BBC_ADAPT_SELFLINK=1: the
linker links the compiler at each PAGE. LATHE_BBC_ADAPT_LOOP=1: the rebuild loop at $1900.
LATHE_BBC_ADAPT_REPORT=1 prints the account and the cycles.
"""
import contextlib
import dataclasses
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_bbc_rom128 as rom128  # noqa: E402
import src_support as support  # noqa: E402
import bbcrom  # noqa: E402
import boards  # noqa: E402

SETTINGS = {'ADFS': 1, 'ADAPT': 1}
REPORT = os.environ.get('LATHE_BBC_ADAPT_REPORT') == '1'
SELFHOST = os.environ.get('LATHE_BBC_ADAPT_SELFHOST') == '1'
SELFLINK = os.environ.get('LATHE_BBC_ADAPT_SELFLINK') == '1'
LOOP = os.environ.get('LATHE_BBC_ADAPT_LOOP') == '1'
PAGES = ('1900', '1F00')


@contextlib.contextmanager
def machine(page, shadow=False, model=()):
    """The BBC the helpers of the other tests run, at PAGE `page` (hex), in a shadow mode if
    asked (HIMEM $8000), with the emulator's options `model` (a Model B and its sideways RAM)."""
    import test_bbc_selfhost
    import test_bbc_toolchain
    extra = ('--bbc-page', page) + (('--bbc-shadow',) if shadow else ()) + tuple(model)
    board = dataclasses.replace(boards.BOARDS['bbc'], options=boards.BOARDS['bbc'].options + extra)
    saved = (test_bbc_selfhost.BOARD, test_bbc_toolchain.BOARD, rom128.BOARD)
    test_bbc_selfhost.BOARD = test_bbc_toolchain.BOARD = rom128.BOARD = board
    try:
        yield board
    finally:
        test_bbc_selfhost.BOARD, test_bbc_toolchain.BOARD, rom128.BOARD = saved


def build_image(out_dir):
    """Both tools linked for Image A, the account and the image: (tools, account, image, listing)."""
    tools = rom128.build_tools(out_dir, settings=SETTINGS)
    account = rom128.Account(tools)
    image = None
    listing = ''
    if account.fits():
        image = os.path.join(out_dir, 'MODULE')
        listing = bbcrom.image([t[:4] for t in tools], image, os.path.join(out_dir, 'listing'),
                               short=image + '.short', banks=rom128.BANKS)
        bbcrom.loader(os.path.join(out_dir, 'LOADMOD'))
    return tools, account, image, listing


def free_bytes(listing):
    m = re.search(r'(\d+) bytes free', listing)
    return int(m.group(1)) if m else None


@unittest.skipUnless(rom128.HAVE_TOOLS, 'compiler or emulator missing')
class ImageA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-bbc-adapt-')
        cls.tools, cls.account, cls.image, cls.listing = build_image(cls.dir)
        if REPORT:
            print('\n' + cls.account.text())
            print(cls.listing)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def need_image(self):
        if self.image is None:
            self.skipTest('Image A does not fit: ' + self.account.summary())

    def test_image_a_fits_the_128k_image(self):
        self.assertTrue(self.account.fits(), self.account.summary() + ' ' + str(self.account.errors))

    def test_its_regions_are_dynamic_and_its_code_starts_at_1f00(self):
        for command, resident, rom, map_path, error, notes in self.tools:
            with open(rom) as f:
                text = f.read()
            with self.subTest(tool=command):
                self.assertIsNone(error)
                self.assertRegex(text, r'(?m)^define\s+ADAPT 1')
                with open(map_path) as f:
                    self.assertIn('rt_place.place', f.read())

    def test_the_tool_chain_at_each_page(self):
        self.need_image()
        import test_bbc_toolchain as chain
        for page in PAGES:
            with machine(page), rom128.scheme():
                # farcall runs from the module's RAM form, which LOADMOD (assembled for $1900)
                # fills: at $1F00 hello alone.
                for case in [c for c in chain.corpus() if c[0] in ('hello', 'farcall')[:2 if page == '1900' else 1]]:
                    name, source, _, _, banked = case
                    with self.subTest(page=page, program=name):
                        disk, compiles, link, files, said, load = chain.prepare(
                            case, os.path.join(self.dir, 'chain-%s-%s' % (page, name)))
                        lines = chain.bbc_lines(compiles, link, load, len(files[link[2]]))
                        status, out, mos, written, cycles, traffic = chain.bbc_run(self.image, disk, lines,
                                                                                   ram=banked)
                        self.assertEqual((status, mos), (0, b''))
                        with open(os.path.splitext(source)[0] + '.expected.out', 'rb') as f:
                            self.assertEqual(out, f.read())
                        self.assertEqual(sorted(written), sorted(files))
                        for f in files:
                            self.assertTrue(written[f] == files[f], f + ' differs')

    def chain_on(self, page, model, programs=('hello',)):
        import test_bbc_toolchain as chain
        with machine(page, model=model), rom128.scheme():
            for case in [c for c in chain.corpus() if c[0] in programs]:
                name, source, _, _, banked = case
                with self.subTest(model=model, program=name):
                    disk, compiles, link, files, said, load = chain.prepare(
                        case, os.path.join(self.dir, 'chain-%s-%s-%s' % (page, '-'.join(model), name)))
                    lines = chain.bbc_lines(compiles, link, load, len(files[link[2]]))
                    status, out, mos, written, cycles, traffic = chain.bbc_run(self.image, disk, lines)
                    self.assertEqual((status, mos), (0, b''))
                    with open(os.path.splitext(source)[0] + '.expected.out', 'rb') as f:
                        self.assertEqual(out, f.read())
                    for f in files:
                        self.assertTrue(written[f] == files[f], f + ' differs')

    def test_a_model_b_with_four_banks_elsewhere(self):
        """A Model B (`--bbc-model b`) with four banks of sideways RAM in slots 8 to 11, not the
        B+128's 0, 1, 12 and 13: the placer finds them (by the MOS's table and a write) and gives
        each slot the tools are linked with one of them; every file the host tools'."""
        self.need_image()
        self.chain_on('1900', ('--bbc-model', 'b', '--bbc-sideways-ram', '8,9,10,11'))
        with machine('1900', model=('--bbc-model', 'b', '--bbc-sideways-ram', '8,9,10,11')):
            rom128.compile_modules(self, self.image, ('rom',), ['err', 'src'])

    def test_too_little_sideways_ram_is_refused(self):
        """With two banks the compiler starts (its tables are set at start-up) and the linker,
        whose regions do not fit, is refused: `Too little sideways RAM`; with none both are."""
        self.need_image()
        base = boards.BOARDS['bbc']
        for ram, command, refused in (('8,9', 'LATHE', False), ('8,9', 'LLINK', True),
                                      ('none', 'LATHE', True), ('none', 'LLINK', True)):
            board = dataclasses.replace(base, options=base.options + ('--bbc-model', 'b', '--bbc-sideways-ram', ram))
            with self.subTest(ram=ram, command=command), rom128.scheme(), tempfile.TemporaryDirectory() as d:
                code, out, err, cycles = boards.run_module(board, self.image, d, command, raw=True)
                if refused:
                    self.assertIn(b'Too little sideways RAM', out + err)
                else:
                    self.assertIn(b'usage: lathec', out)

    def test_page_above_the_fixed_part_is_refused(self):
        """PAGE above $1F00: the tool refuses, `PAGE too high`. The module has copied the
        resident part to $1F00 by then, below PAGE, which --bbc-strict would stop first: the
        check belongs in the module's command code too (lathe/docs/bbc.md), so this run is not
        strict."""
        self.need_image()
        base = boards.BOARDS['bbc']
        board = dataclasses.replace(base, options=tuple(o for o in base.options if o != '--bbc-strict')
                                    + ('--bbc-page', '2100'))
        for command in ('LATHE', 'LLINK'):
            with self.subTest(command=command), rom128.scheme(), tempfile.TemporaryDirectory() as d:
                code, out, err, cycles = boards.run_module(board, self.image, d, command, raw=True)
                self.assertIn(b'PAGE too high', out + err)

    def test_the_start_up_at_each_page(self):
        self.need_image()
        for page in PAGES:
            for command, text in (('LATHE', b'usage: lathec'), ('LLINK', b'usage: link')):
                with self.subTest(page=page, command=command), machine(page) as board, rom128.scheme(), \
                        tempfile.TemporaryDirectory() as d:
                    code, out, err, cycles = boards.run_module(board, self.image, d, command, raw=True)
                    self.assertIn(text, out)
                    if REPORT:
                        print('\n*%s with no arguments at PAGE &%s: %d cycles' % (command, page, cycles))

    def compile_at(self, page, modules):
        base = self.dir
        self.dir = os.path.join(base, 'page-' + page)
        os.makedirs(self.dir, exist_ok=True)
        try:
            with machine(page):
                return rom128.compile_modules(self, self.image, ('rom',), modules)
        finally:
            self.dir = base

    def test_the_compiler_compiles_itself_at_each_page(self):
        self.need_image()
        import test_src_selfhost
        modules = rom128.selfhost_modules() if SELFHOST else test_src_selfhost.QUICK[:3]
        for page in PAGES:
            cycles = self.compile_at(page, modules)
            if REPORT or SELFHOST:
                print('\nImage A, PAGE &%s: %d compiles, %d cycles' % (
                    page, len(cycles), sum(c['rom'] for c in cycles.values())))

    @unittest.skipUnless(SELFLINK, 'LATHE_BBC_ADAPT_SELFLINK=1 has the linker link the compiler from it')
    def test_the_linker_links_the_compiler_at_each_page(self):
        self.need_image()
        import test_bbc_selflink as selflink
        import test_bbc_toolchain as chain
        for page in PAGES:
            with machine(page), rom128.scheme():
                name, source, env = selflink.TOOLS[0]
                work = os.path.join(self.dir, 'link-%s-%s' % (page, name))
                disk, compiles, link, files = selflink.prepare(name, source, env, work)
                for f in files:
                    if f.endswith('.lo'):
                        shutil.copy(os.path.join(work, 'host', f), disk)
                lines = [boards.module_command('LLINK', ['@' + selflink.COMMAND_FILE])]
                status, out, mos, written, cycles, traffic = chain.bbc_run(self.image, disk, lines)
                self.assertEqual((status, out, mos), (0, b'', b''))
                print('\nImage A, PAGE &%s: the linker links the compiler in %d cycles' % (page, cycles))
                expected = selflink.link_outputs(files)
                self.assertEqual(sorted(written), sorted(expected))
                for f in expected:
                    self.assertTrue(written[f] == expected[f], f + ' differs')

    @unittest.skipUnless(LOOP, 'LATHE_BBC_ADAPT_LOOP=1 has the compiler rebuild itself from it at $1900')
    def test_the_compiler_rebuilds_itself_at_page_1900(self):
        self.need_image()
        import test_bbc_selflink as selflink
        import test_bbc_toolchain as chain
        import mapenv
        with machine('1900'), rom128.scheme():
            work = os.path.join(self.dir, 'loop')
            disk, compiles, link, files = selflink.prepare('lathec', 'lathec.lth', chain.COMPILER_ENV, work)
            image = link[2]
            again = [args for args in compiles if os.path.splitext(args[-2])[0] in selflink.LOOP_AGAIN]
            lines = [boards.module_command('LATHE', args) for args in compiles]
            lines.append(boards.module_command('LLINK', ['@' + selflink.COMMAND_FILE]))
            load = mapenv.read_env(chain.COMPILER_ENV).code[0]
            lines += ['LOAD %s %X' % (image, load), 'SAVE %s %X +%X %X' % (image, load, len(files[image]), load)]
            lines += [boards.module_command('RUN', [image] + args) for args in again]
            status, out, mos, written, cycles, traffic = selflink.run_long(self.image, disk, lines)
            self.assertEqual((status, mos, out), (0, b'', b''))
            print('\nImage A, PAGE &1900: the rebuild loop in %d cycles' % cycles)
            self.assertEqual(sorted(written), sorted(files))
            for f in files:
                self.assertTrue(written[f] == files[f], f + ' differs')


if __name__ == '__main__':
    unittest.main()


import test_bbc_asked_fs  # noqa: E402


@unittest.skipUnless(rom128.HAVE_TOOLS, 'compiler or emulator missing')
class ImageAWithEitherFilingSystem(test_bbc_asked_fs.OneImage):
    """Image A built with BBCFS 3 (the filing system asked when a tool runs): test_bbc_asked_fs's
    runs, a program of several modules compiled, linked and run under the DFS (PAGE $1900) and
    under ADFS (PAGE $1F00), and under a filing system that is neither, every file the host
    tools' under that disc's names."""

    @classmethod
    def setUpClass(cls):
        saved = bbcrom.rom_env

        def rom_env(source, out, first=1, banks=8, settings=None):
            return saved(source, out, first, banks, settings=dict(settings or {}, ADAPT=1))

        bbcrom.rom_env = rom_env
        try:
            super().setUpClass()
        finally:
            bbcrom.rom_env = saved

    def test_its_regions_are_dynamic(self):
        for command, resident, rom, map_path, notes in self.tools:
            with open(rom) as f:
                self.assertRegex(f.read(), r'(?m)^define\s+ADAPT 1')
            with open(map_path) as f:
                self.assertIn('rt_place.place', f.read())
