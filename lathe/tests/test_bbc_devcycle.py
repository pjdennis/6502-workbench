"""The developer's cycle for the images that ship (lathe/docs/bbc.md, "The developer's cycle",
"For the images that ship"): Image A's tools and Image B's rebuilt on the B+128 with the developer's
linker, the full linker with dynamic regions (`LKDYN 1`), which the shipped ROM forms leave out.

The developer's linker is the linker's 128 KB layout (`ROM128 1`) with a fourth bank, in the
sixteen-bank RAM form after the image's own tools: bbcrom.rom_env(linker-bbc.env, ..., 8, 16,
settings=DEVLINK_SETTINGS) numbers its banks 8 to 11 of the module, and `when ROM128 when LKDYN`
in linker-bbc.env gives the fourth bank (lk_map, lk_dyn, lk_boot and lk_win). It is the module's
`*DEVLINK`, beside the image's `*LATHE` and `*LLINK`, in bbcrom.py's whole layout: the image's tools
in banks 0 to 7 as they ship, DEVLINK 8 to 11, the home bank 12, the resident parts 13 to 15.

By default (about a minute): rom_env's settings reach a conditional define; the developer's
linker fits its four banks and main RAM at ADFS's PAGE; Image A's module (ImageAModule): MODLOAD
loads it from nothing and each tool into it, a resident part with its list of places checked by
the list's first word, and the tools start and compile from it.

LATHE_BBC_DEVCYCLE=1 (about ten minutes; LATHE_BBC_DEVCYCLE_TOOL=LATHE or LLINK for one tool):
ImageACycle, each of Image A's tools on its pair of ADFS discs (test_bbc_cycle's layout): its
modules compiled by *LATHE, linked by *DEVLINK, loaded by MODLOAD, every file the host tools'
and the module bbcrom.py's whole image; then hello compiled, linked and run by the new tools.
ImageBCycle, Image B's tools compiled and linked on the B+128 so (the linker's link two bytes
from the host's: a fault of lk_dyn, see there); ImageBFromTheBBC, test_bbc_image_b's runs on a
Model B with no sideways RAM from the 128 KB image of Image B's compiler as the B+128 linked it,
the same bytes as the host's; with LATHE_BBC_IMAGE_B_PROGRAMS=1 too, its largest programs.
"""
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import src_support as support  # noqa: E402
import bbcrom  # noqa: E402
import build  # noqa: E402

HAVE_TOOLS = os.path.isfile(support.EMULATOR) and os.path.isfile(build.COMPILER)
LINKER_ENV = os.path.join(support.SRC, 'linker-bbc.env')
DEVLINK = 'DEVLINK'
DEVLINK_FIRST = 8                   # its banks of the module: 8 to 11, after the image's 0 to 7
DEVLINK_SETTINGS = {'ADFS': 1, 'BBCFS': 3, 'ROM128': 1, 'LKDYN': 1}
DEVLINK_BANKS = 4


def devlink_env(out):
    """The developer's linker's ROM environment, written to out; the next bank free."""
    return bbcrom.rom_env(LINKER_ENV, out, DEVLINK_FIRST, 16, settings=DEVLINK_SETTINGS)


def build_devlink(out_dir, judged=False):
    """The developer's linker, linked by the host linker (lk_judged.py with judged): (command,
    resident image, ROM environment, map, the judged notes or None)."""
    import test_bbc_rom128 as rom128
    d = os.path.join(out_dir, DEVLINK.lower())
    os.makedirs(d)
    rom = os.path.join(d, 'linker-bbc.env')
    devlink_env(rom)
    resident = os.path.join(d, DEVLINK)
    notes = os.path.join(d, 'judged')
    saved = build.LINKER
    if judged:
        os.environ['LK_JUDGED_OUT'] = notes
        build.LINKER = rom128.JUDGED
    try:
        build.build(os.path.join(support.SRC, 'link.lth'), resident, env=rom, keep=os.path.join(d, 'work'))
    finally:
        build.LINKER = saved
        os.environ.pop('LK_JUDGED_OUT', None)
    return (DEVLINK, resident, rom, os.path.join(d, 'work', 'link.map'),
            rom128.read_judged(notes) if judged else None)


