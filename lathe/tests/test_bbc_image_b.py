"""Image B, the 128 KB image for machines with no sideways RAM (lathe/docs/bbc.md, "The image for
machines with no sideways RAM"): the linker's form `define RAM32 1` with `define ADAPT 1`, linked
from $1F00 with the 32K build's capacities (LKSMALL 2) but for its symbols of the object files,
its slots and its calls, which are dynamic regions of planes (LKROOMS 1) that the module's placer
puts in main RAM alone as the tool starts (`main_only`: FIXED_REGIONS with dynamic regions; no slot
is probed or used), each block on a page (`top WIN N $BEFF`), the slots and calls `dynamic main`
(told fixed: their accessors map nothing); `link` in the linker's second bank; BBCFS 3, the names
of the filing system the MOS names. The compiler's form is `define RAM32 1` with `define ADAPT 1`
too: every table in main RAM at capacities of its own (script_host.IMAGE_B), its name heap lowest,
from $1900 (`region NAMES fixed $1900`), and begun at PAGE as it starts (OSBYTE 131), so that a DFS
machine has 4,646 bytes of it and ADFS's 3,110; the module refuses *LATHE at a PAGE above $1F00
(`define HIGHEST_PAGE $1F00`). Its oracle is the host compiler at those capacities with the heap
begun at that machine's offset (lathec_image_b.py).

What is tested here, by default:

- the image fits the 128 KB module, the linker's list has no sideways RAM to probe (main_only);
- what the linker gets on each machine, by the model of the placer (places.plan): a Model B with
  the DFS (PAGE $1900), with ADFS and the DFS (PAGE $1F00), and a B+ in a shadow mode at each;
  on the DFS machine every table at least the 32K build's;
- on a Model B with no sideways RAM at PAGE $1900 and at $1F00: *LLINK links a program of the
  end-to-end cases from the host compiler's objects, every file the host linker's at that
  machine's capacities; a generated program that needs more calls than ADFS's machine gives
  (7 modules of 23 functions: 542) is linked at $1900 and refused at $1F00, each as the host
  linker at those capacities does it (so the real placer gives what the model says); PAGE above
  $1F00 is refused, and a screen mode below the tool's memory;
- *LATHE at PAGE $1900 and $1F00 compiles a small module and the one of the census whose names need
  the most (lk_name), every file the oracle's at that page, the same files at both pages and at
  full size; the most variables of 31 characters each machine takes (MOST_NAMES) and one more,
  refused as the oracle refuses it; *LATHE refused above $1F00 and outside mode 7, and its start.

LATHE_BBC_IMAGE_B_PROGRAMS=1: the largest generated program each machine takes, under the
emulator's DFS at PAGE $1900 (the 25 KB program, 8 modules of 26 functions: every module compiled
by *LATHE, linked by *LLINK @LINKARG, *SAVEd and run, as test_gen_program's 32K test does it) and
under its ADFS at $1F00 (7 modules of 22 functions, every module compiled by *LATHE there too,
linked by *LLINK and run); every file the host tools' under that filing system's names (BBCFS 3),
and the host tools at that machine's capacities give the same.

LATHE_BBC_IMAGE_B_ALL=1 (Assessment, a few minutes): every module of lathe/src and lathe/rt compiled
by *LATHE at PAGE $1900 and $1F00, each the oracle's files or error, the same files at both pages.

LATHE_BBC_IMAGE_B_REPORT=1 prints the capacities, the account and the cycles.
"""
import dataclasses
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import src_support as support  # noqa: E402
import bbcrom  # noqa: E402
import boards  # noqa: E402
import build  # noqa: E402

REPORT = os.environ.get('LATHE_BBC_IMAGE_B_REPORT') == '1'
PROGRAMS = os.environ.get('LATHE_BBC_IMAGE_B_PROGRAMS') == '1'
import test_bbc_rom as tbr  # noqa: E402
HAVE_TOOLS = tbr.HAVE_TOOLS
COMPILER_SETTINGS = {'RAM32': 1, 'ADAPT': 1, 'BBCFS': 3}
LINKER_SETTINGS = {'RAM32': 1, 'ADAPT': 1, 'ADFS': 1, 'BBCFS': 3}
ROOMS_LINKER = os.path.join(HERE, 'lk_rooms.py')
COMPILER_ORACLE = os.path.join(HERE, 'lathec_image_b.py')
LINKER_REGIONS = {'lklocal': 'locals', 'lkslots': 'slots', 'lkcalls': 'calls'}

