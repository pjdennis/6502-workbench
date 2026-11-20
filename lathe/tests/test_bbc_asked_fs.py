"""One image for the DFS and ADFS (lathe/docs/bbc.md, "File names on the BBC", "The filing system
asked when a tool runs"): with `define BBCFS 3` the BBC's build of a program asks the MOS which
filing system is current (OSARGS with A = 0 and Y = 0) each time it names a file, and maps the
name by the DFS's rules if the answer is 4, by ADFS's if it is 8 (making the directory a file is
created in, as BBCFS 2 does), and leaves it as given for any other number. So the tools' ROM
forms built so serve a machine with either filing system from one image.

- Names: the host's twin (lathe/host/driver/bbcfs.py, asked_name) on the rules for each number.
- Map: map() and cdir() on the BBC under --bbc-fs dfs, --bbc-fs adfs and, for the numbers no
  mapping is made for, --bbc-fs host with --bbc-fs-number N: the twin's names.
- One image: the 128 KB image of both tools built with BBCFS 3 (and ADFS 1, main RAM from ADFS's
  PAGE, which serves both) compiles, links and runs a program of several modules under --bbc-fs
  dfs and under --bbc-fs adfs, every file the host tools' under the names of that disc; and
  under a filing system whose number is neither (--bbc-fs host --bbc-fs-number 5, the network
  filing system's), with the names as given. LATHE_BBC_ASKED_FS_REPORT=1 prints the image's
  account.
"""
import dataclasses
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'lathe', 'host', 'driver'))
sys.path.insert(0, HERE)

import bbcfs  # noqa: E402
import boards  # noqa: E402
import build  # noqa: E402

LATHE = os.path.join(ROOT, 'lathe')
HAVE_TOOLS = os.path.isfile(boards.EMULATOR) and os.path.isfile(build.COMPILER)
REPORT = os.environ.get('LATHE_BBC_ASKED_FS_REPORT') == '1'
COMPILER_ENV = os.path.join(LATHE, 'src', 'lathec-bbc.env')
LINKER_ENV = os.path.join(LATHE, 'src', 'linker-bbc.env')
CAP = 4_000_000_000
# The numbers OSARGS gives that no mapping is made for: no filing system, the cassette at 1200
# and 300 baud, the ROM filing system, the network, Telesoftware, IEEE, and two past ADFS.
OTHER_NUMBERS = (0, 1, 2, 3, 5, 6, 7, 9, 255)
UNKNOWN = 5                     # the network filing system's number (memory, not checked)


def asked_env(source, path, page=True):
    """Write to path the environment source with `define BBCFS 3` and, with page, `define ADFS 1`
    (main RAM from ADFS's PAGE, $1F00, which a machine with the DFS alone serves too)."""
    import re
    with open(source) as f:
        text = f.read()
    text, n = re.subn(r'(?m)^define\s+BBCFS\s+0\b', 'define    BBCFS 3', text)
    assert n == 1, source
    if page:
        text, n = re.subn(r'(?m)^define\s+ADFS\s+0\b', 'define    ADFS 1', text)
        assert n == 1, source
    with open(path, 'w') as f:
        f.write(text)
    return path


def board(fs, number=None):
    """The BBC under --bbc-fs fs ('dfs', 'adfs' or 'host'), PAGE at $1F00 under ADFS; with number,
    OSARGS gives it for the filing system (--bbc-fs-number)."""
    b = boards.BOARDS['bbc']
    options = ('--bbc-fs', fs) + (('--bbc-page', '1F00') if fs == 'adfs' else ())
    if number is not None:
        options += ('--bbc-fs-number', str(number))
    return dataclasses.replace(b, options=b.options + options)


# ---- Names ------------------------------------------------------------------------------------

