"""Image B, the 128 KB image for machines with no sideways RAM (lathe/docs/bbc.md, "The image for
machines with no sideways RAM"): the linker's form `define RAM32 1` with `define ADAPT 1`, linked
from $1F00 with the 32K build's capacities (LKSMALL 2) but for its symbols of the object files,
its slots and its calls, which are dynamic regions of planes (LKROOMS 1) that the module's placer
puts in main RAM alone as the tool starts (`main_only`: FIXED_REGIONS with dynamic regions; no slot
is probed or used), each block on a page (`top WIN N $BEFF`), the slots and calls `dynamic main`
(told fixed: their accessors map nothing); `link` in the linker's second bank; BBCFS 3, the names
of the filing system the MOS names. The compiler is its 32K form with BBCFS 3 (the compiler's half
is not built yet), which runs at PAGE $1900 only.

What is tested here, by default:

- the image fits the 128 KB module, the linker's list has no sideways RAM to probe (main_only);
- what the linker gets on each machine, by the model of the placer (places.plan): a Model B with
  the DFS (PAGE $1900), with ADFS and the DFS (PAGE $1F00), and a B+ in a shadow mode at each;
- on a Model B with no sideways RAM at PAGE $1900 and at $1F00: *LLINK links a program of the
  end-to-end cases from the host compiler's objects, every file the host linker's at that
  machine's capacities; a generated program that needs more slots than ADFS's machine gives
  (6 modules of 22 functions: 528) is linked at $1900 and refused at $1F00, each as the host
  linker at those capacities does it (so the real placer gives what the model says); PAGE above
  $1F00 is refused, and a screen mode below the tool's memory.

LATHE_BBC_IMAGE_B_PROGRAMS=1: the largest generated program each machine takes, under the
emulator's DFS at PAGE $1900 (the 25 KB program, 8 modules of 26 functions: every module compiled
by *LATHE, linked by *LLINK @LINKARG, *SAVEd and run, as test_gen_program's 32K test does it) and
under its ADFS at $1F00 (6 modules of 21 functions, the objects the host compiler's, since the
compiler's form here runs at $1900 only: linked by *LLINK and run); every file the host tools'
under that filing system's names (BBCFS 3), and the host linker at that machine's capacities
gives the same. LATHE_BBC_IMAGE_B_REPORT=1 prints the capacities, the account and the cycles.
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
COMPILER_SETTINGS = {'RAM32': 1, 'BBCFS': 3}
LINKER_SETTINGS = {'RAM32': 1, 'ADAPT': 1, 'ADFS': 1, 'BBCFS': 3}
ROOMS_LINKER = os.path.join(HERE, 'lk_rooms.py')
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
    'Model B, DFS': {'locals': 512, 'slots': 1024, 'calls': 768},
    'Model B, ADFS and DFS': {'locals': 512, 'slots': 512, 'calls': 512},
    'B+, DFS, shadow mode': {'locals': 768, 'slots': 1024, 'calls': 768},
    'B+, ADFS and DFS, shadow mode': {'locals': 512, 'slots': 1024, 'calls': 512},
}
# The generated programs (modules, functions a module): one that needs 528 slots, more than ADFS's
# machine gives; the largest each machine links and holds (PAGE, the emulator's filing system).
MORE_SLOTS_THAN_ADFS = (6, 22)
LARGEST = (('1900', 'dfs', 8, 26), ('1F00', 'adfs', 6, 21))


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


def host_objects(work, main, env):
    """The BBC's disc for a generated program with the host compiler's objects and interfaces on
    it and LINKARG: (disc, the compiles' arguments, the link's, {file: bytes} the host tools wrote)."""
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
        if f.endswith(('.lo', '.li')):
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

    def test_a_program_that_needs_more_slots_than_adfs_gives_links_with_the_dfs_alone(self):
        """The machines' capacities told apart by the real placer: a generated program that needs
        528 slots links at PAGE $1900 (1,024) and not at $1F00 (512), each time as the host
        linker at that machine's capacities does it, the files or the error."""
        work = os.path.join(self.dir, 'more-slots')
        main, env, expected, p = generated(work, *MORE_SLOTS_THAN_ADFS, page='1F00')
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
                    self.assertIn(b'slots', host_said)
                    self.assertEqual((status, out + mos), (1, host_said))

    def test_a_tool_is_refused_where_it_cannot_run(self):
        import test_bbc_rom128 as rom128
        for page, mode, said in (('2100', 7, b'PAGE too high'), ('1900', 4, b'Mode 7 needed')):
            with self.subTest(page=page, mode=mode), rom128.scheme(), tempfile.TemporaryDirectory() as d:
                code, out, err, cycles = boards.run_module(board(page, mode), self.image, d, 'LLINK', raw=True)
                self.assertIn(said, out + err)

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

    def test_the_adfs_machine_links_and_runs_its_largest_program(self):
        """Under the emulator's ADFS at PAGE $1F00 the host compiler's objects (the compiler's
        form in the image runs at $1900 only) linked by *LLINK @LINKARG, *SAVEd and run: every file
        the host tools' under ADFS's names, and the host linker at the ADFS machine's capacities
        links it so too."""
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
        test_bbc_adfs.to_adfs(disk)
        before = test_bbc_dfs.files_of(disk)
        lines = chain.bbc_lines(compiles, link, int(page, 16), len(files[link[2]]))[len(compiles):]
        lines[0] = boards.module_command('LLINK', ['@' + selflink.COMMAND_FILE])
        status, out, mos, cycles = fs_run(self.image, disk, lines, page, fs)
        self.assertEqual((status, mos), (0, b''))
        self.assertEqual(out, expected)
        written = {f: d for f, d in test_bbc_dfs.files_of(disk).items() if before.get(f) != d}
        want = {bbcfs.asked_host_file(f, 8): data for f, data in files_at.items()}
        self.assertEqual(sorted(written), sorted(want))
        for f in want:
            self.assertTrue(written[f] == want[f], f + ' differs')
        if REPORT:
            print('\nImage B, ADFS: %d modules of %d functions, %d lines, the image %d bytes; the link and '
                  'the run %.1f million cycles' % (modules, functions, p.lines(), len(files[link[2]]), cycles / 1e6))


if __name__ == '__main__':
    unittest.main()