COMPILER_ENV = os.path.join(support.SRC, 'lathec-bbc.env')
# Each image's tools as they ship, (command, source, environment, settings), numbered from bank 0
# of the eight-bank image: Image A's (test_bbc_adapt with BBCFS 3, the filing system asked when
# a tool runs), Image B's (test_bbc_image_b's). The module for Image B's has the plain image's
# compiler in Image B's compiler's place: Image B's compiles 54 of the 79 modules of lathe/src and
# lathe/rt, not the tools', and a module's dynamic regions are placed in main RAM alone or with
# the sideways RAM probed, not both, so Image A's compiler cannot be beside Image B's linker.
IMAGE_A = (('LATHE', 'lathec.lth', COMPILER_ENV, {'ADFS': 1, 'BBCFS': 3, 'ADAPT': 1}),
           ('LLINK', 'link.lth', LINKER_ENV, {'ADFS': 1, 'BBCFS': 3, 'ADAPT': 1}))
IMAGE_B = (('LATHE', 'lathec.lth', COMPILER_ENV, {'RAM32': 1, 'ADAPT': 1, 'BBCFS': 3}),
           ('LLINK', 'link.lth', LINKER_ENV, {'RAM32': 1, 'ADAPT': 1, 'ADFS': 1, 'BBCFS': 3}))
PLAIN_COMPILER = ('LATHE', 'lathec.lth', COMPILER_ENV, {'ADFS': 1, 'BBCFS': 3})
MODULE_B = (PLAIN_COMPILER, IMAGE_B[1])


def build_image_tools(out_dir, specs):
    """The tools specs [(command, source, environment, settings)] in their eight-bank ROM forms,
    the first from bank 0: [(command, resident image, ROM environment, map)]."""
    tools, first = [], 0
    for command, source, env, settings in specs:
        d = os.path.join(out_dir, command.lower())
        os.makedirs(d)
        rom = os.path.join(d, os.path.basename(env))
        first = bbcrom.rom_env(env, rom, first, 8, settings=settings)
        resident = os.path.join(d, command)
        build.build(os.path.join(support.SRC, source), resident, env=rom, keep=os.path.join(d, 'work'))
        tools.append((command, resident, rom, os.path.join(d, 'work', os.path.splitext(source)[0] + '.map')))
    return tools


def build_module(out_dir, specs):
    """The developer's module: the tools specs and the developer's linker in bbcrom.py's whole
    layout of sixteen banks, and its home bank alone: (tools [(command, resident, ROM environment,
    map)], the whole image, HOME)."""
    tools = build_image_tools(out_dir, specs) + [build_devlink(out_dir)[:4]]
    image, home = os.path.join(out_dir, 'WHOLE'), os.path.join(out_dir, 'HOME')
    bbcrom.image(tools, image, os.path.join(out_dir, 'listing'), banks=16, whole=True, home=home)
    return tools, image, home


def tool_files(tools):
    """test_modload.tool_files with the developer's linker's files on drive 1 (`1/`): its bank
    files have the names of the image's linker's (LLINK1.BIN to LLINK4.BIN)."""
    import test_modload as modload
    files, args = modload.tool_files([t for t in tools if t[0] != DEVLINK])
    dev, dev_args = modload.tool_files([t for t in tools if t[0] == DEVLINK])
    files.update({'1/' + name: data for name, data in dev.items()})
    return files, args + ['1/' + a for a in dev_args]