# (name, PAGE, HIMEM, the emulator's options): a Model B has no shadow screen; the B+ in a shadow
# mode is the model's alone here (the emulator's --bbc-shadow is the B+'s).
MACHINES = (
    ('Model B, DFS', 0x1900, 0x7C00),
    ('Model B, ADFS and DFS', 0x1F00, 0x7C00),
    ('B+, DFS, shadow mode', 0x1900, 0x8000),
    ('B+, ADFS and DFS, shadow mode', 0x1F00, 0x8000),
)
# What the linker gets there, by the model of the placer over the list (rows).
LINKER_GETS = {
    'Model B, DFS': {'locals': 768, 'slots': 1024, 'calls': 768},
    'Model B, ADFS and DFS': {'locals': 512, 'slots': 768, 'calls': 512},
    'B+, DFS, shadow mode': {'locals': 768, 'slots': 1024, 'calls': 768},
    'B+, ADFS and DFS, shadow mode': {'locals': 512, 'slots': 1024, 'calls': 768},
}
# The 32K build's (LKSMALL 2): on a DFS machine Image B's linker has at least each of them.
LINKER_32K = {'locals': 640, 'slots': 848, 'calls': 768}
# The generated programs (modules, functions a module): one that needs 542 calls, more than ADFS's
# machine gives; the largest each machine links and holds (PAGE, the emulator's filing system).
MORE_THAN_ADFS = (7, 23)
LARGEST = (('1900', 'dfs', 8, 26), ('1F00', 'adfs', 7, 22))
# The compiler's name heap on each machine: from $1900, begun at PAGE (lathec_image_b.py), so a DFS
# machine has kernel.NAME_HEAP_SIZE (4,470 bytes) and ADFS's 1,536 less. The most variables of 31
# characters a module (test_bbc_rooms.big_names_source) has that each compiles: one more is error 70.
COMPILER_HEAP = {0x1900: 4646, 0x1F00: 3110}
MOST_NAMES = {0x1900: 106, 0x1F00: 64}
# Modules of lathe/src compiled at each page in the default tests: a small one, and the one of the
# census whose names need the most (3,110 bytes from offset 1: all of ADFS's heap).
COMPILER_MODULES = ('typetab', 'lk_name')
ASSESS = os.environ.get('LATHE_BBC_IMAGE_B_ALL') == '1'


def build_image(out_dir):
    """Image B in out_dir/MODULE: [(command, resident, ROM environment, map)], the image, the listing."""
    tools, first = [], 0
    for command, source, env, settings in (('LATHE', 'lathec.lth', 'lathec-bbc.env', COMPILER_SETTINGS),
                                           ('LLINK', 'link.lth', 'linker-bbc.env', LINKER_SETTINGS)):
        d = os.path.join(out_dir, command.lower())
        os.makedirs(d)
        rom = os.path.join(d, env)
        first = bbcrom.rom_env(os.path.join(support.SRC, env), rom, first, 8, settings=settings)
        resident = os.path.join(d, command)
        build.build(os.path.join(support.SRC, source), resident, env=rom, keep=os.path.join(d, 'work'))
        tools.append((command, resident, rom, os.path.join(d, 'work', os.path.splitext(source)[0] + '.map')))
    image = os.path.join(out_dir, 'MODULE')
    listing = os.path.join(out_dir, 'listing')
    bbcrom.image(tools, image, listing, short=image + '.disc', banks=8)
    with open(listing) as f:
        return tools, image, f.read()


def linker_capacities(tool, page, himem):
    """{table: rows} of Image B's linker at PAGE and HIMEM, by the model of the placer; None if refused."""
    import places
    p, names = places.of_tool(*tool[1:4])
    done = places.plan(p, page, himem, [])
    if done is None:
        return None
    return {LINKER_REGIONS[names[i]]: d.room for i, d in done.items() if p.regions[i].room}


