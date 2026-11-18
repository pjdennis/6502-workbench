"""The tools' 32K variant: a BBC Model B with 32 KB of RAM, no sideways RAM and no shadow screen,
the Acorn DFS, mode 7 (lathe/docs/bbc.md, "The 32K Model B"). `define RAM32 1` in the tools'
environments (bbcrom.rom_env(..., settings={'RAM32': 1})): every table in main RAM, in regions
in fixed memory that the compiler is told of (FIXED_REGIONS, lathec -fREGION), so that no
function stays fixed for a `with` block and all the compiler's code but fold is in the module's
banks; the capacities are the small build's with RAM32's own where they differ (SMALL 1 and
`#if RAM32` in the twins, script_host.RAM32).

The 32K image is the module's sixteen-bank form (scheme direct16): both tools' 32K forms with the
texts of their errors (bbcrom.py, "The texts in the module") need one bank with 4,227 bytes free
after its code for the module's code and the texts, and in the eight-bank form the fullest tools
leave at most 3,230 (EightBanks, below).

What is tested here, by default:

- rom_env sets a define of the source (RAM32), and refuses one the source does not have;
- the compiler's 32K form with the DFS's names: nothing in sideways RAM, nothing kept fixed,
  everything in $1900-$7BFF and $0401-$06FF; with LATHE_BBC_RAM32_REPORT=1 its account of main
  RAM and of the image;
- the module image of both tools' 32K forms (the compiler in banks 1 to 5, the linker in 6 to
  10), which refuses a command where HIMEM is below the tool's memory (ScreenMode);
- on the Model B (boards.BOARDS['bbc32']: --bbc-model b, --bbc-fs dfs) with --fill-ram, from that
  image: both tools' errors with their texts and nothing on the disc; cases/e2e-config's farcall
  (six modules, banked) compiled by *LATHE, linked by *LLINK @LINKARG and run, every file the host
  tools' and the output the case's;
- that the eight-bank form has no bank with room for the module's code and texts.

With LATHE_BBC_RAM32=1 it also compiles every module of lathe/src and lathe/rt the 32K form's
capacities take (the host compiler at those capacities decides which) and checks each against
the host, and those it does not take give the host's capacity error (the assessment in
lathe/docs/bbc.md, "The 32K Model B"), and runs the tool chain on every program of
test_bbc_toolchain's corpus that the host's tools take at the 32K capacities;
LATHE_BBC_RAM32_REPORT=1 prints the cycles and the disc's files.
"""
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import src_support as support  # noqa: E402
import bbcrom  # noqa: E402
import bbcfs  # noqa: E402
import boards  # noqa: E402
import build  # noqa: E402
import mapenv  # noqa: E402
import test_bbc_dfs as dfs  # noqa: E402
import test_bbc_rom as tbr  # noqa: E402

ALL = os.environ.get('LATHE_BBC_RAM32') == '1'
REPORT = os.environ.get('LATHE_BBC_RAM32_REPORT') == '1'
HAVE_TOOLS = tbr.HAVE_TOOLS
BANKS = 16                  # the 32K image: the eight-bank form has no bank with room for the texts
FIRST_BANK = 1              # a sixteen-bank image keeps bank 0 for the module's own code
BOARD = boards.BOARDS['bbc32']
COMPILER_ENV = os.path.join(support.SRC, 'lathec-bbc.env')
LINKER_ENV = os.path.join(support.SRC, 'linker-bbc.env')
MAIN_RAM = ((0x1900, 0x7BFF), (0x0401, 0x06FF))     # what a program has in mode 7 with the DFS
CAP = 4_000_000_000


def tool_env(source, out_dir, first, ram32, banks=BANKS):
    """The ROM environment of a tool for an image of `banks` banks with the DFS's names (BBCFS 1),
    from bank `first`, in its 32K form with ram32: (its path, the next bank free)."""
    dev = dfs.dfs_env(source, os.path.join(out_dir, 'dev.env'))
    rom = os.path.join(out_dir, os.path.basename(source))
    first = bbcrom.rom_env(dev, rom, first, banks, settings={'RAM32': 1} if ram32 else None)
    return rom, first