class RomEnv(unittest.TestCase):
    def test_a_setting_reaches_a_define_under_when_or_unless(self):
        """`settings` sets a define of the name wherever it is, under `when` and `unless` too, so
        that the developer's linker is the ROM form with LKDYN 1; a define with no such name is
        still an error."""
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, 'a.env')
            with open(src, 'w') as f:
                f.write('define    ROMFORM 0\nunless    ROMFORM define LKDYN 1  ; the developer\'s\n'
                        'when      ROMFORM define LKDYN 0\nwindow    WIN $8000 $BFDF\n')
            out = os.path.join(d, 'b.env')
            bbcrom.rom_env(src, out, 1, 16, settings={'LKDYN': 1})
            with open(out) as f:
                lines = f.read().splitlines()
            self.assertEqual(lines[1:3], ['unless    ROMFORM define LKDYN 1  ; the developer\'s',
                                          'when      ROMFORM define LKDYN 1'])
            with self.assertRaises(bbcrom.ImageError):
                bbcrom.rom_env(src, out, 1, 16, settings={'NONE': 1})


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class TheDevelopersLinker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-devlink-')
        cls.tool = build_devlink(cls.dir, judged=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_it_has_dynamic_regions_in_four_banks_after_the_image(self):
        import mapenv
        command, resident, rom, map_path, (notes, fixed) = self.tool
        env = mapenv.read_env(rom)
        self.assertIn(('LKDYN', 1), [(n.upper(), v) for n, v in env.defines])
        _, _, banks = bbcrom.read_env_banks(rom)
        self.assertEqual([b.value for b in banks if b.value & 0x80],
                         [0x80 + DEVLINK_FIRST + i for i in range(DEVLINK_BANKS)])
        self.assertTrue(all(b.rom for b in banks if b.value & 0x80))
        with open(map_path) as f:
            self.assertIn('lk_dyn.', f.read())

    def test_each_bank_and_main_ram_hold_it(self):
        import mapenv
        import test_bbc_adfs as adfs
        command, resident, rom, map_path, (notes, fixed) = self.tool
        self.assertEqual(sorted(notes), list(range(1, DEVLINK_BANKS + 1)))
        for n, (judged, placed, modules) in notes.items():
            self.assertLessEqual(judged, bbcrom.ROOM, (n, modules))
        env = mapenv.read_env(rom)
        code_end, lo, hi, more, free = adfs.room(map_path)
        self.assertEqual(env.code[0], adfs.PAGE)
        self.assertLessEqual(code_end, env.code[1] + 1)
        self.assertGreaterEqual(lo, env.data[0])
        self.assertLessEqual(hi, adfs.HIMEM)


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class ImageAModule(unittest.TestCase):
    """The module for Image A's developer: Image A's *LATHE (banks 0 to 4) and *LLINK (5 to 7) as
    they ship, *DEVLINK (8 to 11), the home bank 12, the resident parts 13 to 15. MODLOAD loads it
    from nothing and one tool into it: a resident part of Image A holds its list of places after
    the code the map gives, which MODLOAD checks by its first word, the code range's start."""

    @classmethod
    def setUpClass(cls):
        import test_modload as modload
        cls.dir = tempfile.mkdtemp(prefix='lathe-devmodule-')
        cls.modload = modload.build_modload(os.path.join(cls.dir, 'modload'))
        cls.tools, cls.whole, cls.home = build_module(os.path.join(cls.dir, 'tools'), IMAGE_A)
        cls.files, cls.args = tool_files(cls.tools)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def disc(self, files=None):
        import test_modload as modload
        return modload.OnTheBBC.disc(self, files)

    def run_lines(self, disk, lines, dump=None, preload=None):
        import test_modload as modload
        return modload.OnTheBBC.run_lines(self, disk, lines, dump, preload)

    def assert_whole_image(self, dump):
        import test_modload as modload
        modload.OnTheBBC.assert_whole_image(self, dump)

    def test_the_layout(self):
        with open(self.home, 'rb') as f:
            d = f.read()[-16:]
        self.assertEqual(d[:6], b'LW\x01\x0C\x03\x01')
        self.assertEqual(list(d[8:]), [0x1F, 0x00, 0xE0, 0x00, 0x00, 0x0F, 0, 0])

    def test_modload_loads_it_and_the_tools_run(self):
        """From an empty RAM form: the whole image; then *LATHE compiles a module as the host
        compiler does, placing its tables as it starts, and *DEVLINK and *LLINK give the usage."""
        import subprocess
        import bbcfs
        import test_bbc_adfs as adfs
        disk = self.disc()
        hello = b'module hello\nvar x: byte\npub func main()\n  x = 72\nend\n'
        adfs.put(disk, 'hello.lth', hello)
        host = tempfile.mkdtemp(dir=self.dir)
        with open(os.path.join(host, 'hello.lth'), 'wb') as f:
            f.write(hello)
        dump = os.path.join(self.dir, 'dump')
        load = 'RUN MODLOAD HOME ' + ' '.join(self.args)
        status, out, said, report = self.run_lines(disk, [load, 'LATHE -c6502 hello.lth .'], dump)
        self.assertEqual((status, out, said), (0, b'', b''), report)
        self.assert_whole_image(dump)
        r = subprocess.run([sys.executable, build.COMPILER, '-c6502', 'hello.lth', '.'], cwd=host,
                           capture_output=True)
        self.assertEqual(r.returncode, 0)
        for name in ('hello.lo', 'hello.li'):
            with open(bbcfs.adfs_host_path(disk, name), 'rb') as f, open(os.path.join(host, name), 'rb') as g:
                self.assertEqual(f.read(), g.read(), name)
        r = subprocess.run([sys.executable, build.LINKER], capture_output=True)
        for command in ('LLINK', DEVLINK):
            with self.subTest(command=command):
                status, out, said, report = self.run_lines(self.disc(), [command], preload=self.whole)
                self.assertEqual((status, out), (r.returncode, r.stdout + r.stderr), report)

    def test_one_tool_into_the_module_there(self):
        import test_modload as modload
        for i, (command, banks) in enumerate((('LATHE', (0, 1, 2, 3, 4, 13)), ('LLINK', (5, 6, 7, 14)),
                                               (DEVLINK, (8, 9, 10, 11, 15)))):
            with self.subTest(command=command):
                before = modload.OnTheBBC.image_with(self, modload.OnTheBBC.wipe(banks))
                dump = os.path.join(self.dir, 'dump-' + command)
                line = 'RUN MODLOAD ' + ' '.join(self.args[3 * i:3 * i + 3])
                status, out, said, report = self.run_lines(self.disc(), [line], dump, preload=before)
                self.assertEqual((status, out, said), (0, b'', b''), report)
                self.assert_whole_image(dump)

    def test_a_list_of_places_not_the_maps_is_refused(self):
        """An image of Image A's linker whose list does not start where its map's code ends with
        the code range's start, or that runs past the code range: refused, the module as it was."""
        import mapenv
        import test_bbc_adfs as adfs
        command, resident, rom, map_path = self.tools[1]
        start, last = mapenv.read_env(rom).code
        image = bytearray(self.files['LLINK'])
        at = adfs.room(map_path)[0] - start
        self.assertEqual(image[at:at + 2], start.to_bytes(2, 'little'))
        self.assertGreater(len(image), at + 2)
        wrong = bytearray(image)
        wrong[at + 1] += 1
        longer = bytes(image) + bytes(last + 2 - start - len(image))
        for n, data in enumerate((bytes(wrong), longer)):
            with self.subTest(case=n):
                disk = self.disc()
                adfs.put(disk, 'LLINK', data)
                dump = os.path.join(self.dir, 'dump-list-%d' % n)
                line = 'RUN MODLOAD ' + ' '.join(self.args[3:6])
                status, out, said, report = self.run_lines(disk, [line], dump, preload=self.whole)
                self.assertEqual(status, 2, report)
                self.assertTrue(out.startswith(b'modload: not the size its map gives: '), out)
                with open(self.whole, 'rb') as f, open(dump, 'rb') as g:
                    self.assertEqual(f.read(), g.read())


# ---- The cycle (opt-in) -------------------------------------------------------------------------

CYCLE = os.environ.get('LATHE_BBC_DEVCYCLE') == '1'
ONLY = os.environ.get('LATHE_BBC_DEVCYCLE_TOOL')
CAP = 14_000_000_000
# The change each tool's sources carry in copies, to show which tool ran (test_bbc_cycle.TOOLS's
# for the compiler, the version byte of the interface files; for the linker the name of the start
# code in every map, since the image's own linker does not link the tools here: the developer's
# linker does, from the host, and the new *LLINK then links a program).
CHANGES = {
    'LATHE': [('src/decl.lth', 'const LI_VERSION = 2', 'const LI_VERSION = 3'),
              ('host/decl.py', 'LI_VERSION = 2', 'LI_VERSION = 3')],
    'LLINK': [('src/lk_map.lth', 'const START_NAME: [6]byte = "$start"', 'const START_NAME: [6]byte = "$START"'),
              ('host/lk_map.py', 'START_NAME = b"$start"', 'START_NAME = b"$START"')],
}
SOURCES = {'LATHE': 'lathec.lth', 'LLINK': 'link.lth'}


def changed_tree(work, command, changes):
    """Copies of lathe/src and lathe/host in work with the changes [(file, old, new)]: (src, host)."""
    src, host = os.path.join(work, 'src'), os.path.join(work, 'host')
    shutil.copytree(support.SRC, src)
    shutil.copytree(os.path.join(os.path.dirname(support.SRC), 'host'), host,
                    ignore=shutil.ignore_patterns('__pycache__'))
    for name, old, new in changes:
        path = os.path.join(work, name)
        with open(path) as f:
            text = f.read()
        assert text.count(old) == 1, (name, old)
        with open(path, 'w') as f:
            f.write(text.replace(old, new))
    return src, host


_named = set()


def named_in_sources():
    """The words of lathe/src, lathe/rt and lathe/rt/bbc's sources (a define none of them names
    cannot change what the compiler writes)."""
    import glob
    import re
    if not _named:
        rt = os.path.join(os.path.dirname(support.SRC), 'rt')
        for path in glob.glob(os.path.join(support.SRC, '*.lth')) + glob.glob(os.path.join(rt, '*.lth')) + \
                glob.glob(os.path.join(rt, 'bbc', '*.lth')):
            with open(path) as f:
                _named.update(re.findall(r'\w+', f.read()))
    return _named


def on_the_command_line(args):
    """A compile's arguments as the developer types them on the BBC: the host's (build.py gives
    the compiler every define of the environment), or, if *LATHE's tail would be longer than the
    module copies (boards.ROM_TAIL: Image B's compiler, whose options alone are 249 bytes), without
    the defines no source names (FIXED_REGIONS, HIGHEST_PAGE and ROM128 there: the module and
    bbcrom.py read them, the compiler does not), which leaves every file the compiler writes the
    same (the test compares them with the host's of the whole command)."""
    import boards
    if len(' '.join(args)) <= boards.ROM_TAIL:
        return args
    return [a for a in args if not (a.startswith('-d') and a[2:].split('=')[0] not in named_in_sources())]


class DevCycle:
    """A tool of an image rebuilt on its pair of ADFS discs (test_bbc_cycle's layout) by the module
    `MODULE` holds from power on: *LATHE compiles each of its modules, *DEVLINK @LINKARG links its
    ROM form, and, if the tool is the module's own, *RUN MODLOAD loads it into its banks; every
    file on both drives the host tools' of the same commands, the module's sixteen banks
    bbcrom.py's whole image of the host's link outputs. With `turns` 2 the second turn runs on the
    module the first left. Then hello compiled, linked and run by the module's *LATHE and *LLINK
    on a disc of its own, every file the host tools' (with the change of the tool loaded)."""
    MODULE = None                     # the module's tools' specs
    TOOLS = None                      # the specs of the tools rebuilt

    @classmethod
    def setUpClass(cls):
        import test_modload as modload
        cls.dir = tempfile.mkdtemp(prefix='lathe-devcycle-')
        cls.modload = modload.build_modload(os.path.join(cls.dir, 'modload'))
        cls.tools, cls.whole, cls.home = build_module(os.path.join(cls.dir, 'module'), cls.MODULE)
        built = build_image_tools(os.path.join(cls.dir, 'image'), cls.TOOLS)
        cls.image_tools = {t[0]: t for t in built}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def whole_image(self, command, resident, out):
        """The whole image with `command` replaced by the link whose resident image is `resident`."""
        tools = [(c, resident, env) if c == command else (c, r, env, m) for c, r, env, m in self.tools]
        bbcrom.image(tools, out, os.path.join(self.dir, 'listing'), banks=16, whole=True)
        return out

    def assert_module(self, dump, want):
        import test_bbc_cycle
        test_bbc_cycle.Cycle.assert_module(self, dump, want)

    def cycle(self, command, turns, changes, loaded):
        """The tool `command` of TOOLS: `turns` turns, with the changes; loaded, if MODLOAD puts it
        in the module. Returns (the BBC's disc of the last turn, the host's, the link's arguments,
        the module as the last turn left it)."""
        import bbcfs
        import boards
        import test_bbc_adfs as adfs
        import test_bbc_cycle
        work = os.path.join(self.dir, command.lower())
        os.makedirs(work)
        src, host = changed_tree(work, command, changes)
        rom_env = self.image_tools[command][2]
        disk, compiles, link, load = test_bbc_cycle.lay_out_pair(work, os.path.join(src, SOURCES[command]),
                                                                 rom_env, self.modload)
        changed = changes and command == 'LATHE'
        compilers = [build.COMPILER, os.path.join(host, 'lathec.py') if changed else build.COMPILER]
        bbc = os.path.join(work, 'bbc')
        os.makedirs(bbc)
        for f, d in adfs.files_of(disk).items():
            adfs.put(bbc, f, d)
        with open(bbcfs.adfs_host_path(bbc, 'MODLOAD') + '.inf', 'w') as f:
            f.write(boards.inf_text('$.MODLOAD', adfs.PAGE, os.path.getsize(self.modload)))
        hosts, previous = [], disk
        for turn in range(turns):
            h = os.path.join(work, 'host%d' % turn)
            shutil.copytree(previous, h)
            test_bbc_cycle.host_turn(h, compiles, link, compilers[turn], build.LINKER)
            hosts.append(h)
            previous = h
        lines = [boards.module_command('LATHE', on_the_command_line(args)) for args in compiles]
        lines.append(boards.module_command(DEVLINK, ['@' + test_bbc_cycle.COMMAND_FILE]))
        if loaded:
            lines.append(boards.module_command('RUN', ['MODLOAD'] + load))
        module = self.whole
        saved, adfs.CAP = adfs.CAP, CAP
        try:
            for turn in range(turns):
                dump = os.path.join(work, 'module%d' % turn)
                status, out, mos, written, cycles, report = adfs.run_adfs(
                    module, bbc, lines, ram=True, extra=('--bbc-module-dump', dump))
                cat = adfs.catalogue(bbc)
                print('\n%s of %s, turn %d: %d cycles, %.1f minutes at 2 MHz; most open %d, writing %d, '
                      'most entries %d' % ((command, self.__class__.__name__, turn + 1, cycles,
                                            cycles / 2e6 / 60) + report[:3]))
                for line in adfs.account(cat, report):
                    print('    ' + line)
                self.assertEqual((status, out, mos), (0, b'', b''))
                want = test_bbc_cycle.on_the_bbc(adfs.files_of(hosts[turn]))
                with open(self.modload, 'rb') as f:
                    want[bbcfs.adfs_host_file('MODLOAD')] = f.read()
                got = adfs.files_of(bbc)
                self.assertEqual(sorted(got), sorted(want))
                for f in want:
                    self.assertTrue(got[f] == want[f], f + ' differs')
                self.assert_module(dump, self.whole_image(command, os.path.join(hosts[turn], link[2]),
                                                          os.path.join(work, 'whole%d' % turn))
                                   if loaded else self.whole)
                self.assertEqual(report[:2], (2, 1))
                for d, (_, _, n, most) in cat.items():
                    self.assertEqual(report[3][d][0], n, d)
                    self.assertLessEqual(report[3][d][1], adfs.SECTORS)
                module = dump
        finally:
            adfs.CAP = saved
        return bbc, hosts[-1], link, module

    def hello(self, module, host, command):
        """hello compiled, linked and run by the module's *LATHE and *LLINK under ADFS, every file
        what the host compiler and linker of lathe/host in `host` (the changed copy, for
        `command`) give."""
        import bbcfs
        import test_bbc_adfs as adfs
        import test_bbc_toolchain as toolchain
        case = [c for c in toolchain.corpus() if c[0] == 'hello'][0]
        work = os.path.join(self.dir, 'hello-' + command.lower())
        os.makedirs(work)
        saved = toolchain.HOST_COMPILER, toolchain.HOST_LINKER
        if command == 'LATHE':
            toolchain.HOST_COMPILER = os.path.join(host, 'lathec.py')
        else:
            toolchain.HOST_LINKER = os.path.join(host, 'link.py')
        try:
            disk, compiles, link, files, said, load = toolchain.prepare(adfs.adfs_case(case, work),
                                                                        os.path.join(work, 'w'))
        finally:
            toolchain.HOST_COMPILER, toolchain.HOST_LINKER = saved
        self.assertEqual(said, [(0, b'')] * len(said))
        adfs.to_adfs(disk)
        lines = toolchain.bbc_lines(compiles, link, load, len(files[link[2]]))
        status, out, mos, written, cycles, report = adfs.run_adfs(module, disk, lines, ram=True)
        self.assertEqual((status, mos), (0, b''), out)
        with open(os.path.splitext(case[1])[0] + '.expected.out', 'rb') as f:
            self.assertEqual(out, f.read())
        want = {bbcfs.adfs_host_file(bbcfs.adfs_name(f)): data for f, data in files.items()}
        self.assertEqual(sorted(written), sorted(want))
        for f in want:
            self.assertTrue(written[f] == want[f], f + ' differs')
        return files


@unittest.skipUnless(HAVE_TOOLS and CYCLE, 'LATHE_BBC_DEVCYCLE=1 runs it')
class ImageACycle(DevCycle, unittest.TestCase):
    """Image A's tools rebuilt on the B+128 and run from its module: the compiler in two turns,
    the second's compiles by the compiler the first linked (its interfaces version 3); the
    linker in one, then hello linked by it (its map's `$START`)."""
    MODULE = IMAGE_A
    TOOLS = IMAGE_A

    @unittest.skipIf(ONLY and ONLY != 'LATHE', 'LATHE_BBC_DEVCYCLE_TOOL')
    def test_the_compiler_on_its_pair(self):
        import test_bbc_adfs as adfs
        bbc, host, link, module = self.cycle('LATHE', 2, CHANGES['LATHE'], True)
        lis = [f for f, d in adfs.files_of(bbc).items() if f.startswith(':1/li/')]
        self.assertTrue(lis)
        for f in lis:
            self.assertEqual(adfs.files_of(bbc)[f][2], 3, f)
        files = self.hello(module, os.path.join(self.dir, 'lathe', 'host'), 'LATHE')
        self.assertTrue(all(d[2] == 3 for f, d in files.items() if f.endswith('.li')))

    @unittest.skipIf(ONLY and ONLY != 'LLINK', 'LATHE_BBC_DEVCYCLE_TOOL')
    def test_the_linker_on_its_pair(self):
        bbc, host, link, module = self.cycle('LLINK', 1, CHANGES['LLINK'], True)
        files = self.hello(module, os.path.join(self.dir, 'llink', 'host'), 'LLINK')
        maps = [d for f, d in files.items() if f.endswith('.map')]
        self.assertEqual(len(maps), 1)
        self.assertIn(b' $START', maps[0])


MADE_B = {}                         # command: the tool as the B+128 linked it (made_tool)
_made = []


def made_dir():
    """A directory for MADE_B's files that lasts until the tests end."""
    import atexit
    if not _made:
        _made.append(tempfile.mkdtemp(prefix='lathe-devcycle-made-'))
        atexit.register(shutil.rmtree, _made[0], True)
    return _made[0]


def made_tool(command, bbc, host, link, rom_env, out):
    """The tool `command` from the files the BBC's link wrote on the pair `bbc` (drive 1: the
    resident image, the bank files, the map; `host` the host's disc of the same turn, for their
    names), copied with their own names into out: (command, resident, ROM environment, map)."""
    import bbcfs
    os.makedirs(out)
    for name in os.listdir(os.path.join(host, '1')):
        if not name.endswith(('.lo', '.li')):
            with open(bbcfs.adfs_host_path(bbc, '1/' + name), 'rb') as f, open(os.path.join(out, name), 'wb') as g:
                g.write(f.read())
    rom = os.path.join(out, os.path.basename(rom_env))
    shutil.copy(rom_env, rom)
    return (command, os.path.join(out, os.path.basename(link[2])), rom, os.path.join(out, os.path.basename(link[3])))


def list_bank_bytes(image, code_lo, at):
    """The offsets in `image` (a resident part from code_lo) of the bank byte of each region of
    its list of places (at `at`) that is not dynamic (no block): lathe/host/lk_dyn.py's form."""
    i = at - code_lo
    word = (lambda k: image[k] | image[k + 1] << 8)
    i += 4
    i += 1 + 4 * image[i]
    regions, i = image[i], i + 1
    found = []
    for _ in range(regions):
        bank_at, size, room = i, word(i + 3), word(i + 5)
        if size == 0:
            found.append(bank_at)
        i += 7
        planes = 0
        if room:
            planes = image[i + 8]
            i += 9
        for each_planes in (planes, 0):
            n, i = word(i), i + 2
            for _ in range(n):
                i += 3 if image[i] == 0 else 1
                i += 1 if each_planes else 0
    return found


@unittest.skipUnless(HAVE_TOOLS and CYCLE, 'LATHE_BBC_DEVCYCLE=1 runs it')
class ImageBCycle(DevCycle, unittest.TestCase):
    """Image B's tools on the B+128, on the module of the plain image's compiler, Image B's linker
    and the developer's linker (MODULE_B), their sources as they are.

    The compiler: every module compiled by *LATHE (its command lines without the defines no
    source names: on_the_command_line) and linked by *DEVLINK, every file the host tools' of the
    whole commands. Its banks are the module's compiler's and it starts elsewhere ($2B26), so
    MODLOAD refuses it there (a new HOME is needed): it runs on the Model B (ImageBFromTheBBC).

    The linker: *DEVLINK links it, every file the host linker's but two bytes of its resident part,
    the bank bytes in its list of places of its two regions that are not dynamic (LKNODES and
    LKWORK, `fixed`, in no bank), where the host linker writes 0 and the developer's $FF: both
    tools write `bank_value[region_bank[r] - 1]` (lk_dyn.put_region), with region_bank 0 for a
    region in no bank, so the host's Python reads the list's last entry (0) and the twin the byte
    after its array. A fault of lk_dyn, host and twin (lathe/docs/bbc.md, "For the images that
    ship"); mended there, a measured copy links it to the host's bytes, but that changes Wendy 2's
    banked linkers (LKDYN 1), so it waits for the owner. So Image B's linker as the host linked
    it, which the module holds, runs on the B+128: hello compiled by the plain *LATHE, linked by
    Image B's *LLINK (its tables in main RAM, an ADFS machine's: PAGE $1F00) and run."""
    MODULE = MODULE_B
    TOOLS = IMAGE_B

    def keep(self, command, bbc, host, link):
        MADE_B[command] = made_tool(command, bbc, host, link, self.image_tools[command][2],
                                    os.path.join(made_dir(), command.lower()))

    @unittest.skipIf(ONLY and ONLY != 'LATHE', 'LATHE_BBC_DEVCYCLE_TOOL')
    def test_the_compiler_on_its_pair(self):
        import boards
        import test_bbc_adfs as adfs
        bbc, host, link, module = self.cycle('LATHE', 1, [], False)
        self.keep('LATHE', bbc, host, link)
        load = [os.path.basename(self.image_tools['LATHE'][2]), link[3], link[2]]
        status, out, mos, written, cycles, report = adfs.run_adfs(
            module, bbc, [boards.module_command('RUN', ['MODLOAD'] + load)], ram=True)
        self.assertEqual(status, 2)
        self.assertIn(b'a new HOME is needed', out)

    @unittest.skipIf(ONLY and ONLY != 'LLINK', 'LATHE_BBC_DEVCYCLE_TOOL')
    def test_the_linker_on_its_pair(self):
        """*DEVLINK links Image B's linker from the objects *LATHE compiled: every file the host's
        but the two bytes above."""
        import bbcfs
        import mapenv
        import places
        import test_bbc_adfs as adfs
        with self.assertRaises(AssertionError) as caught:
            self.cycle('LLINK', 1, [], False)
        self.assertIn(':1/LINK differs', str(caught.exception))
        work = os.path.join(self.dir, 'llink')
        with open(os.path.join(work, 'host0', '1', 'LINK'), 'rb') as f:
            host = f.read()
        with open(bbcfs.adfs_host_path(os.path.join(work, 'bbc'), '1/LINK'), 'rb') as f:
            got = f.read()
        self.assertEqual(len(got), len(host))
        code_lo = mapenv.read_env(self.image_tools['LLINK'][2]).code[0]
        with open(os.path.join(work, 'host0', '1', 'LINK.map')) as f:
            place = next(int(line.split()[1], 16) for line in f
                         if line.startswith('F ') and line.split()[3] == 'rt_place.place')
        _, at = places.find(host, code_lo, place)
        fixed = list_bank_bytes(host, code_lo, at)
        self.assertEqual(len(fixed), 2)
        self.assertEqual([i for i in range(len(host)) if host[i] != got[i]], fixed)
        self.assertEqual([(host[i], got[i]) for i in fixed], [(0, 0xFF)] * 2)
        command, resident, rom, map_path = self.image_tools['LLINK']
        kept = os.path.join(made_dir(), 'llink')
        shutil.copytree(os.path.dirname(resident), kept)
        MADE_B['LLINK'] = (command, os.path.join(kept, os.path.basename(resident)),
                           os.path.join(kept, os.path.basename(rom)),
                           os.path.join(kept, os.path.relpath(map_path, os.path.dirname(resident))))
        self.hello(self.whole, os.path.join(work, 'host'), 'LLINK')


import test_bbc_image_b  # noqa: E402


def from_the_bbc(cls):
    """cls's tools, image and listing: Image B's 128 KB image of the compiler's files as the B+128
    linked them and the linker's as the host did (ImageBCycle, run here if it has not run), in a
    directory of cls's own."""
    for command, test in (('LATHE', 'test_the_compiler_on_its_pair'), ('LLINK', 'test_the_linker_on_its_pair')):
        if command not in MADE_B:
            ImageBCycle.setUpClass()
            try:
                ImageBCycle(test).debug()
            finally:
                ImageBCycle.tearDownClass()
    cls.dir = tempfile.mkdtemp(prefix='lathe-image-b-from-the-bbc-')
    cls.tools = [MADE_B['LATHE'], MADE_B['LLINK']]
    cls.image = os.path.join(cls.dir, 'MODULE')
    listing = os.path.join(cls.dir, 'listing')
    bbcrom.image(cls.tools, cls.image, listing, banks=8)
    with open(listing) as f:
        cls.listing = f.read()


@unittest.skipUnless(HAVE_TOOLS and CYCLE and not ONLY, 'LATHE_BBC_DEVCYCLE=1 runs it')
class ImageBFromTheBBC(test_bbc_image_b.ImageB):
    """test_bbc_image_b's runs on a Model B with no sideways RAM (at PAGE $1900 and $1F00), from
    the 128 KB image bbcrom.py makes of Image B's compiler as the B+128 linked it (from_the_bbc):
    the same bytes as the host's Image B."""

    @classmethod
    def setUpClass(cls):
        from_the_bbc(cls)

    def test_it_is_the_hosts_image_b(self):
        host_tools, host_image, _ = test_bbc_image_b.build_image(os.path.join(self.dir, 'host'))
        with open(host_image, 'rb') as f, open(self.image, 'rb') as g:
            self.assertTrue(f.read() == g.read())


@unittest.skipUnless(HAVE_TOOLS and CYCLE and not ONLY and test_bbc_image_b.PROGRAMS,
                     'LATHE_BBC_DEVCYCLE=1 with LATHE_BBC_IMAGE_B_PROGRAMS=1 runs it')
class ImageBProgramsFromTheBBC(test_bbc_image_b.LargestPrograms):
    """test_bbc_image_b's largest programs, compiled, linked and run on the Model B by the image of
    from_the_bbc."""

    @classmethod
    def setUpClass(cls):
        from_the_bbc(cls)


if __name__ == '__main__':
    unittest.main()