def host_compile_at(d, args, page):
    """Image B's compiler's oracle (lathec_image_b.py) at PAGE `page` in a copy of d, or with `page`
    None the host compiler at full size: (status, output and error output, {file: bytes} it wrote)."""
    where = d + ('-host-%04X' % page if page else '-host-full')
    shutil.rmtree(where, ignore_errors=True)
    shutil.copytree(d, where)
    before = set(os.listdir(where))
    tool = [COMPILER_ORACLE] if page else [build.COMPILER]
    r = subprocess.run([sys.executable] + tool + list(args), cwd=where, capture_output=True,
                       env=dict(os.environ, LATHE_PAGE='%04X' % (page or 0x1900)))
    files = {}
    for f in sorted(os.listdir(where)):
        if f not in before:
            with open(os.path.join(where, f), 'rb') as handle:
                files[f] = handle.read()
    return r.returncode, r.stdout + r.stderr, files


def bbc_compile_at(image, d, args, page, mode=7):
    """*LATHE ARGS on a Model B with no sideways RAM at PAGE `page` (names as given) in a copy of
    d: (status, output, what the MOS said, {file: bytes} written, cycles)."""
    import test_bbc_rom128 as rom128
    where = d + '-bbc-%04X' % page
    shutil.rmtree(where, ignore_errors=True)
    shutil.copytree(d, where)
    before = {}
    for f in os.listdir(where):
        with open(os.path.join(where, f), 'rb') as handle:
            before[f] = handle.read()
    with rom128.scheme():
        code, out, err, cycles = boards.run_module(board('%04X' % page, mode), image, where, 'LATHE',
                                                   tail=' '.join(args), raw=True, cap=4_000_000_000)
    status, said, cycles = boards.bbc_status(code, err.decode('latin-1'))
    written = {}
    for f in sorted(os.listdir(where)):
        with open(os.path.join(where, f), 'rb') as handle:
            data = handle.read()
        if before.get(f) != data:
            written[f] = data
    return status, boards.bbc_output(out), said, written, cycles


def module_dir(work, name):
    """A directory with lathe/src/NAME.lth (or lathe/rt's) and the host's interfaces of what it
    imports, and its arguments to the compiler (test_bbc_ram32.prepare_li)."""
    import memory_report
    import test_bbc_ram32 as ram32
    path = os.path.join(support.SRC, name + '.lth')
    if not os.path.exists(path):
        path = os.path.join(support.LATHE, 'rt', name + '.lth')
    options = tuple(memory_report.options_of(path, None))
    d = ram32.prepare_li(path, options, work)
    return d, list(options) + [name + '.lth', '.']


def names_dir(work, count):
    """A directory with a module of `count` variables of 31 characters (test_bbc_rooms.bignames)."""
    import test_bbc_rooms as rooms
    d = os.path.join(work, 'bignames-%d' % count)
    os.makedirs(d)
    with open(os.path.join(d, 'bignames.lth'), 'w') as f:
        f.write(rooms.big_names_source(count))
    return d, ['bignames.lth', '.']


def host_link_at(link, disk, caps):
    """The host linker in disk (a copy of the BBC's) at the 32K build's capacities with `caps`
    {table: rows} (lk_rooms.py): (status, output, {file: bytes} it wrote)."""
    import lk_rooms
    before = set(os.listdir(disk))
    r = subprocess.run([sys.executable, ROOMS_LINKER] + link, cwd=disk, capture_output=True,
                       env=dict(os.environ, LATHE_LK_CAPACITIES=lk_rooms.setting(caps), LATHE_LK_SMALL='2'))
    files = {}
    for f in os.listdir(disk):
        if f not in before:
            with open(os.path.join(disk, f), 'rb') as handle:
                files[f] = handle.read()
    return r.returncode, r.stdout + r.stderr, files


def board(page, mode=7):
    """A Model B with no sideways RAM at PAGE `page` (hex) in screen mode `mode`, the names as given
    (a filing system that is neither the DFS nor ADFS: BBCFS 3 maps nothing)."""
    base = boards.BOARDS['bbc']
    return dataclasses.replace(base, options=base.options + ('--bbc-model', 'b', '--bbc-page', page,
                                                             '--bbc-mode', str(mode), '--bbc-fs-number', '5'))