def build_tools(out_dir, linker=True, banks=BANKS):
    """The compiler in its 32K form (banks 1 to 5 of sixteen, 0 to 4 of eight) and, with linker,
    the linker in its 32K form (linker-bbc.env with RAM32 1, the five banks after them, or three of
    eight), each linked with the DFS's names: [(command, resident part, ROM environment, map)]."""
    tools, first = [], FIRST_BANK if banks == 16 else 0
    for command, source, env, ram32 in (('LATHE', 'lathec.lth', COMPILER_ENV, True),
                                        ('LLINK', 'link.lth', LINKER_ENV, True))[:2 if linker else 1]:
        d = os.path.join(out_dir, command.lower())
        os.makedirs(d)
        rom, first = tool_env(env, d, first, ram32, banks)
        resident = os.path.join(d, command)
        build.build(os.path.join(support.SRC, source), resident, env=rom, keep=os.path.join(d, 'work'))
        tools.append((command, resident, rom, os.path.join(d, 'work', os.path.splitext(source)[0] + '.map')))
    return tools


def build_image(out_dir, linker=True, check_himem=True):
    """The sixteen-bank module image of the tools (build_tools) in out_dir/MODULE, with the banks in
    use alone in MODULE.disc and LOADMOD beside it: (image, the tools, the listing's text). With
    check_himem, a command whose program's memory reaches above HIMEM is refused (bbcrom.image)."""
    tools = build_tools(out_dir, linker)
    image = os.path.join(out_dir, 'MODULE')
    listing = os.path.join(out_dir, 'listing')
    bbcrom.image(tools, image, listing, short=image + '.disc', banks=BANKS, check_himem=check_himem)
    bbcrom.loader(os.path.join(out_dir, 'LOADMOD'))
    with open(listing) as f:
        return image, tools, f.read()


def main_ram(map_path):
    """What the 32K form takes of main RAM, from its map: {'code': fixed code, constants and
    stubs from $1900, 'variables': the variables and frames in the data ranges, 'free': what
    is left of $1900-$7BFF and $0401-$06FF, 'top': the last address used below $7C00}."""
    entries = mapenv.read_map(map_path)
    fixed = [e for e in entries if e.bank is None and e.kind in 'FDTVS' and e.size]
    code = max(e.addr + e.size for e in fixed if e.kind in 'FDT' and 0x1900 <= e.addr < 0x7C00) - 0x1900
    variables, top = 0, 0
    for low, high in MAIN_RAM:
        inside = [e for e in fixed if e.kind in 'VS' and low <= e.addr <= high]
        if inside:
            start = low if low != 0x1900 else min(e.addr for e in inside)
            end = max(e.addr + e.size for e in inside)
            variables += end - start
            top = max(top, end - 1) if low == 0x1900 else top
    room = sum(high - low + 1 for low, high in MAIN_RAM)
    return {'code': code, 'variables': variables, 'free': room - code - variables, 'top': top}


def run(image, disk, lines, cap=CAP, mode=7, ram=False):
    """The * commands on the Model B (BOARD) in screen mode `mode` with the module image in ROM,
    scheme direct8, in disk: (status, output, what the MOS said, CPU cycles, the emulator's
    report)."""
    import dataclasses
    board = dataclasses.replace(BOARD, options=BOARD.options + ('--bbc-mode', str(mode)))
    command, _, tail = lines[-1].partition(' ')
    code, out, err, cycles = boards.run_module(board, image, disk, command, tail=tail, before=lines[:-1],
                                               raw=True, cap=cap, scheme=bbcrom.SCHEMES[BANKS], ram=ram)
    text = err.decode('latin-1')
    status, said, cycles = boards.bbc_status(code, text)
    return status, boards.bbc_output(out), said, cycles, text