class Names(unittest.TestCase):
    NAMES = ('expr.lth', './err.lo', 'EXPR.LTH', 'asmblock.lth', 'abcdefghijk.lth', 'prog.map',
             'LATHE1.BIN', 'gen.txt', 'a.', 'a.abcdefghijk', 'HELLO', '1/expr.lo', '2/expr.lo',
             '3/IMAGE', 'lib/k.li', '.lth', 'a.b.lth', 'ABCDEFGHIJKLM', 'ABCDEFGHIJKLMNOPQRSTUVWXY')

    def test_4_is_the_dfs_and_8_adfs(self):
        for name in self.NAMES:
            with self.subTest(name=name):
                self.assertEqual(bbcfs.asked_name(name, 4), bbcfs.dfs_name(name))
                self.assertEqual(bbcfs.asked_name(name, 8), bbcfs.adfs_name(name))

    def test_any_other_number_is_the_name_as_given(self):
        for number in OTHER_NUMBERS:
            for name in self.NAMES:
                with self.subTest(number=number, name=name):
                    self.assertEqual(bbcfs.asked_name(name, number), name)

    def test_where_the_emulator_keeps_a_file(self):
        self.assertEqual(bbcfs.asked_host_file('./expr.lo', 4), 'O.EXPR')
        self.assertEqual(bbcfs.asked_host_file('1/expr.lo', 4), ':1/O.EXPR')
        self.assertEqual(bbcfs.asked_host_file('1/expr.lo', 8), ':1/lo/expr')
        self.assertEqual(bbcfs.asked_host_file('HELLO', 4), '$.HELLO')
        self.assertEqual(bbcfs.asked_host_file('HELLO', 8), 'HELLO')
        self.assertEqual(bbcfs.asked_host_file('./expr.lo', 5), 'expr.lo')
        self.assertEqual(bbcfs.asked_host_file('1/expr.lo', 5), '1/expr.lo')


# ---- map() and cdir() on the BBC --------------------------------------------------------------

def emulated(fs, number=None):
    """The number OSARGS gives under --bbc-fs fs, with --bbc-fs-number number if given."""
    if number is not None:
        return number
    return bbcfs.ADFS_NUMBER if fs == 'adfs' else bbcfs.DFS_NUMBER


