"""Stage 12, step 5 of lathe/docs/bbc.md: the whole tool chain on the emulated BBC Model B+128.

One module image (lathe/host/driver/bbcrom.py) holds the Lathe-written compiler (`*LATHE`,
lathe/src/lathec-bbc.env, banks 1 to 5) and the Lathe-written linker (`*LLINK`,
lathe/src/linker-bbc.env, banks 6 to 10). For a program of the end-to-end corpus, on one disc:

1. every module the host tool chain compiles for it (build.py with its environment: the
   program's own modules, lathe/rt/bbc/host.lth, bbc, sys, and the run-time modules the code
   calls, rt_math, rt_frame, rt_bbc...), in the order build.py compiles them, is compiled by
   `*LATHE OPTIONS NAME.lth .` with build.py's options;
2. the objects are linked by `*LLINK ENV MAIN IMAGE IMAGE.map OBJECTS...` with the environment
   file read from the disc;
3. the image is given its load and execution addresses (`*LOAD IMAGE 1900`, `*SAVE IMAGE 1900
   +LENGTH 1900`: the linker writes the bytes, and *RUN needs the addresses a DFS keeps in its
   catalogue) and run with `*RUN IMAGE`;

all in one run of the emulator, --bbc-strict, on memory that starts filled with bytes that are
not 0 (the emulator's --fill-ram, which boards.run_module passes): the first compile runs on that,
and each tool after it, and the program, on what the one before left, as on a real machine. The
program's output must be NAME.expected.out, and
every object file, interface file, the image, its bank files and the map must be byte for byte
what the host compiler and the host linker write from the same inputs in a directory laid out
the same way (the host's own runs of lathec.py and link.py, by base name). A banked program
(lathe/env/bbc-bank.env and its lines, from lathe/tests/test_bbc_bank.py) runs from the module's
RAM form: the image is put there by `*RUN LOADMOD MODULE` first, and the program's start-up
code loads its own banks over the tools'.

The linker on the BBC has the full capacities (since 2026-11-16, when its work area went into
sideways RAM: lathe/docs/bbc.md, "The linker links the compiler"), so it links every program of
the corpus. The compiler's test programs outtest and regtest (LARGE), compiled by the host, are
linked on the BBC as the host links them (regtest with LATHE_BBC_TOOLCHAIN only). The compiler and
the linker themselves are linked there by test_bbc_selflink.py.

By default (about 15 s) a few programs (QUICK), one of them banked, and outtest. With
LATHE_BBC_TOOLCHAIN=1 every program of the corpus the BBC runs (66 of e2e and 3 of e2e-config,
about 90 s). LATHE_BBC_TOOLCHAIN_REPORT=1 prints, for each link, the cycles in the ROM form, far
calls and `with` blocks (a counting copy of the linker), files opened and bytes read and written
(the emulator's exit report; its MOS charges about nothing for a file call), the cycles of the
whole run, and the start-up's.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import src_support as support
import test_bbc_selfhost as selfhost
from test_cases import cases, defines, _name, _read

import bbcrom
import boards
import build
import mapenv

ALL = os.environ.get('LATHE_BBC_TOOLCHAIN') == '1'
REPORT = os.environ.get('LATHE_BBC_TOOLCHAIN_REPORT') == '1'
COMPILER_ENV = os.path.join(support.SRC, 'lathec-bbc.env')
LINKER_ENV = os.path.join(support.SRC, 'linker-bbc.env')
BOARD = boards.BOARDS['bbc']
CAP = 4_000_000_000
HAVE_TOOLS = os.path.isfile(support.EMULATOR) and os.path.isfile(build.COMPILER)
HOST_COMPILER = build.COMPILER
HOST_LINKER = build.LINKER


def build_image(out_dir):
    """The module image of both tools in out_dir/MODULE, with LOADMOD beside it. Returns
    (image, the linker's ROM environment, the linker's map)."""
    tools = []
    first = 1
    for command, source, env in (('LATHE', 'lathec.lth', COMPILER_ENV), ('LLINK', 'link.lth', LINKER_ENV)):
        d = os.path.join(out_dir, command.lower())
        os.makedirs(d)
        rom = os.path.join(d, os.path.basename(env))
        first = bbcrom.rom_env(env, rom, first)
        resident = os.path.join(d, command)
        build.build(os.path.join(support.SRC, source), resident, env=rom, keep=os.path.join(d, 'work'))
        tools.append((command, resident, rom,
                      os.path.join(d, 'work', os.path.splitext(source)[0] + '.map')))
    image = os.path.join(out_dir, 'MODULE')
    bbcrom.image(tools, image, os.path.join(out_dir, 'listing'))
    bbcrom.loader(os.path.join(out_dir, 'LOADMOD'))
    return image, tools[1][2], tools[1][3]


# ---- What the host tool chain does for a program ----------------------------------------------

def recorded(source, env, work, extra=()):
    """Build source with env as build.py builds it, recording each run of the compiler and the
    linker: [('compile', options, source path) ..., ('link', env, main, objects)]."""
    steps = []
    real = build.run

    def run(cmd, what, cwd=None):
        if cmd[1] == build.COMPILER:
            steps.append(('compile', cmd[2:-2], cmd[-2]))
        elif cmd[1] == build.LINKER:
            steps.append(('link', cmd[2], cmd[3], cmd[6:]))
        return real(cmd, what, cwd)
    build.run = run
    try:
        build.build(source, os.path.join(work, 'host.bin'), env, keep=os.path.join(work, 'build'),
                    defines=list(extra))
    finally:
        build.run = real
    return steps


def lay_out(steps, disk):
    """Copy what the steps read from outside (the sources and the environment) into disk under
    their base names. Returns (each compile's arguments, the link's)."""
    compiles, link = [], None
    for step in steps:
        if step[0] == 'compile':
            _, options, path = step
            name = os.path.basename(path)
            if os.path.exists(os.path.join(disk, name)):
                raise AssertionError(f'two sources named {name}')
            shutil.copyfile(path, os.path.join(disk, name))
            compiles.append(list(options) + [name, '.'])
        else:
            _, env, main, objects = step
            shutil.copyfile(env, os.path.join(disk, os.path.basename(env)))
            image = main.upper()[:7]
            link = ([os.path.basename(env), main, image, image + '.map']
                    + [os.path.basename(o) for o in objects])
    return compiles, link


def host_files(compiles, link, disk):
    """The host compiler and linker run in disk (a copy of the BBC's) as the BBC runs them:
    ({file: bytes} of what they wrote, [(status, output and error output)] of each run)."""
    before = set(os.listdir(disk))
    said = []
    for args in compiles:
        r = subprocess.run([sys.executable, HOST_COMPILER] + args, cwd=disk, capture_output=True)
        said.append((r.returncode, r.stdout + r.stderr))
    r = subprocess.run([sys.executable, HOST_LINKER] + link, cwd=disk, capture_output=True)
    said.append((r.returncode, r.stdout + r.stderr))
    return {f: _read(os.path.join(disk, f), 'rb') for f in os.listdir(disk) if f not in before}, said


# ---- The same on the BBC ----------------------------------------------------------------------

def bbc_lines(compiles, link, load, length, run=True):
    """The * commands: each compile, the link, the image's addresses and its run."""
    lines = [boards.module_command('LATHE', args) for args in compiles]
    lines.append(boards.module_command('LLINK', link))
    image = link[2]
    if run:
        lines += ['LOAD %s %X' % (image, load), 'SAVE %s %X +%X %X' % (image, load, length, load)]
        lines.append('RUN ' + image)
    return lines


def bbc_run(module, disk, lines, ram=False):
    """Runs the lines on the BBC with the module image (in its RAM form through LOADMOD with
    ram), in disk: (status, output, what the MOS said, {file: bytes} written, CPU cycles, (files
    opened, bytes read, bytes written))."""
    before = set(os.listdir(disk))
    first = []
    copied = []
    if ram:
        for name in ('LOADMOD', 'LOADMOD.inf'):
            shutil.copy(os.path.join(os.path.dirname(module), name), disk)
        shutil.copy(module, os.path.join(disk, 'MODULE'))
        copied += ['LOADMOD', 'LOADMOD.inf', 'MODULE']
        first = ['RUN LOADMOD MODULE'] + first
    command, _, tail = lines[-1].partition(' ')
    code, out, err, cycles = boards.run_module(BOARD, module, disk, command, tail=tail, ram=ram,
                                               before=first + lines[:-1], raw=True, cap=CAP)
    text = err.decode('latin-1')
    status, said, cycles = boards.bbc_status(code, text)
    m = selfhost.FILES_RE.findall(text)
    traffic = tuple(int(n) for n in m[-1]) if m else (0, 0, 0)
    files = {f: _read(os.path.join(disk, f), 'rb') for f in sorted(os.listdir(disk))
             if f not in before and f not in copied and not f.endswith('.inf')}
    return status, boards.bbc_output(out), said, files, cycles, traffic


# ---- The programs -----------------------------------------------------------------------------

CASES = os.path.join(support.LATHE, 'tests', 'cases')
QUICK = ('hello', 'calls', 'rec_tree')      # run by default, with BANKED_QUICK
BANKED_QUICK = ('farcall',)

def host_link(link, disk):
    """The host linker on the link in a copy of disk's object and environment files: (status,
    output and error output joined, as the BBC has one stream)."""
    with tempfile.TemporaryDirectory() as d:
        for f in os.listdir(disk):
            if f.endswith(('.lo', '.env')):
                shutil.copy(os.path.join(disk, f), d)
        r = subprocess.run([sys.executable, HOST_LINKER] + link, cwd=d, capture_output=True)
    return r.returncode, r.stdout + r.stderr


def corpus():
    """[(name, source, environment maker, defines, banked)] of every program: the end-to-end
    cases the BBC runs (test_bbc_cases.py), then the banked cases of e2e-config the BBC runs
    (test_bbc_bank.py)."""
    import test_bbc_bank
    import test_bbc_cases
    found = [(_name(p), p, None, defines(p), False) for p in cases('e2e')
             if _name(p) not in test_bbc_cases.NOT_ON_THE_BBC]
    for name, lines in (('farcall', test_bbc_bank.FARCALL), ('bankdata', test_bbc_bank.BANKDATA),
                        ('regions', test_bbc_bank.REGIONS)):
        found.append((name, os.path.join(CASES, 'e2e-config', name + '.lth'),
                      lambda path, lines=lines: test_bbc_bank.bank_env(path, lines, ports=0), [], True))
    return found


def chosen():
    if ALL:
        return corpus()
    return [c for c in corpus() if c[0] in (BANKED_QUICK if c[4] else QUICK)]


def prepare(case, work):
    """The BBC's disc and the host's for a program, the host's run on its own: (bbc disc, the
    compiles' arguments, the link's, {file: bytes} the host wrote, what the host said, the
    program's load address)."""
    name, source, make_env, extra, banked = case
    os.makedirs(work)
    env = make_env(os.path.join(work, name + '.env')) if make_env else 'bbc'
    steps = recorded(source, env, work, extra)
    disk = os.path.join(work, 'bbc')
    os.makedirs(disk)
    compiles, link = lay_out(steps, disk)
    host = os.path.join(work, 'host')
    shutil.copytree(disk, host)
    files, said = host_files(compiles, link, host)
    load = mapenv.read_env(steps[-1][1]).code[0]
    return disk, compiles, link, files, said, load


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class Toolchain(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-bbc-toolchain-')
        cls.module, cls.linker_env, cls.linker_map = build_image(os.path.join(cls.dir, 'image'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_both_tools_are_in_one_image(self):
        with open(os.path.join(self.dir, 'image', 'listing')) as f:
            listing = f.read()
        self.assertIn('*LATHE: LATHE', listing)
        self.assertIn('*LLINK: LLINK', listing)
        self.assertEqual(re.findall(r'\*LLINK: .*; banks ([0-9, ]+);', listing), ['6, 7, 8, 9, 10'])
        # The linker's tables in main RAM fit $1900-$7BFF and $0401-$06FF beside its resident
        # part; those in regions are in sideways slots 0, 1 and 12 (banks 20 to 22).
        entries = mapenv.read_map(self.linker_map)
        slots = {bank: sorted(e.name for e in entries if e.kind == 'V' and e.bank == bank and e.size > 256)
                 for bank in (20, 21, 22)}
        self.assertEqual(slots, {20: ['lk_name.local', 'lk_tab.slot_sz', 'lk_tab.slot_weight'],
                                 21: ['lk_tab.edge_word', 'lk_tab.fn_edge', 'lk_tab.nodes'],
                                 22: ['lk_tab.work']})
        self.assertFalse([e for e in entries if e.kind == 'V' and e.bank is not None and e.bank not in slots])

    def test_programs_are_compiled_linked_and_run_on_the_bbc(self):
        for case in chosen():
            name, source, _, _, banked = case
            with self.subTest(program=name):
                disk, compiles, link, files, said, load = prepare(case, os.path.join(self.dir, name))
                self.assertEqual(said, [(0, b'')] * len(said))
                lines = bbc_lines(compiles, link, load, len(files[link[2]]))
                status, out, mos, written, cycles, traffic = bbc_run(self.module, disk, lines, ram=banked)
                self.assertEqual((status, mos), (0, b''))
                self.assertEqual(out, _read(os.path.splitext(source)[0] + '.expected.out', 'rb'))
                self.assertEqual(sorted(written), sorted(files))
                for f in files:
                    self.assertTrue(written[f] == files[f], f + ' differs')
                if REPORT:
                    self.report(name, disk, link, files, banked, cycles)

    def test_the_largest_programs_of_lathe_src(self):
        """The compiler's test programs as test_bbc_bank_src.py builds them (banked, the small
        build), compiled by the host and linked on the BBC as the host links them: outtest, and
        regtest, which the BBC's capacities of before 2026-11-16 refused (one file's names in the
        image pass)."""
        for name in LARGE if ALL or REPORT else LARGE[:1]:
            with self.subTest(program=name):
                files, link, disk = link_alone(name, os.path.join(self.dir, name))
                lines = [boards.module_command('LLINK', link)]
                status, out, mos, written, cycles, traffic = bbc_run(self.module, disk, lines)
                self.assertEqual((status, out, mos), (0, b'', b''))
                linked = {f: d for f, d in files.items() if not f.endswith(('.lo', '.li'))}
                self.assertEqual(sorted(written), sorted(linked))
                for f in linked:
                    self.assertTrue(written[f] == linked[f], f + ' differs')
                if REPORT:
                    self.report(name, disk, link, files, True)

    # ---- LATHE_BBC_TOOLCHAIN_REPORT --------------------------------------------------------

    def report(self, name, disk, link, files, banked, chain=0):
        """The link alone, in the ROM form (so that the file traffic is the link's), and in the
        counting copy (far calls and blocks): one line of the table, with the
        cycles of the whole run (memory filled, the compiles, the link, the program) if `chain`."""
        if not hasattr(type(self), 'counting'):
            type(self).counting = build_counting(os.path.join(self.dir, 'counting'))
            start = bbc_run(self.module, disk, ['LLINK'])
            print('\nthe start-up: *LLINK with no arguments (link error 1) takes %d cycles' % start[4])
            print('%-14s %12s %9s %9s %7s %9s %9s %8s %13s' % (
                'link', 'cycles', 'min 2MHz', 'far calls', 'blocks', 'opened', 'read', 'written',
                'all (cycles)'))
        for f in files:
            if f.endswith('.lo') and not os.path.exists(os.path.join(disk, f)):
                shutil.copy(os.path.join(os.path.dirname(disk), 'host', f), disk)
        status, out, mos, written, cycles, traffic = bbc_run(
            self.module, disk, [boards.module_command('LLINK', link)])
        far, withs = counted_link(self.counting, disk, link)
        print('%-14s %12d %9.2f %9d %7d %9d %9d %8d %13d' % (
            (name, cycles, cycles / 2e6 / 60, far, withs) + traffic + (chain,)))


# The compiler's test programs linked on the BBC.
LARGE = ('outtest', 'regtest')


def link_alone(name, work):
    """lathe/src/NAME.lth built for the BBC banked (bbc_support.bank_env, the small build), its
    modules compiled by the host: ({file: bytes} the host wrote, the link's arguments, the BBC's
    disc with the objects and the environment)."""
    import bbc_support
    case = (name, os.path.join(support.SRC, name + '.lth'),
            lambda path: bbc_support.bank_env(name, path), [], True)
    disk, compiles, link, files, said, load = prepare(case, work)
    assert said == [(0, b'')] * len(said), said
    for f in files:
        if f.endswith('.lo'):
            shutil.copy(os.path.join(work, 'host', f), disk)
    return files, link, disk


# ---- The counting copy (LATHE_BBC_TOOLCHAIN_REPORT) -------------------------------------------

def build_counting(where):
    """The linker's developer form with rt_bbc's call() and map() counting and bbc.exit writing
    the counts to the file COUNTS (test_bbc_selfhost.counting_copies, with a fixed name: every
    argument of the linker is a file it reads), the split moved for the counters' code."""
    os.makedirs(where)
    selfhost.counting_copies(where, 0)
    path = os.path.join(where, 'bbc.lth')
    with open(path) as f:
        text = f.read()
    old = '  h = open_out(argv(0))'
    assert text.count(old) == 1
    with open(path, 'w') as f:
        f.write(text.replace(old, '  h = open_out("COUNTS")'))
    with open(LINKER_ENV) as f:
        env = f.read()
    with open(os.path.join(where, 'llink.env'), 'w') as f:
        f.write(selfhost.moved_split(env, selfhost.COUNTING_ROOM))
    image = os.path.join(where, 'llink.bin')
    build.build(os.path.join(where, 'link.lth'), image, env=os.path.join(where, 'llink.env'),
                keep=os.path.join(where, 'work'))
    return image


def counted_link(image, disk, link):
    """(far calls, `with` blocks) of the link in the counting copy (whose start() clears its
    counters: test_bbc_selfhost.counting_copies)."""
    env = mapenv.read_env(os.path.splitext(image)[0] + '.env')
    build.window_files(env, os.path.dirname(image), disk)
    try:
        status, out, err, cycles = boards.run_mos(BOARD, image, disk, link, cap=CAP,
                                                  module=boards.module_options(env))
        with open(os.path.join(disk, 'COUNTS'), 'rb') as f:
            data = f.read()
    finally:
        for name in list(env.files) + ['COUNTS']:
            if os.path.exists(os.path.join(disk, name)):
                os.unlink(os.path.join(disk, name))
    return int.from_bytes(data[:3], 'big'), int.from_bytes(data[3:6], 'big')


if __name__ == '__main__':
    unittest.main()