@unittest.skipUnless(HAVE_TOOLS, 'compiler or emulator missing')
class ScreenMode(unittest.TestCase):
    """Started in a mode whose screen is below the tools' memory (mode 4: HIMEM $5800 on a Model
    B), a tool would put its tables in the screen, and the MOS's text would write over them.
    The module refuses the command first, with the MOS error `Mode 7 needed`, before it touches
    anything (bbcrom.image checks by default, in every image); without the check
    (check_himem=False) the tool starts and writes to the screen, which --bbc-strict ends as a
    failed check."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-bbc-ram32-mode-')
        cls.checked = build_image(os.path.join(cls.dir, 'checked'), linker=False)[0]
        cls.unchecked = build_image(os.path.join(cls.dir, 'unchecked'), linker=False, check_himem=False)[0]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def disk(self, name):
        d = os.path.join(self.dir, name)
        os.makedirs(d)
        dfs.put(d, 'hello.lth', b'module hello\n')
        return d

    def test_in_mode_4_the_command_is_refused(self):
        for mode in (4, 6, 0):
            with self.subTest(mode=mode):
                disk = self.disk('refused%d' % mode)
                status, out, said, cycles, report = run(self.checked, disk, ['LATHE hello.lth .'], mode=mode)
                self.assertEqual((status, out, said), (1, b'', b'Mode 7 needed\n'))
                self.assertIn('screen-writes=0', report)
                self.assertEqual(sorted(dfs.files_of(disk)), ['L.HELLO'])

    def test_in_mode_7_it_runs(self):
        disk = self.disk('mode7')
        status, out, said, cycles, report = run(self.checked, disk, ['LATHE hello.lth .'])
        self.assertEqual((status, out, said), (0, b'', b''))
        self.assertIn('O.HELLO', dfs.files_of(disk))

    def test_without_the_check_the_tool_writes_to_the_screen(self):
        disk = self.disk('unchecked-run')
        with self.assertRaises(boards.RunError) as caught:
            run(self.unchecked, disk, ['LATHE hello.lth .'], mode=4)
        self.assertIn('the run ended by strict', str(caught.exception))
        self.assertIn('write to the screen at $', str(caught.exception))


@unittest.skipUnless(HAVE_TOOLS, 'compiler or emulator missing')
class EightBanks(unittest.TestCase):
    """Both tools' 32K forms in the eight-bank form (the compiler in banks 0 to 4, the linker in 5
    to 7): their code fits the banks, but no bank has room after its code for the module's code
    and the texts of the errors, which must be in one bank (the home bank): the image is refused."""

    def test_no_bank_has_room_for_the_module_code_and_texts(self):
        with tempfile.TemporaryDirectory(prefix='lathe-bbc-ram32-8-') as d:
            tools = build_tools(d, banks=8)
            programs = [bbcrom.load_program(bbcrom.Program(c, r, e, m), 8) for c, r, e, m in tools]
            code = bbcrom.module_code(programs, [[] for _ in programs])[1]
            room = max(bbcrom.TOP - bbcrom.FIRST + 1 - len(b.data) for p in programs for b in p.banks
                       if b.value & 0x80)
            self.assertLess(room, len(code))
            with self.assertRaises(bbcrom.ImageError):
                bbcrom.image(tools, os.path.join(d, 'MODULE'), banks=8)
            if REPORT:
                print('\nthe eight-bank form: the module\'s code and texts %d bytes, the most room after a '
                      'bank\'s code %d' % (len(code), room))


class RomEnv(unittest.TestCase):
    def test_rom_env_sets_a_define_of_the_source(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, 'a.env')
            with open(src, 'w') as f:
                f.write('define ROMFORM 0\ndefine RAM32 0   ; the 32K variant\nwindow WIN $8000 $BFDF\n'
                        'unless RAM32 bank WIN 1 $81 A1.BIN\nwhen RAM32 bank WIN 2 $82 A2.BIN\n')
            out = os.path.join(d, 'b.env')
            self.assertEqual(bbcrom.rom_env(src, out, 0, 8, settings={'RAM32': 1}), 1)
            with open(out) as f:
                text = f.read()
            self.assertIn('define RAM32 1   ; the 32K variant\n', text)
            self.assertIn('unless RAM32 bank WIN 1 $81 A1.BIN\n', text)     # not an entry there
            self.assertIn('bank      WIN 2 $80 A2.BIN\n', text)
            with self.assertRaises(bbcrom.ImageError) as caught:
                bbcrom.rom_env(src, out, 0, 8, settings={'TINY': 1})
            self.assertIn('no define of TINY to set', str(caught.exception))


@unittest.skipUnless(HAVE_TOOLS, 'compiler or emulator missing')
class Ram32(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-bbc-ram32-')
        cls.image, cls.tools, cls.listing = build_image(os.path.join(cls.dir, 'image'))
        cls.map = cls.tools[0][3]
        if REPORT:
            print('\n' + account(cls.map, cls.listing))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_every_table_is_in_main_ram_and_nothing_is_kept_fixed(self):
        entries = mapenv.read_map(self.map)
        self.assertEqual(sorted(e.number for e in entries if e.kind == 'W'), [1, 2, 3, 4, 5])
        self.assertEqual([e.name for e in entries if e.kind == 'F' and e.kept is not None], [])
        self.assertEqual([e.name for e in entries if e.kind == 'V' and e.bank is not None], [])
        for e in entries:
            if e.kind in 'FDTVS' and e.bank is None and e.size and e.addr >= 0x100:
                with self.subTest(item=e.name):
                    self.assertTrue(any(low <= e.addr and e.addr + e.size - 1 <= high for low, high in MAIN_RAM),
                                    '%s at $%04X' % (e.name, e.addr))
        for name in ('kernel.names', 'kernel.sym_bytes', 'fbuf.buffer', 'lex.string', 'out.table',
                     'decl.want_module'):
            with self.subTest(table=name):
                self.assertIsNone([e for e in entries if e.kind == 'V' and e.name == name][0].bank)
        self.assertGreaterEqual(main_ram(self.map)['free'], 0)

    def test_the_image_holds_both_tools_32k_forms(self):
        self.assertIn('16 banks of 16 KB, scheme direct16', self.listing)
        self.assertEqual(re.findall(r'\*LATHE: .*; banks ([0-9, ]+);', self.listing), ['1, 2, 3, 4, 5'])
        self.assertEqual(re.findall(r'\*LLINK: .*; banks ([0-9, ]+);', self.listing), ['6, 7, 8, 9, 10'])
        self.assertEqual(re.findall(r'regions in ([a-z]+);', self.listing), ['none', 'none'])
        self.assertEqual(os.path.getsize(self.image), BANKS * 0x4000)

    def test_errors_have_their_texts_with_nothing_on_the_disc(self):
        """The texts are in the module (lathe/docs/bbc.md, "The texts in the module"): on the Model
        B, with only the source on the disc, each tool's errors are the host's, word for word."""
        import subprocess
        import test_bbc_texts as texts
        cases = [('LATHE', name, text, args) for name, text, args in texts.compiler_cases()]
        cases += [('LLINK', 'link ' + name, None, args) for name, args in texts.LINKER_CASES]
        for command, name, text, args in cases:
            with self.subTest(case=name):
                disk = tempfile.mkdtemp(dir=self.dir)
                host = tempfile.mkdtemp(dir=self.dir)
                if text is not None:
                    dfs.put(disk, args[0], text.encode())
                    with open(os.path.join(host, args[0]), 'w') as f:
                        f.write(text)
                tool = build.COMPILER if command == 'LATHE' else build.LINKER
                r = subprocess.run([sys.executable, tool] + args, cwd=host, capture_output=True)
                status, out, said, cycles, report = run(self.image, disk, [boards.module_command(command, args)])
                self.assertEqual((status, out), (r.returncode, r.stdout + r.stderr))
                self.assertNotEqual(status, 0)

    def test_farcall_is_compiled_linked_and_run_on_the_model_b(self):
        """The tool chain on the 32K Model B: cases/e2e-config/farcall.lth, six modules and the
        run-time modules, banked (its banks loaded into the module's RAM form by its start-up),
        compiled by *LATHE, linked by *LLINK @LINKARG, and run (chain)."""
        import test_bbc_toolchain as toolchain
        case = [c for c in toolchain.corpus() if c[0] == 'farcall'][0]
        result = chain(self, self.image, case, os.path.join(self.dir, 'farcall'))
        if REPORT:
            print('\n' + chain_text('farcall', result))

    @unittest.skipUnless(ALL, 'LATHE_BBC_RAM32=1 runs the tool chain on every case the 32K tools take')
    def test_the_tool_chain_on_the_model_b(self):
        """Every case of test_bbc_toolchain's corpus that the host's tools take at the 32K forms'
        capacities (the compiler's: lathec_ram32.py; the linker's: lk_small.load(2)) goes through
        the chain on the Model B as farcall does; the others are listed with the host's error."""
        import test_bbc_toolchain as toolchain
        refused = []
        for case in toolchain.corpus():
            name = case[0]
            work = os.path.join(self.dir, 'all-' + name)
            why = host_refuses(case, work + '-host')
            if why:
                refused.append((name, why))
                continue
            with self.subTest(program=name):
                result = chain(self, self.image, case, work)
                if REPORT:
                    print('\n' + chain_text(name, result))
        if REPORT:
            print('\nrefused at the 32K capacities: ' + '; '.join('%s (%s)' % r for r in refused))


LINK_FILE = 'LINKARG'               # the linker's arguments, for *LLINK @LINKARG


def chain(case, image, program, work, drive='1'):
    """The tool chain for one program of test_bbc_toolchain's corpus on the 32K Model B, from the
    image, under the DFS's names: each module compiled by *LATHE, the objects and interfaces on
    drive 1 (a side holds 31 files), the link by *LLINK @LINKARG, the image *SAVEd with its
    addresses and run. Every file written is the host tools' of the name it maps, and the output
    is the case's. A banked program runs with the module's RAM form, which LOADMOD fills from the
    image first, as on a developer's machine. Returns (CPU cycles of the compiles and the link,
    of the whole run, {drive: (files, bytes)} on the disc at the end, the program's size)."""
    import test_bbc_toolchain as toolchain
    name, source, _, _, banked = program
    os.makedirs(work)
    disk, compiles, link, files, said, load = toolchain.prepare(dfs.dfs_case(program, work), os.path.join(work, 'w'))
    case.assertEqual(said, [(0, b'')] * len(said))
    compiles = [c[:-1] + [drive] for c in compiles]
    link = link[:4] + [drive + '/' + o for o in link[4:]]
    files = dfs.host_run(compiles, link, disk, os.path.join(work, 'host-' + drive), drive)
    dfs.to_dfs(disk)
    dfs.put(disk, LINK_FILE, (' '.join(link) + '\r').encode())
    first = []
    if banked:
        for f, path in (('LOADMOD', os.path.join(os.path.dirname(image), 'LOADMOD')), ('MODULE', image + '.disc')):
            with open(path, 'rb') as fh:
                dfs.put(disk, f, fh.read())
        with open(bbcfs.host_path(disk, 'LOADMOD') + '.inf', 'w') as f:
            f.write(boards.inf_text('$.LOADMOD', 0x1900, os.path.getsize(bbcfs.host_path(disk, 'LOADMOD'))))
        first = ['RUN LOADMOD MODULE']
    tools = [boards.module_command('LATHE', args) for args in compiles] + ['LLINK @' + LINK_FILE]
    before = dict(dfs.files_of(disk))
    status, out, said, cycles_tools, report = run(image, disk, first + tools, ram=banked)
    case.assertEqual((status, out, said), (0, b'', b''))
    case.assertIn('screen-writes=0', report)
    lines = toolchain.bbc_lines(compiles, link, load, len(files[link[2]]))[len(compiles) + 1:]
    cycles_run = None
    # A program with regions in sideways RAM slots (regions.lth) has no RAM to run in on a Model B:
    # it is compiled and linked, and not run.
    if not sideways(os.path.join(work, 'host-' + drive, link[0])):
        status, out, said, cycles_run, report = run(image, disk, first + lines, ram=banked)
        case.assertEqual((status, said), (0, b''))
        with open(os.path.splitext(source)[0] + '.expected.out', 'rb') as f:
            case.assertEqual(out, f.read())
    written = {f: d for f, d in dfs.files_of(disk).items() if before.get(f) != d}
    want = {bbcfs.host_file(bbcfs.dfs_name(f)): data for f, data in files.items()}
    case.assertEqual(sorted(written), sorted(want))
    for f in want:
        case.assertTrue(written[f] == want[f], f + ' differs')
    return cycles_tools, cycles_run, dfs.catalogue(disk), len(files[link[2]]), len(compiles)


def sideways(env_path):
    """True if the environment has a bank in a sideways RAM slot (a `bank` value below $80)."""
    return any(w[0].lower() == 'bank' and len(w) >= 4 and not mapenv._number(w[3], env_path) & 0x80
               for n, w in mapenv.read_entries(env_path))


def chain_text(name, result):
    cycles, run_cycles, disc, size, compiles = result
    return ('%s on the 32K Model B: %d compiles and the link %d cycles (%.2f minutes at 2 MHz); the image '
            '%d bytes%s; the disc: %s' % (name, compiles, cycles, cycles / 2e6 / 60, size,
                                          '' if run_cycles is not None else ', not run (its regions are in sideways RAM)',
                                        ', '.join('drive %d %d files %d bytes' % (d, n, b)
                                                  for d, (n, b) in sorted(disc.items()))))


def host_refuses(program, work):
    """Why the host's tools at the 32K forms' capacities refuse the program, or None: each module
    compiled by lathec_ram32.py, linked by the host linker at LKSMALL 2."""
    import subprocess
    import test_bbc_toolchain as toolchain
    os.makedirs(work)
    disk, compiles, link, files, said, load = toolchain.prepare(dfs.dfs_case(program, work), os.path.join(work, 'w'))
    for args in compiles:
        r = subprocess.run([sys.executable, ORACLE] + args, cwd=disk, capture_output=True)
        if r.returncode:
            return (r.stdout + r.stderr).decode('latin-1').strip().splitlines()[-1]
    r = subprocess.run([sys.executable, '-c', 'import sys, lk_small; lk_small.load(2); import env, link; '
                        'env.start(sys.argv[1:]); link.main()'] + link, cwd=disk, capture_output=True,
                       env=dict(os.environ, PYTHONPATH=os.pathsep.join([HERE, os.path.join(support.LATHE, 'host')])))
    if r.returncode:
        return (r.stdout + r.stderr).decode('latin-1').strip().splitlines()[-1]
    return None


ORACLE = os.path.join(HERE, 'lathec_ram32.py')


def assessed():
    """[(path, options)] of every module of lathe/src and lathe/rt the host compiler compiles at
    full size with the options memory_report gives it (a run-time module for a board only, with
    that board's)."""
    import glob
    import subprocess
    import memory_report
    found = []
    work = tempfile.mkdtemp(prefix='lathe-ram32-options-')
    try:
        for path in sorted(glob.glob(os.path.join(support.SRC, '*.lth')) + glob.glob(os.path.join(support.LATHE, 'rt', '*.lth'))):
            for env_name in (None, 'michael', 'bbc-bank'):
                options = tuple(memory_report.options_of(path, env_name))
                if prepare_li(path, options, work) is not None:
                    found.append((path, options))
                    break
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return found


def prepare_li(path, options, work):
    """A directory under work with the source at path and the host's interfaces (at full size) of
    the modules it imports, or None if the host compiler does not compile them all."""
    import subprocess
    name = build.module_name(path)
    d = os.path.join(work, name + '-' + str(abs(hash(options)) % 10000))
    if os.path.isdir(d):
        return d
    lis = os.path.join(work, 'li-' + str(abs(hash(options)) % 10000))
    os.makedirs(lis, exist_ok=True)
    try:
        order = build.module_order(path)
    except build.BuildError:
        return None
    for _, dep in order:
        r = subprocess.run([sys.executable, build.COMPILER] + list(options) + [dep, lis], capture_output=True)
        if r.returncode != 0:
            return None
    os.makedirs(d)
    shutil.copy(path, d)
    for _, dep in order[:-1]:
        shutil.copy(os.path.join(lis, build.module_name(dep) + '.li'), d)
    return d


def host_compile(d, name, options):
    """The 32K form's oracle in a copy of d: (status, output and error output, {file: bytes})."""
    import subprocess
    where = d + '-host'
    shutil.copytree(d, where)
    before = set(os.listdir(where))
    r = subprocess.run([sys.executable, ORACLE] + list(options) + [name + '.lth', '.'], cwd=where,
                       capture_output=True)
    files = {}
    for f in sorted(os.listdir(where)):
        if f not in before:
            with open(os.path.join(where, f), 'rb') as fh:
                files[f] = fh.read()
    return r.returncode, r.stdout + r.stderr, files


@unittest.skipUnless(HAVE_TOOLS and ALL, 'LATHE_BBC_RAM32=1 compiles every module the 32K form takes')
class Assessment(unittest.TestCase):
    """Every module of lathe/src and lathe/rt compiled by *LATHE on the 32K Model B: those the
    32K form's capacities take give the host's files, those they do not the host's capacity
    error (lathec_ram32.py at the same capacities)."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-bbc-ram32-all-')
        cls.image, cls.tools, cls.listing = build_image(os.path.join(cls.dir, 'image'), linker=False)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_each_module_compiles_as_the_host_does_at_the_same_capacities(self):
        rows = []
        for path, options in assessed():
            name = build.module_name(path)
            d = prepare_li(path, options, os.path.join(self.dir, 'work'))
            host = host_compile(d, name, options)
            disk = d + '-bbc'
            shutil.copytree(d, disk)
            dfs.to_dfs(disk)
            before = dict(dfs.files_of(disk))
            status, out, said, cycles, report = run(self.image, disk,
                                                    [boards.module_command('LATHE', list(options) + [name + '.lth', '.'])])
            written = {f: data for f, data in dfs.files_of(disk).items() if before.get(f) != data}
            want = {bbcfs.host_file(bbcfs.dfs_name(f)): data for f, data in host[2].items()}
            with self.subTest(module=os.path.relpath(path, support.LATHE)):
                self.assertEqual((status, said), (host[0], b''))
                if host[0] == 0:
                    self.assertEqual(sorted(written), sorted(want))
                    for f in want:
                        self.assertTrue(written[f] == want[f], f + ' differs')
                else:
                    self.assertEqual(re.findall(rb'error \d+', out), re.findall(rb'error \d+', host[1]))
            rows.append((os.path.relpath(path, support.LATHE), host[0], cycles,
                         (re.findall(rb'error \d+', host[1]) or [b''])[0].decode()))
        if REPORT:
            print('\nThe 32K form on the Model B, each module of lathe/src and lathe/rt:')
            for p, st, cycles, e in rows:
                with open(os.path.join(support.LATHE, p), encoding='latin-1') as f:
                    lines = sum(1 for _ in f)
                print('  %-24s %5d lines  %s  %11d cycles  %6.2f min at 2 MHz' % (
                    p, lines, 'compiled' if st == 0 else 'refused: ' + e, cycles, cycles / 2e6 / 60))
            print('  %d of %d compiled' % (sum(1 for r in rows if r[1] == 0), len(rows)))


def account(map_path, listing):
    """The 32K form's account of main RAM, as text."""
    ram = main_ram(map_path)
    lines = ['The compiler, 32K form (RAM32 1, BBCFS 1), sixteen-bank ROM form:',
             '  main RAM: code, constants and stubs from $1900 %d bytes; variables and frames %d; '
             'free %d; the variables end at $%04X' % (ram['code'], ram['variables'], ram['free'], ram['top'])]
    lines += ['  ' + l for l in listing.splitlines() if l.startswith('bank ') or 'free' in l or l.startswith('*')]
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    unittest.main()