def generated(work, modules, functions, page):
    """A generated program (test_gen_program) built for PAGE `page` (hex): (main, environment,
    the expected output, the program)."""
    import gen_program
    import lk_ram32
    import test_gen_program as tgp
    p = gen_program.Program(modules, functions, 2.0, 1, None)
    main = p.write(os.path.join(work, 'src'))
    measured = os.path.join(work, 'measure')
    with tgp.rt_first():
        build.build(main, os.path.join(work, 'measure.bin'), env=tgp.measure_env(os.path.join(work, 'measure.env')),
                    keep=measured)
    size = lk_ram32.link_size(os.path.join(measured, 'genmain.map'))
    env = tgp.page_env(os.path.join(work, 'genmain.env'), size, int(page, 16))
    with open(os.path.join(work, 'src', 'genmain.expected.out'), 'rb') as f:
        return main, env, f.read(), p


def host_objects(work, main, env, objects=True):
    """The BBC's disc for a generated program with the host compiler's objects and interfaces on
    it (with `objects`; else its sources alone) and LINKARG: (disc, the compiles' arguments, the
    link's, {file: bytes} the host tools wrote)."""
    import test_bbc_selflink as selflink
    import test_bbc_toolchain as chain
    import test_gen_program as tgp
    steps = tgp.recorded(main, env, os.path.join(work, 'steps'))
    disk = os.path.join(work, 'bbc')
    os.makedirs(disk)
    compiles, link = chain.lay_out(steps, disk)
    host = os.path.join(work, 'host')
    shutil.copytree(disk, host)
    files, said = chain.host_files(compiles, link, host)
    assert said == [(0, b'')] * len(said), said
    for f in files:
        if objects and f.endswith(('.lo', '.li')):
            shutil.copy(os.path.join(host, f), disk)
    with open(os.path.join(disk, selflink.COMMAND_FILE), 'w') as f:
        f.write(' '.join(link) + '\r\n')
    return disk, compiles, link, files


def fs_board(page, fs):
    """A Model B with no sideways RAM at PAGE `page` (hex) under the emulator's DFS or ADFS
    (--bbc-fs), strict, in mode 7: BBCFS 3 gives the names of the one the MOS names."""
    base = boards.BOARDS['bbc']
    return dataclasses.replace(base, options=base.options + ('--bbc-model', 'b', '--bbc-page', page, '--bbc-mode',
                                                             '7', '--bbc-fs', fs, '--bbc-strict'))


def fs_run(image, disk, lines, page, fs):
    """The * commands on fs_board: (status, output, what the MOS said, cycles)."""
    import bbcrom
    command, _, tail = lines[-1].partition(' ')
    code, out, err, cycles = boards.run_module(fs_board(page, fs), image, disk, command, tail=tail,
                                               before=lines[:-1], raw=True, cap=4_000_000_000,
                                               scheme=bbcrom.SCHEMES[8])
    status, said, cycles = boards.bbc_status(code, err.decode('latin-1'))
    return status, boards.bbc_output(out), said, cycles


def bbc_link(image, disk, page):
    """*LLINK @LINKARG on disk on the Model B at PAGE `page`: (status, output, the MOS's, written, cycles)."""
    import test_bbc_rom128 as rom128
    import test_bbc_selflink as selflink
    import test_bbc_toolchain as chain
    saved = chain.BOARD
    chain.BOARD = board(page)
    try:
        with rom128.scheme():
            lines = [boards.module_command('LLINK', ['@' + selflink.COMMAND_FILE])]
            status, out, mos, written, cycles, traffic = chain.bbc_run(image, disk, lines)
    finally:
        chain.BOARD = saved
    return status, out, mos, written, cycles