def run_program(fs, image, disk, args, number=None):
    """Runs the program file image (with its IMAGE.inf) by `*RUN NAME ARGS` under --bbc-fs fs
    (with --bbc-fs-number number), the file kept in disk where that filing system finds NAME:
    (status, output, what the MOS said, cycles)."""
    import subprocess
    name = boards.bbc_name(image)
    path = os.path.join(disk, bbcfs.asked_host_file(name, emulated(fs, number)))
    with open(image + '.inf') as fh:
        load = int(fh.read().split()[1], 16)
    shutil.copyfile(image, path)
    with open(path + '.inf', 'w') as fh:
        fh.write(boards.inf_text(('$.' if fs == 'dfs' else '') + name, load, os.path.getsize(image)))
    b = board(fs, number)
    cmd = ([boards.EMULATOR, '--machine', b.machine] + list(boards.FILL)
           + [o.format(disk=os.path.abspath(disk)) for o in b.options]
           + ['--bbc-command', boards.bbc_command(name, args), '--cycle-cap', str(b.cycle_cap), '--exit-report'])
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, input=b'')
    finally:
        os.unlink(path)
        os.unlink(path + '.inf')
    status, said, cycles = boards.bbc_status(r.returncode, r.stderr.decode('latin-1'))
    return status, boards.bbc_output(r.stdout), said, cycles


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class Map(unittest.TestCase):
    """bbcfs.map() itself, on the BBC with BBCFS 3: test_bbc_adfs's program prints what map()
    makes of each argument, then the *CDIR command cdir() makes of it and the name again()
    writes back; the same program under each filing system."""

    NAMES = ['expr.lth', 'expr.lo', './err.lo', '././err.li', 'EXPR.LTH', 'Expr.Lth', 'asmblock.lth',
             'kerneltest.lo', 'abcdefghijk.lth', 'prog.map', 'bbc.env', 'LATHE1.BIN', 'gen.txt',
             'a.lthx', 'a.', 'a.abcdefghij', 'a.abcdefghijk', 'HELLO', 'LOADMOD', '1/expr.lo',
             './1/x.li', '0/a.lth', '1/IMAGE', '2/x.lo', '3/IMAGE', '4/x.lo', 'lib/k.li', 'a/b',
             '.lth', 'a.b.lth', 'ABCDEFGHIJKL', 'ABCDEFGHIJKLM', 'ABCDEFGHIJKLMNOPQRSTUVWX',
             'ABCDEFGHIJKLMNOPQRSTUVWXY', 'z_9.lth', 'abcdefghijklmnop.lo']

    @classmethod
    def setUpClass(cls):
        import test_bbc_adfs
        cls.dir = tempfile.mkdtemp(prefix='lathe-bbcfs-asked-')
        src = os.path.join(cls.dir, 'mapnames.lth')
        with open(src, 'w') as f:
            f.write(test_bbc_adfs.MAP_SOURCE)
        env = asked_env(os.path.join(LATHE, 'env', 'bbc.env'), os.path.join(cls.dir, 'bbc-asked.env'))
        cls.image = os.path.join(cls.dir, 'MAPNAME')        # seven characters, for the DFS
        build.build(src, cls.image, env=env, keep=os.path.join(cls.dir, 'work'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def check(self, fs, number=None):
        disk = tempfile.mkdtemp(dir=self.dir)
        names = list(self.NAMES)
        n = emulated(fs, number)
        while names:
            chunk = []
            while names and len(' '.join(chunk + [names[0]])) < 200:
                chunk.append(names.pop(0))
            status, out, err, cycles = run_program(fs, self.image, disk, chunk, number)
            self.assertEqual((status, err), (0, b''))
            want = ''
            for name in chunk:
                a = bbcfs.asked_name(name, n) or ''
                want += a + ' '
                if n == bbcfs.ADFS_NUMBER and a and bbcfs.adfs_directory(a):
                    want += 'CDIR ' + bbcfs.adfs_directory(a) + ' ' + a
                want += '\n'
            self.assertEqual(out.decode('latin-1'), want)

    def test_under_the_dfs_the_dfss_names(self):
        self.check('dfs')

    def test_under_adfs_adfss_names_and_directories(self):
        self.check('adfs')

    def test_under_any_other_filing_system_the_names_as_given(self):
        for number in OTHER_NUMBERS:
            with self.subTest(number=number):
                self.check('host', number)


# ---- One image for both -----------------------------------------------------------------------

BANKS = 8                       # the 128 KB module, scheme direct8
JUDGED = os.path.join(HERE, 'lk_judged.py')


def build_image(out_dir, banks=BANKS, page=True):
    """The module image of both tools built with BBCFS 3 (and ADFS 1 with page) in out_dir/MODULE,
    the banks in use alone in MODULE.disc, LOADMOD beside it; of eight banks, the compiler's from
    bank 0 and the linker's after it, or of sixteen, from bank 1. Each tool is linked by
    lk_judged.py, which links as link.py does and notes each bank as the linker judges it.
    Returns (image, [(command, resident, ROM environment, map, the judged notes' file)])."""
    import bbcrom
    tools = []
    first = 0 if banks == 8 else 1
    for command, source, env in (('LATHE', 'lathec.lth', COMPILER_ENV), ('LLINK', 'link.lth', LINKER_ENV)):
        d = os.path.join(out_dir, command.lower())
        os.makedirs(d)
        dev = asked_env(env, os.path.join(d, 'dev.env'), page)
        rom = os.path.join(d, os.path.basename(env))
        first = bbcrom.rom_env(dev, rom, first, banks)
        resident = os.path.join(d, command)
        notes = os.path.join(d, 'judged')
        saved, os.environ['LK_JUDGED_OUT'] = build.LINKER, notes
        build.LINKER = JUDGED
        try:
            build.build(os.path.join(LATHE, 'src', source), resident, env=rom, keep=os.path.join(d, 'work'))
        finally:
            build.LINKER = saved
            del os.environ['LK_JUDGED_OUT']
        tools.append((command, resident, rom, os.path.join(d, 'work', os.path.splitext(source)[0] + '.map'), notes))
    image = os.path.join(out_dir, 'MODULE')
    bbcrom.image([t[:4] for t in tools], image, os.path.join(out_dir, 'listing'), short=image + '.disc',
                 banks=banks)
    bbcrom.loader(os.path.join(out_dir, 'LOADMOD'), 0x1F00 if page else 0x1900)
    return image, tools


def account(tools):
    """test_bbc_rom128's account of the eight-bank image the tools make."""
    import test_bbc_rom128
    return test_bbc_rom128.Account([t[:4] + (None, test_bbc_rom128.read_judged(t[4])) for t in tools])


def case_for(fs, case, work):
    """The program's own build for the filing system: test_bbc_dfs's (BBCFS 1), test_bbc_adfs's
    (BBCFS 2 and ADFS 1), or bbc.env's, the names as given."""
    import test_bbc_adfs
    import test_bbc_dfs
    if fs == 'dfs':
        return test_bbc_dfs.dfs_case(case, work)
    if fs == 'adfs':
        return test_bbc_adfs.adfs_case(case, work)
    return case


def to_disc(fs, disk):
    """Move the files of disk, named as the host's tools name them, to where the filing system
    keeps the files bbcfs maps those names to."""
    import test_bbc_adfs
    import test_bbc_dfs
    if fs == 'dfs':
        test_bbc_dfs.to_dfs(disk)
    elif fs == 'adfs':
        test_bbc_adfs.to_adfs(disk)


def run_image(image, disk, lines, fs, number=None):
    """The * commands on the B+128 with the eight-bank image in the module, under --bbc-fs fs
    (with --bbc-fs-number number), in disk, memory filled with bytes that are not 0: (status,
    output, what the MOS said, {file: bytes} written or changed)."""
    import bbcrom
    import test_bbc_dfs
    before = test_bbc_dfs.files_of(disk)
    command, _, tail = lines[-1].partition(' ')
    code, out, err, cycles = boards.run_module(board(fs, number), image, disk, command, tail=tail,
                                               before=lines[:-1], raw=True, cap=CAP,
                                               scheme=bbcrom.SCHEMES[BANKS])
    status, said, cycles = boards.bbc_status(code, err.decode('latin-1'))
    written = {f: d for f, d in test_bbc_dfs.files_of(disk).items() if f not in before or before[f] != d}
    return status, boards.bbc_output(out), said, written


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class OneImage(unittest.TestCase):
    """The 128 KB image of both tools built with BBCFS 3 and ADFS 1: under the DFS and under
    ADFS the same image compiles each module of a program (its own and the run-time modules),
    links them and runs the result, every file written the host tools' under the name that
    filing system gives it; under a filing system that is neither, with the names as given."""
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-bbc-asked-fs-')
        cls.image, cls.tools = build_image(os.path.join(cls.dir, 'image'))
        cls.account = account(cls.tools)
        if REPORT:
            print('\nBBCFS 3, ADFS 1:\n' + cls.account.text())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_the_image_fits_with_the_compiler_in_banks_0_to_4_and_the_linker_in_5_to_7(self):
        self.assertTrue(self.account.fits(), self.account.summary())
        self.assertEqual({r[0] for n, r in self.account.rows.items() if n < 5}, {'LATHE'})
        self.assertEqual({r[0] for n, r in self.account.rows.items() if n >= 5}, {'LLINK'})

    def test_both_tools_fit_main_ram_at_adfs_page(self):
        """test_bbc_adfs's check of the ROM forms at $1F00: the code below the split, the
        variables below HIMEM, and what is free."""
        import mapenv
        import test_bbc_adfs
        for command, resident, rom, map_path, notes in self.tools:
            env = mapenv.read_env(rom)
            self.assertEqual(env.code[0], test_bbc_adfs.PAGE)
            code_end, lo, hi, more, free = test_bbc_adfs.room(map_path)
            self.assertLessEqual(code_end, env.code[1] + 1, command)
            self.assertGreaterEqual(lo, env.data[0], command)
            self.assertLessEqual(hi, test_bbc_adfs.HIMEM, command)
            self.assertGreaterEqual(free, 0, command)
            if REPORT:
                print('\n%s, eight-bank ROM form: code $1F00-$%04X, variables $%04X-$%04X and $0401-$%04X: '
                      '%d bytes free' % (command, code_end - 1, lo, hi - 1, more - 1, free))

    def programs(self):
        """hello, and longname: two modules of the program, one whose name is longer than ADFS's
        ten characters (averylongone: AVERYLO on the DFS, averylongo on ADFS)."""
        import test_bbc_dfs
        import test_bbc_toolchain as toolchain
        hello = [c for c in toolchain.corpus() if c[0] == 'hello'][0]
        d = os.path.join(self.dir, 'long-src')
        if not os.path.isdir(d):
            os.makedirs(d)
            for n in ('longname.lth', 'averylongone.lth'):
                with open(os.path.join(d, n), 'w') as f:
                    f.write(test_bbc_dfs.LONG[n])
        with open(os.path.splitext(hello[1])[0] + '.expected.out', 'rb') as f:
            expected = f.read()
        return [(hello, expected), (('longname', os.path.join(d, 'longname.lth'), None, [], False), b'1\n')]

    def chain(self, fs, number=None):
        import test_bbc_toolchain as toolchain
        n = emulated(fs, number)
        for case, expected in self.programs():
            name = case[0]
            with self.subTest(program=name):
                work = os.path.join(self.dir, '%s-%s-%d' % (name, fs, n))
                os.makedirs(work)
                disk, compiles, link, files, said, load = toolchain.prepare(case_for(fs, case, work),
                                                                             os.path.join(work, 'w'))
                self.assertEqual(said, [(0, b'')] * len(said))
                self.assertGreaterEqual(len(compiles), 4)     # its modules and the run-time modules
                to_disc(fs, disk)
                lines = toolchain.bbc_lines(compiles, link, load, len(files[link[2]]))
                status, out, mos, written = run_image(self.image, disk, lines, fs, number)
                self.assertEqual((status, mos), (0, b''), out)
                self.assertEqual(out, expected)
                want = {bbcfs.asked_host_file(f, n): data for f, data in files.items()}
                self.assertEqual(sorted(written), sorted(want))
                for f in want:
                    self.assertTrue(written[f] == want[f], f + ' differs')

    def test_under_the_dfs(self):
        self.chain('dfs')

    def test_under_adfs(self):
        self.chain('adfs')

    def test_under_a_filing_system_that_is_neither_the_names_as_given(self):
        self.chain('host', UNKNOWN)