@unittest.skipUnless(HAVE_TOOLS, 'emulator missing')
class ImageB(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-bbc-image-b-')
        cls.tools, cls.image, cls.listing = build_image(cls.dir)
        if REPORT:
            print('\nImage B:', [line for line in cls.listing.splitlines() if line.startswith('free')])
            for name, page, himem in MACHINES:
                print('%s: the linker gets %r' % (name, linker_capacities(cls.tools[1], page, himem)))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_the_image_has_the_placer_for_main_ram_alone(self):
        import mapenv
        env = mapenv.read_env(self.tools[1][2])
        self.assertEqual(sorted(env.dynamic_regions), ['lkcalls', 'lklocal', 'lkslots'])
        with open(self.image, 'rb') as f:
            text = f.read().decode('latin-1')
        self.assertNotIn('Too little sideways RAM', text)
        self.assertIn('Too little memory', text)

    def test_a_region_in_main_ram_alone_needs_the_placer_for_main_ram(self):
        """bbcrom refuses a program with a `dynamic main` region whose placer would probe sideways
        RAM: its accessors of the region map nothing."""
        with open(self.tools[1][2]) as f:
            text = f.read()
        told_not = os.path.join(self.dir, 'not-told.env')
        with open(told_not, 'w') as f:
            f.write(text + 'define    FIXED_REGIONS 0\n')
        tools = [self.tools[0], self.tools[1][:2] + (told_not,) + self.tools[1][3:]]
        with self.assertRaisesRegex(bbcrom.ImageError, 'dynamic main'):
            bbcrom.image(tools, os.path.join(self.dir, 'NOT'), os.path.join(self.dir, 'not.listing'), banks=8)

    def test_what_the_linker_gets_on_each_machine(self):
        for name, page, himem in MACHINES:
            with self.subTest(machine=name):
                self.assertEqual(linker_capacities(self.tools[1], page, himem), LINKER_GETS[name])
        dfs = LINKER_GETS['Model B, DFS']
        self.assertEqual({t: dfs[t] for t in LINKER_32K if dfs[t] < LINKER_32K[t]}, {})

    def prepared(self, case, page):
        """A program of the end-to-end cases, its objects the host compiler's, ready to link on disk."""
        import test_bbc_selflink as selflink
        import test_bbc_toolchain as chain
        disk, compiles, link, files, said, load = chain.prepare(case, os.path.join(self.dir, case[0] + '-' + page))
        for f in files:
            if f.endswith('.lo'):
                shutil.copy(os.path.join(os.path.dirname(disk), 'host', f), disk)
        with open(os.path.join(disk, selflink.COMMAND_FILE), 'w') as f:
            f.write(' '.join(link) + '\r\n')
        return disk, link, files

    def test_the_linker_links_a_program_at_each_page(self):
        import test_bbc_selflink as selflink
        import test_bbc_toolchain as chain
        case = [c for c in chain.corpus() if c[0] == 'calls'][0]
        for name, page, himem in MACHINES[:2]:
            with self.subTest(machine=name):
                disk, link, files = self.prepared(case, '%04X' % page)
                at_caps = disk + '-host'
                shutil.copytree(disk, at_caps)
                status, host_said, host_files = host_link_at(link, at_caps, LINKER_GETS[name])
                self.assertEqual((status, host_said), (0, b''))
                expected = selflink.link_outputs(files)
                self.assertEqual(host_files, expected)
                status, out, mos, written, cycles = bbc_link(self.image, disk, '%04X' % page)
                self.assertEqual((status, out, mos), (0, b'', b''))
                self.assertEqual(sorted(written), sorted(expected))
                for f in expected:
                    self.assertTrue(written[f] == expected[f], f + ' differs')
                if REPORT:
                    print('\n%s: calls linked in %d cycles' % (name, cycles))

    def test_a_program_that_needs_more_than_adfs_gives_links_with_the_dfs_alone(self):
        """The machines' capacities told apart by the real placer: a generated program that needs
        542 calls links at PAGE $1900 (768) and not at $1F00 (512), each time as the host linker
        at that machine's capacities does it, the files or the error."""
        work = os.path.join(self.dir, 'more-calls')
        main, env, expected, p = generated(work, *MORE_THAN_ADFS, page='1F00')
        for name, page, himem in MACHINES[:2]:
            with self.subTest(machine=name):
                disk, compiles, link, files = host_objects(os.path.join(work, '%04X' % page), main, env)
                at_caps = disk + '-host'
                shutil.copytree(disk, at_caps)
                host_status, host_said, host_files = host_link_at(link, at_caps, LINKER_GETS[name])
                status, out, mos, written, cycles = bbc_link(self.image, disk, '%04X' % page)
                if page == 0x1900:
                    self.assertEqual((host_status, host_said), (0, b''))
                    self.assertEqual((status, out, mos), (0, b'', b''))
                    self.assertEqual(sorted(written), sorted(host_files))
                    for f in host_files:
                        self.assertTrue(written[f] == host_files[f], f + ' differs')
                    self.assertEqual(host_files[link[2]], files[link[2]])   # as at full capacities
                else:
                    self.assertEqual(host_status, 1)
                    self.assertIn(b'calls', host_said)
                    self.assertEqual((status, out + mos), (1, host_said))

    def test_a_tool_is_refused_where_it_cannot_run(self):
        import test_bbc_rom128 as rom128
        for page, mode, said in (('2100', 7, b'PAGE too high'), ('1900', 4, b'Mode 7 needed')):
            with self.subTest(page=page, mode=mode), rom128.scheme(), tempfile.TemporaryDirectory() as d:
                code, out, err, cycles = boards.run_module(board(page, mode), self.image, d, 'LLINK', raw=True)
                self.assertIn(said, out + err)

    def test_the_compiler_compiles_at_each_page_as_the_host_does(self):
        """*LATHE at PAGE $1900 and $1F00 gives every file the host compiler gives at Image B's
        capacities with the heap begun where that machine begins it (lathec_image_b.py), and the
        same files at both pages, which are the host compiler's at full size."""
        for name in COMPILER_MODULES:
            d, args = module_dir(os.path.join(self.dir, 'modules'), name)
            full = host_compile_at(d, args, None)
            self.assertEqual(full[:2], (0, b''))
            at = {}
            for page in (0x1900, 0x1F00):
                with self.subTest(module=name, page='%04X' % page):
                    host = host_compile_at(d, args, page)
                    self.assertEqual(host[:2], (0, b''))
                    status, out, mos, written, cycles = bbc_compile_at(self.image, d, args, page)
                    self.assertEqual((status, out, mos), (0, b'', b''))
                    self.assertEqual(sorted(written), sorted(host[2]))
                    for f in host[2]:
                        self.assertTrue(written[f] == host[2][f], f + ' differs')
                    at[page] = written
                    if REPORT:
                        print('\n%s at PAGE $%04X: compiled in %d cycles' % (name, page, cycles))
            self.assertEqual(at[0x1900], at[0x1F00])
            self.assertEqual(at[0x1900], full[2])

    def test_the_most_names_each_machine_compiles(self):
        """A module of MOST_NAMES[page] variables of 31 characters compiles at that PAGE, every file
        the host's, and one more variable is error 70 there, as the host compiler says: the DFS
        machine's heap is 1,536 bytes larger than ADFS's."""
        for page in (0x1900, 0x1F00):
            for count in (MOST_NAMES[page], MOST_NAMES[page] + 1):
                with self.subTest(page='%04X' % page, count=count):
                    d, args = names_dir(os.path.join(self.dir, 'names-%04X' % page), count)
                    host = host_compile_at(d, args, page)
                    status, out, mos, written, cycles = bbc_compile_at(self.image, d, args, page)
                    self.assertEqual((status, out + mos), (host[0], host[1]))
                    if count == MOST_NAMES[page]:
                        self.assertEqual(host[:2], (0, b''))
                        self.assertEqual(written, host[2])
                    else:
                        self.assertEqual(host[0], 1)
                        self.assertIn(b'error 70: too many names', host[1])
        self.assertEqual(COMPILER_HEAP[0x1900] - COMPILER_HEAP[0x1F00], 0x1F00 - 0x1900)

    def test_the_compiler_is_refused_where_it_cannot_run(self):
        import test_bbc_rom128 as rom128
        for page, mode, said in (('2000', 7, b'PAGE too high'), ('1F00', 4, b'Mode 7 needed'),
                                 ('1900', 4, b'Mode 7 needed')):
            with self.subTest(page=page, mode=mode), rom128.scheme(), tempfile.TemporaryDirectory() as d:
                code, out, err, cycles = boards.run_module(board(page, mode), self.image, d, 'LATHE', raw=True)
                self.assertIn(said, out + err)

    def test_the_compiler_starts_at_each_page(self):
        import test_bbc_rom128 as rom128
        for page in ('1900', '1F00'):
            with self.subTest(page=page), rom128.scheme(), tempfile.TemporaryDirectory() as d:
                code, out, err, cycles = boards.run_module(board(page), self.image, d, 'LATHE', raw=True)
                self.assertIn(b'usage: lathec', out)
                if REPORT:
                    print('\nImage B at PAGE $%s: *LATHE starts in %d cycles' % (page, cycles))

    def test_the_linker_starts_at_each_page(self):
        import test_bbc_rom128 as rom128
        for page in ('1900', '1F00'):
            with self.subTest(page=page), rom128.scheme(), tempfile.TemporaryDirectory() as d:
                code, out, err, cycles = boards.run_module(board(page), self.image, d, 'LLINK', raw=True)
                self.assertIn(b'usage: link', out)
                if REPORT:
                    print('\nImage B at PAGE $%s: *LLINK starts in %d cycles' % (page, cycles))


@unittest.skipUnless(HAVE_TOOLS and PROGRAMS, 'LATHE_BBC_IMAGE_B_PROGRAMS=1 builds and runs the largest programs')
class LargestPrograms(unittest.TestCase):
    """The largest generated program each machine takes (LARGEST), under the emulator's DFS at
    PAGE $1900 and its ADFS at $1F00, Image B's names (BBCFS 3) for each."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-bbc-image-b-programs-')
        cls.tools, cls.image, cls.listing = build_image(os.path.join(cls.dir, 'image'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_the_dfs_machine_compiles_links_and_runs_the_25_kb_program(self):
        """As test_gen_program.model_b on the 32K Model B (the DFS, PAGE $1900): every module by
        *LATHE, the objects on drive 1, *LLINK @LINKARG, the image *SAVEd and run, every file the
        host tools'; and the host linker at the DFS machine's capacities links it so too."""
        import test_gen_program as tgp
        page, fs, modules, functions = LARGEST[0]
        work = os.path.join(self.dir, fs)
        main, env, expected, p = generated(work, modules, functions, page)
        self.assertIsNotNone(env)
        result = tgp.model_b(self, self.image, work, main, env, expected)
        link = result['link']
        disk, compiles, link_here, files = host_objects(os.path.join(work, 'at-caps'), main, env)
        status, said, files_at = host_link_at(link_here, disk, LINKER_GETS['Model B, DFS'])
        self.assertEqual((status, said), (0, b''))
        self.assertEqual(files_at[link_here[2]], files[link_here[2]])
        if REPORT:
            print('\nImage B, DFS: %d modules of %d functions, %d lines, the image %d bytes; %d compiles %.1f '
                  'million cycles, the link %.1f million, the run %.1f million' % (
                      modules, functions, p.lines(), result['image'], result['compiles'],
                      result['cycles compiles'] / 1e6, result['cycles link'] / 1e6, result['cycles run'] / 1e6))

    def test_the_adfs_machine_compiles_links_and_runs_its_largest_program(self):
        """Under the emulator's ADFS at PAGE $1F00 every module compiled by *LATHE (its name heap
        begun at PAGE), linked by *LLINK @LINKARG, *SAVEd and run: every file the host tools' under
        ADFS's names, and the host linker at the ADFS machine's capacities links it so too."""
        import bbcfs
        import test_bbc_adfs
        import test_bbc_dfs
        import test_bbc_selflink as selflink
        import test_bbc_toolchain as chain
        page, fs, modules, functions = LARGEST[1]
        work = os.path.join(self.dir, fs)
        main, env, expected, p = generated(work, modules, functions, page)
        self.assertIsNotNone(env)
        disk, compiles, link, files = host_objects(work, main, env)
        at_caps = disk + '-host'
        shutil.copytree(disk, at_caps)
        status, said, files_at = host_link_at(link, at_caps, LINKER_GETS['Model B, ADFS and DFS'])
        self.assertEqual((status, said), (0, b''))
        self.assertEqual(files_at[link[2]], files[link[2]])         # as at full capacities
        disk, compiles, link, files = host_objects(work + '-sources', main, env, objects=False)
        oracle = disk + '-oracle'                                   # the compiler at ADFS's capacities
        shutil.copytree(disk, oracle)
        for args in compiles:
            r = subprocess.run([sys.executable, COMPILER_ORACLE] + args, cwd=oracle, capture_output=True,
                               env=dict(os.environ, LATHE_PAGE=page))
            self.assertEqual((r.returncode, r.stdout + r.stderr), (0, b''), args)
        for f, data in files.items():
            if f.endswith(('.lo', '.li')):
                with open(os.path.join(oracle, f), 'rb') as handle:
                    self.assertTrue(handle.read() == data, f + ' differs')
        test_bbc_adfs.to_adfs(disk)
        before = test_bbc_dfs.files_of(disk)
        lines = chain.bbc_lines(compiles, link, int(page, 16), len(files[link[2]]))
        lines[len(compiles)] = boards.module_command('LLINK', ['@' + selflink.COMMAND_FILE])
        status, out, mos, cycles = fs_run(self.image, disk, lines[:len(compiles)], page, fs)
        self.assertEqual((status, out, mos), (0, b'', b''))
        status, out, mos, cycles_link = fs_run(self.image, disk, lines[len(compiles):], page, fs)
        self.assertEqual((status, mos), (0, b''))
        self.assertEqual(out, expected)
        written = {f: d for f, d in test_bbc_dfs.files_of(disk).items() if before.get(f) != d}
        want = {bbcfs.asked_host_file(f, 8): data for f, data in files.items()}
        self.assertEqual(sorted(written), sorted(want))
        for f in want:
            self.assertTrue(written[f] == want[f], f + ' differs')
        if REPORT:
            print('\nImage B, ADFS: %d modules of %d functions, %d lines, the image %d bytes; %d compiles %.1f '
                  'million cycles, the link and the run %.1f million' % (
                      modules, functions, p.lines(), len(files[link[2]]), len(compiles), cycles / 1e6,
                      cycles_link / 1e6))


@unittest.skipUnless(HAVE_TOOLS and ASSESS, 'LATHE_BBC_IMAGE_B_ALL=1 compiles every module at both pages')
class Assessment(unittest.TestCase):
    """Every module of lathe/src and lathe/rt compiled by *LATHE on a Model B with no sideways RAM at
    PAGE $1900 and at $1F00: each gives the files or the error the host compiler gives at Image B's
    capacities with the heap begun there (lathec_image_b.py), as test_bbc_ram32.Assessment does for
    the 32K form; and each module compiled at both pages gives the same files at both."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-bbc-image-b-all-')
        cls.tools, cls.image, cls.listing = build_image(os.path.join(cls.dir, 'image'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_each_module_compiles_at_each_page_as_the_host_does(self):
        import re
        import test_bbc_ram32 as ram32
        rows = []
        for path, options in ram32.assessed():
            name = build.module_name(path)
            d = ram32.prepare_li(path, options, os.path.join(self.dir, 'work'))
            args = list(options) + [name + '.lth', '.']
            at = {}
            for page in (0x1900, 0x1F00):
                host = host_compile_at(d, args, page)
                status, out, mos, written, cycles = bbc_compile_at(self.image, d, args, page)
                with self.subTest(module=os.path.relpath(path, support.LATHE), page='%04X' % page):
                    self.assertEqual((status, mos), (host[0], b''))
                    if host[0] == 0:
                        self.assertEqual(sorted(written), sorted(host[2]))
                        for f in host[2]:
                            self.assertTrue(written[f] == host[2][f], f + ' differs')
                        at[page] = written
                    else:
                        self.assertEqual(re.findall(rb'error \d+', out), re.findall(rb'error \d+', host[1]))
                rows.append((os.path.relpath(path, support.LATHE), page, host[0], cycles,
                             (re.findall(rb'error \d+', host[1]) or [b''])[0].decode()))
            if len(at) == 2:
                self.assertEqual(at[0x1900], at[0x1F00], name)
        if REPORT:
            print('\nImage B on the Model B, each module of lathe/src and lathe/rt:')
            for p, page, st, cycles, e in rows:
                with open(os.path.join(support.LATHE, p), encoding='latin-1') as f:
                    lines = sum(1 for _ in f)
                print('  %-24s $%04X %5d lines  %s  %11d cycles' % (
                    p, page, lines, 'compiled' if st == 0 else 'refused: ' + e, cycles))
            for page in (0x1900, 0x1F00):
                print('  $%04X: %d of %d compiled' % (page, sum(1 for r in rows if r[1] == page and r[2] == 0),
                                                      sum(1 for r in rows if r[1] == page)))


if __name__ == '__main__':
    unittest.main()
