"""ADFS on the BBC (lathe/docs/bbc.md, "ADFS"): with `define BBCFS 2` the BBC's build of a program
gives every name it opens to lathe/rt/bbc/bbcfs.lth's map(), which makes ADFS's name of it
(expr.lth is lth.expr), and open_out makes a directory that is not there; with `define ADFS 1`
the tools' and the programs' main RAM starts at ADFS's PAGE, $1F00. The emulator's --bbc-fs adfs
takes only ADFS's names, ten files open, 47 entries a directory and an L disc of 2,560 sectors a
drive, and --bbc-page 1F00 makes a write below PAGE a fault (--bbc-strict).

- Names: the host's twin (lathe/host/driver/bbcfs.py) on the rules; which modules' names are
  longer than ten characters; the tools' own modules map apart.
- Map: map() and cdir() on the BBC give the twin's names.
- Room: what each tool has free in main RAM at ADFS's PAGE, in both forms.
- The tool chain under --bbc-fs adfs: a small program compiled, linked and run on a blank disc
  (the directories made as the files are written); with LATHE_BBC_ADFS=1 every program of the
  corpus; with LATHE_BBC_SELFHOST=1 the compiler's self-compile; with LATHE_BBC_ADFS_LOOP=1 the
  compiler rebuilt on two ADFS discs. LATHE_BBC_ADFS_REPORT=1 prints what each holds.
"""
import os
import re
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
import mapenv  # noqa: E402

LATHE = os.path.join(ROOT, 'lathe')
HAVE_TOOLS = os.path.isfile(boards.EMULATOR) and os.path.isfile(build.COMPILER)
ALL = os.environ.get('LATHE_BBC_ADFS') == '1'
SELFHOST = os.environ.get('LATHE_BBC_SELFHOST') == '1'
LOOP = os.environ.get('LATHE_BBC_ADFS_LOOP') == '1'
REPORT = os.environ.get('LATHE_BBC_ADFS_REPORT') == '1'
COMPILER_ENV = os.path.join(LATHE, 'src', 'lathec-bbc.env')
LINKER_ENV = os.path.join(LATHE, 'src', 'linker-bbc.env')
PAGE = 0x1F00                   # ADFS's PAGE with the DFS beside it (emulator/NOTES-bbcbplus.md)
HIMEM = 0x7C00
MORE = (0x0401, 0x06FF)         # `more data`
CAP = 4_000_000_000
SECTORS = 2560                  # an L disc
ADFS_RE = re.compile(r'adfs: most-open=(\d+)\s+most-writing=(\d+)\s+most-entries=(\d+)((?:\s+drive\d=\d+/\d+/\d+)*)')
DRIVE_RE = re.compile(r'drive(\d)=(\d+)/(\d+)/(\d+)')


def board():
    """The BBC under --bbc-fs adfs with PAGE at $1F00."""
    import dataclasses
    b = boards.BOARDS['bbc']
    return dataclasses.replace(b, options=b.options + ('--bbc-fs', 'adfs', '--bbc-page', '%X' % PAGE))


def adfs_env(source, path, page=True):
    """Write to path the environment source with `define BBCFS 2` and, with page, `define ADFS
    1`: the same build, ADFS's names, main RAM from ADFS's PAGE."""
    with open(source) as f:
        text = f.read()
    text, n = re.subn(r'(?m)^define\s+BBCFS\s+0\b', 'define    BBCFS 2', text)
    assert n == 1, source
    if page:
        text, n = re.subn(r'(?m)^define\s+ADFS\s+0\b', 'define    ADFS 1', text)
        assert n == 1, source
    with open(path, 'w') as f:
        f.write(text)
    return path


def room(map_path, page=PAGE):
    """What a tool's map places in main RAM: (code end, variables' start, variables' end, more
    data's end, bytes free of PAGE-HIMEM and $0401-$06FF). The code is the fixed functions,
    constants and stubs from PAGE; free counts what lies between the code and the variables."""
    import test_bbc_selfhost as selfhost
    fixed = [i for i in selfhost.read_map(map_path) if i[4] is None]
    code = [i for i in fixed if i[0] in 'FTD' and 0x0800 <= i[1] < 0x8000]
    data = [i for i in fixed if i[0] in 'VS' and 0x0800 <= i[1] < 0x8000]
    more = [i for i in fixed if i[0] in 'VS' and 0x0400 <= i[1] < 0x0800]
    code_end = max(i[1] + i[2] for i in code)
    data_lo = min(i[1] for i in data)
    data_end = max(i[1] + i[2] for i in data)
    more_end = max(i[1] + i[2] for i in more) if more else MORE[0]
    used = (code_end - page) + (data_end - data_lo) + (more_end - MORE[0])
    return code_end, data_lo, data_end, more_end, (HIMEM - page) + (MORE[1] + 1 - MORE[0]) - used


def board_ram():
    """board(), the module's RAM form holding the image from power on: as if LOADMOD had filled
    it from a disc of its own before the session (Toolchain.test_loadmod_at_adfs_page runs
    LOADMOD itself)."""
    import dataclasses
    b = board()
    return dataclasses.replace(b, options=b.options + ('--bbc-module-ram',))


# ---- The disc as --bbc-fs adfs keeps it -------------------------------------------------------

def files_of(disk):
    """{path relative to disk: bytes} of every file in disk and its subdirectories, but the .inf
    files."""
    import test_bbc_dfs
    return test_bbc_dfs.files_of(disk)


def to_adfs(disk):
    """Move every file of disk, named as the host's tools name them (in disk or in a drive's
    subdirectory 0/ or 1/), to where --bbc-fs adfs keeps the file bbcfs maps that name to."""
    for top in ('', '0', '1'):
        d = os.path.join(disk, top)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if os.path.isfile(os.path.join(d, f)):
                dst = bbcfs.adfs_host_path(disk, (top + '/' if top else '') + f)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                os.rename(os.path.join(d, f), dst)
        if top and not os.listdir(d):
            os.rmdir(d)


def put(disk, name, data):
    """A file the BBC reads as `name` (a name as the tools give it), in disk as --bbc-fs adfs
    keeps it."""
    path = bbcfs.adfs_host_path(disk, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)
    return path


def catalogue(disk):
    """{drive: (files, bytes, sectors, most entries in a directory)} of what disk holds, as ADFS
    counts it: the map and the root 7 sectors, a directory 5, a file its length in whole sectors."""
    drives = {}
    for drive, top in ((0, disk), (1, os.path.join(disk, ':1'))):
        if not os.path.isdir(top):
            continue
        files = size = 0
        sectors, most = 7, 0
        for d, dirs, names in os.walk(top):
            if d == disk:
                dirs[:] = [x for x in dirs if x != ':1']
            entries = [n for n in names if not n.endswith('.inf')] + dirs
            most = max(most, len(entries))
            sectors += 5 * len(dirs)
            for n in names:
                if not n.endswith('.inf'):
                    files += 1
                    s = os.path.getsize(os.path.join(d, n))
                    size += s
                    sectors += (s + 255) // 256
        drives[drive] = (files, size, sectors, most)
    return drives


def run_adfs(module, disk, lines, ram=False):
    """Runs the * commands on the BBC under --bbc-fs adfs, PAGE $1F00, with the module image (None:
    the RAM form, empty at power on; else in
    its RAM form with ram), in disk, on memory filled with bytes that are not 0: (status,
    output, what the MOS said, {file: bytes} written or changed, CPU cycles, the emulator's adfs
    report: (most open, most writing, most entries, {drive: (sectors in use, most in use, of)}))."""
    before = files_of(disk)
    command, _, tail = lines[-1].partition(' ')
    empty = module is None              # the RAM form, empty at power on
    code, out, err, cycles = boards.run_module(board_ram() if ram and not empty else board(), module, disk,
                                               command, tail=tail, before=lines[:-1], raw=True, cap=CAP,
                                               ram=empty)
    text = err.decode('latin-1')
    status, said, cycles = boards.bbc_status(code, text)
    m = ADFS_RE.findall(text)
    report = (0, 0, 0, {})
    if m:
        report = (int(m[-1][0]), int(m[-1][1]), int(m[-1][2]),
                  {int(d): (int(a), int(b), int(c)) for d, a, b, c in DRIVE_RE.findall(m[-1][3])})
    written = {f: d for f, d in files_of(disk).items() if f not in before or before[f] != d}
    return status, boards.bbc_output(out), said, written, cycles, report


def build_image(out_dir, page=True, banks=16):
    """The module image of both tools built with BBCFS 2 and ADFS 1 in out_dir/MODULE (and the
    banks in use alone in MODULE.disc), with LOADMOD for $1F00 beside it; of sixteen banks, the
    tools' from bank 1, or of eight (the 128 KB module, scheme direct8), the compiler's from bank
    0. Returns (image, {tool: (its developer's environment, its ROM environment, its map)})."""
    import bbcrom
    tools, envs = [], {}
    first = 1 if banks == 16 else 0
    for command, source, env in (('LATHE', 'lathec.lth', COMPILER_ENV), ('LLINK', 'link.lth', LINKER_ENV)):
        d = os.path.join(out_dir, command.lower())
        os.makedirs(d)
        dev = adfs_env(env, os.path.join(d, 'dev.env'), page)
        rom = os.path.join(d, os.path.basename(env))
        first = bbcrom.rom_env(dev, rom, first, banks)
        resident = os.path.join(d, command)
        build.build(os.path.join(LATHE, 'src', source), resident, env=rom, keep=os.path.join(d, 'work'))
        m = os.path.join(d, 'work', os.path.splitext(source)[0] + '.map')
        tools.append((command, resident, rom, m))
        envs[command] = (dev, rom, m)
    image = os.path.join(out_dir, 'MODULE')
    bbcrom.image(tools, image, os.path.join(out_dir, 'listing'), short=image + '.disc', banks=banks)
    bbcrom.loader(os.path.join(out_dir, 'LOADMOD'), PAGE if page else 0x1900)
    return image, envs


def adfs_case(case, work):
    """test_bbc_toolchain's case with ADFS's names and PAGE: bbc.env, or a banked one made from
    bbc-bank.env, with BBCFS 2 and ADFS 1."""
    import test_bbc_bank
    name, source, make_env, extra, banked = case
    if banked:
        base = adfs_env(test_bbc_bank.BANK_ENV, os.path.join(work, 'bbc-bank-adfs.env'))
        lines = {'farcall': test_bbc_bank.FARCALL, 'bankdata': test_bbc_bank.BANKDATA,
                 'regions': test_bbc_bank.REGIONS}[name]
        make_env = (lambda path: test_bbc_bank.bank_env(path, lines, base=base, ports=0))
    else:
        make_env = (lambda path: adfs_env(os.path.join(LATHE, 'env', 'bbc.env'), path))
    return (name, source, make_env, extra, banked)


def account(cat, report=None):
    """Lines of text: per drive, files and bytes, sectors against the disc's, and the most
    entries in a directory; with the emulator's report, its count at the end and at most."""
    lines = []
    for d, (n, size, sectors, most) in sorted(cat.items()):
        used = report[3].get(d) if report else None
        lines.append('drive %d: %d files, %d bytes; %d sectors of %d (%d free, %d bytes)%s; at most %d '
                     'entries in a directory' % (
                         d, n, size, sectors, SECTORS, SECTORS - sectors, (SECTORS - sectors) * 256,
                         '; the emulator: %d at the end, %d at most' % used[:2] if used else '', most))
    return lines


# ---- Names ------------------------------------------------------------------------------------

# The modules of lathe/src, lathe/rt and lathe/rt/bbc whose names are longer than ten characters:
# none is a module of the tools. Cut to ten on ADFS, they still map apart.
LONGER_THAN_TEN = []


class Names(unittest.TestCase):
    def test_the_rules(self):
        for name, adfs in (('expr.lth', 'lth.expr'), ('expr.lo', 'lo.expr'), ('expr.li', 'li.expr'),
                           ('./err.lo', 'lo.err'), ('././err.li', 'li.err'), ('EXPR.LTH', 'LTH.EXPR'),
                           ('asmblock.lth', 'lth.asmblock'), ('kerneltest.lo', 'lo.kerneltest'),
                           ('inlinetest.lth', 'lth.inlinetest'), ('abcdefghijk.lth', 'lth.abcdefghij'),
                           ('prog.map', 'map.prog'), ('bbc.env', 'env.bbc'), ('LATHE1.BIN', 'BIN.LATHE1'),
                           ('gen.txt', 'txt.gen'), ('a.abcdefghij', 'abcdefghij.a'), ('a.abcdefghijk', None),
                           ('HELLO', 'HELLO'), ('LOADMOD', 'LOADMOD'), ('1/expr.lo', ':1.lo.expr'),
                           ('./1/x.li', ':1.li.x'), ('0/a.lth', ':0.lth.a'), ('1/IMAGE', ':1.IMAGE'),
                           ('2/x.lo', None), ('3/x.lo', None), ('lib/k.li', None), ('a/b', None),
                           ('.lth', None), ('a.', None), ('a.b.lth', None),
                           ('ABCDEFGHIJKLMNOPQRSTUVWX', 'ABCDEFGHIJKLMNOPQRSTUVWX'),
                           ('ABCDEFGHIJKLMNOPQRSTUVWXY', None)):
            with self.subTest(name=name):
                self.assertEqual(bbcfs.adfs_name(name), adfs)

    def test_directories_and_where_the_emulator_keeps_a_file(self):
        self.assertEqual(bbcfs.adfs_directory('lth.expr'), 'lth')
        self.assertEqual(bbcfs.adfs_directory(':1.lo.x'), ':1.lo')
        self.assertIsNone(bbcfs.adfs_directory(':1.IMAGE'))
        self.assertIsNone(bbcfs.adfs_directory('HELLO'))
        self.assertEqual(bbcfs.adfs_host_file('lth.expr'), 'lth/expr')
        self.assertEqual(bbcfs.adfs_host_file(':0.lth.a'), 'lth/a')
        self.assertEqual(bbcfs.adfs_host_file(':1.li.x'), ':1/li/x')
        self.assertEqual(bbcfs.adfs_host_file('HELLO'), 'HELLO')

    def test_long_names(self):
        """Every module of the tools fits ten characters, so its files keep its whole name;
        the longer names of lathe/src and lathe/rt are cut to ten and still map apart."""
        tools = set()
        for source in ('lathec.lth', 'link.lth'):
            tools |= {n for n, _ in build.module_order(os.path.join(LATHE, 'src', source))}
        self.assertGreater(len(tools), 40)
        self.assertEqual(sorted(t for t in tools if len(t) > 10), [])
        stems = set()
        for d in ('src', 'rt', os.path.join('rt', 'bbc')):
            stems |= {os.path.splitext(f)[0] for f in os.listdir(os.path.join(LATHE, d)) if f.endswith('.lth')}
        self.assertEqual(sorted(s for s in stems if len(s) > 10), LONGER_THAN_TEN)
        seen = {}
        for stem in sorted(stems):
            seen.setdefault(bbcfs.adfs_name(stem + '.lth').lower(), []).append(stem)
        self.assertEqual({k: v for k, v in seen.items() if len(v) > 1}, {})


# ---- map() and cdir() on the BBC --------------------------------------------------------------

MAP_SOURCE = '''
module mapnames
import bbc
import bbcfs
var buf: [128]byte
func show()
  var i: byte
  i = 0
  while buf[i] != 13 do
    bbc.put_byte(buf[i])
    i += 1
  end
end
pub func main()
  var a: byte
  var i: byte
  var p: ^byte
  for a = 0 until bbc.argc() do
    p = bbc.argv(a)
    i = 0
    while p[i] != 0 do
      buf[i] = p[i]
      i += 1
    end
    buf[i] = 0
    bbcfs.map(@buf)
    show()
    bbc.put_byte(' ')
    if bbcfs.cdir(@buf) then
      show()
      bbcfs.again(@buf)
      bbc.put_byte(' ')
      show()
    end
    bbc.put_byte(10)
  end
end
'''


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class Map(unittest.TestCase):
    """bbcfs.map() itself, on the BBC with BBCFS 2: a program prints what it makes of each
    argument, then the *CDIR command cdir() makes of it and the name again() writes back."""

    NAMES = ['expr.lth', 'expr.lo', './err.lo', '././err.li', 'EXPR.LTH', 'asmblock.lth',
             'kerneltest.lo', 'abcdefghijk.lth', 'prog.map', 'bbc.env', 'LATHE1.BIN', 'gen.txt',
             'a.abcdefghij', 'a.abcdefghijk', 'HELLO', 'LOADMOD', '1/expr.lo', './1/x.li', '0/a.lth',
             '1/IMAGE', '2/x.lo', 'lib/k.li', 'a/b', '.lth', 'a.', 'a.b.lth',
             'ABCDEFGHIJKLMNOPQRSTUVWX', 'ABCDEFGHIJKLMNOPQRSTUVWXY', 'z_9.lth']

    def test_map_gives_the_twins_names(self):
        with tempfile.TemporaryDirectory(prefix='lathe-bbcfs-adfs-') as d:
            src = os.path.join(d, 'mapnames.lth')
            with open(src, 'w') as f:
                f.write(MAP_SOURCE)
            env = adfs_env(os.path.join(LATHE, 'env', 'bbc.env'), os.path.join(d, 'bbc-adfs.env'))
            image = os.path.join(d, 'mapnames')
            build.build(src, image, env=env, keep=os.path.join(d, 'work'))
            with open(image + '.inf') as f:
                self.assertEqual(int(f.read().split()[1], 16), PAGE)
            disk = os.path.join(d, 'disk')
            os.makedirs(disk)
            names = list(self.NAMES)
            while names:
                chunk = []
                while names and len(' '.join(chunk + [names[0]])) < 200:
                    chunk.append(names.pop(0))
                status, out, err, cycles = boards.run_mos(board(), image, disk, chunk)
                self.assertEqual((status, err), (0, b''))
                want = ''
                for n in chunk:
                    a = bbcfs.adfs_name(n) or ''
                    want += a + ' '
                    if a and bbcfs.adfs_directory(a):
                        want += 'CDIR ' + bbcfs.adfs_directory(a) + ' ' + a
                    want += '\n'
                self.assertEqual(out.decode('latin-1'), want)


# ---- The tool chain under --bbc-fs adfs -------------------------------------------------------

QUICK = ('hello',)
BANKED_QUICK = ()
# The programs of the chain that do not fit from ADFS's PAGE, 1,536 bytes less of main RAM.
NOT_AT_ADFS_PAGE = {'for_ranges': 'its code ends at $68E7 from $1900, 743 bytes past $6BFF from $1F00 '
                                  '(link error 27); bbc.env keeps its 4 KB data range, which '
                                  'bigarray_pages needs'}


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class Toolchain(unittest.TestCase):
    """The program's modules compiled by *LATHE, linked by *LLINK and run by *RUN on the B+128
    with --bbc-fs adfs at PAGE $1F00, the tools built with BBCFS 2 and ADFS 1: every file the BBC
    reads and writes has its ADFS name, each written is byte for byte the host's file of the name
    it maps, and the directories the tools write into are made as they are needed."""
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-bbc-adfs-')
        cls.module, cls.envs = build_image(os.path.join(cls.dir, 'image'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_both_tools_fit_at_adfs_page(self):
        """The ROM forms linked from $1F00 (the developer's forms: DeveloperForms): the code
        below the split, the variables below HIMEM, and what is free."""
        for tool, (dev, rom, m) in sorted(self.envs.items()):
            env = mapenv.read_env(rom)
            self.assertEqual(env.code[0], PAGE)
            code_end, lo, hi, more, free = room(m)
            self.assertLessEqual(code_end, env.code[1] + 1, tool)
            self.assertGreaterEqual(lo, env.data[0], tool)
            self.assertLessEqual(hi, HIMEM, tool)
            self.assertGreaterEqual(free, 0, tool)
            if REPORT:
                print('\n%s, ROM form: code $%04X-$%04X, variables $%04X-$%04X and $0401-$%04X: %d bytes free'
                      % (tool, PAGE, code_end - 1, lo, hi - 1, more - 1, free))

    def chain(self, case, drive=None, ram=False, before=()):
        """Compile, link and run the case under ADFS's names, on a disc that holds its sources
        (in lth), its environment (in env) and nothing else: (output, {host file: bytes} written,
        the emulator's report, the disc's catalogue at the end, the compiles' arguments, the
        link's). With drive '1', the objects and interfaces are on drive 1. With ram, the tools
        run from the module's RAM form."""
        import test_bbc_dfs
        import test_bbc_toolchain as toolchain
        name, source, _, _, banked = case
        work = os.path.join(self.dir, name + ('-ram' if ram else '') + ('-' + drive if drive else ''))
        os.makedirs(work)
        disk, compiles, link, files, said, load = toolchain.prepare(adfs_case(case, work), os.path.join(work, 'w'))
        self.assertEqual(said, [(0, b'')] * len(said))
        self.assertEqual(load, PAGE)
        if drive:
            compiles = [c[:-1] + [drive] for c in compiles]
            link = link[:4] + [drive + '/' + o for o in link[4:]]
            files = test_bbc_dfs.host_run(compiles, link, disk, os.path.join(work, 'host-' + drive), drive)
        to_adfs(disk)
        lines = list(before) + toolchain.bbc_lines(compiles, link, load, len(files[link[2]]))
        status, out, mos, written, cycles, report = run_adfs(self.module, disk, lines, ram=banked or ram)
        self.assertEqual((status, mos), (0, b''), out)
        want = {bbcfs.adfs_host_file(bbcfs.adfs_name(f)): data for f, data in files.items()}
        self.assertEqual(sorted(written), sorted(want))
        for f in want:
            self.assertTrue(written[f] == want[f], f + ' differs')
        return out, written, report, catalogue(disk), compiles, link

    def test_a_program_on_a_blank_disc(self):
        """hello on a disc that has only its sources and its environment: the compiler makes lo
        and li as it writes the first object and interface, the linker map; two files open at
        most, one written."""
        import test_bbc_toolchain as toolchain
        for case in toolchain.corpus():
            name, source, _, _, banked = case
            if not (ALL or name in (BANKED_QUICK if banked else QUICK)) or name in NOT_AT_ADFS_PAGE:
                continue
            with self.subTest(program=name):
                out, written, report, cat, compiles, link = self.chain(case, '1' if banked else None)
                with open(os.path.splitext(source)[0] + '.expected.out', 'rb') as f:
                    self.assertEqual(out, f.read())
                self.assertIn('map/' + link[2], written)          # the map: IMAGE.map
                self.assertEqual(report[:2], (2, 1))
                for d, (_, _, sectors, _) in cat.items():          # the emulator's count is the disc's
                    self.assertEqual(report[3][d][0], sectors, d)
                if REPORT:
                    print('\n%-10s most open %d, writing %d; %s' % ((name,) + report[:2] + ('; '.join(account(cat, report)),)))

    def test_a_directory_that_cannot_be_made(self):
        """The root holds 47 entries, so *CDIR lo is Dir full: open_out gives 0 and the compiler
        says error 63, as for any output file it cannot create, its text read from the message
        file in the root."""
        import test_bbc_toolchain as toolchain
        import test_msgfile
        case = [c for c in toolchain.corpus() if c[0] == 'hello'][0]
        work = os.path.join(self.dir, 'full')
        os.makedirs(work)
        disk, compiles, link, files, said, load = toolchain.prepare(adfs_case(case, work), os.path.join(work, 'w'))
        to_adfs(disk)
        test_msgfile.put_on(disk, 2)
        n = len(os.listdir(disk))
        for i in range(47 - n):
            with open(os.path.join(disk, 'F%02d' % i), 'wb') as f:
                f.write(b'x')
        status, out, mos, written, cycles, report = run_adfs(self.module, disk, [boards.module_command('LATHE', compiles[0])])
        self.assertNotEqual(status, 0)
        self.assertIn(b'error 63: cannot create the output file', out)
        self.assertEqual(written, {})
        self.assertFalse(os.path.exists(os.path.join(disk, 'lo')))

    def test_loadmod_at_adfs_page(self):
        """LOADMOD assembled for $1F00 (bbcrom.loader) fills the module's RAM form from the short
        image on drive 1 without writing below PAGE (--bbc-strict), and the tools then compile,
        link and run hello."""
        import test_bbc_toolchain as toolchain
        loader = os.path.join(os.path.dirname(self.module), 'LOADMOD')
        with open(loader + '.inf') as f:
            self.assertEqual(int(f.read().split()[1], 16), PAGE)
        case = [c for c in toolchain.corpus() if c[0] == 'hello'][0]
        work = os.path.join(self.dir, 'loadmod')
        os.makedirs(work)
        disk, compiles, link, files, said, load = toolchain.prepare(adfs_case(case, work), os.path.join(work, 'w'))
        to_adfs(disk)
        for name, src in (('1/LOADMOD', loader), ('1/MODULE', self.module + '.disc')):
            with open(src, 'rb') as f:
                path = put(disk, name, f.read())
        with open(bbcfs.adfs_host_path(disk, '1/LOADMOD') + '.inf', 'w') as f:
            f.write(boards.inf_text(':1.LOADMOD', PAGE, os.path.getsize(loader)))
        before = set(files_of(disk))
        lines = ['RUN :1.LOADMOD :1.MODULE'] + toolchain.bbc_lines(compiles, link, load, len(files[link[2]]))
        command, _, tail = lines[-1].partition(' ')
        import dataclasses
        empty = dataclasses.replace(board(), options=board().options + ('--bbc-module-ram',))
        code, out, err, cycles = boards.run_module(empty, None, disk, command, tail=tail, ram=True,
                                                   before=lines[:-1], raw=True, cap=CAP)
        status, said, cycles = boards.bbc_status(code, err.decode('latin-1'))
        self.assertEqual((status, said), (0, b''))
        with open(os.path.splitext(case[1])[0] + '.expected.out', 'rb') as f:
            self.assertEqual(boards.bbc_output(out), f.read())
        written = {f: d for f, d in files_of(disk).items() if f not in before}
        want = {bbcfs.adfs_host_file(bbcfs.adfs_name(f)): data for f, data in files.items()}
        self.assertEqual(sorted(written), sorted(want))
        del path

    @unittest.skipUnless(ALL or REPORT, 'LATHE_BBC_ADFS=1 runs it')
    def test_the_largest_link(self):
        """outtest, compiled by the host and linked on the BBC under ADFS's names: the image, map
        and bank files are the host's."""
        import test_bbc_toolchain as toolchain
        files, link, disk = toolchain.link_alone('outtest', os.path.join(self.dir, 'outtest'))
        for f in os.listdir(disk):
            if not f.endswith(('.lo', '.env')):
                os.unlink(os.path.join(disk, f))
        to_adfs(disk)
        status, out, mos, written, cycles, report = run_adfs(self.module, disk, [boards.module_command('LLINK', link)])
        self.assertEqual((status, out, mos), (0, b'', b''))
        want = {bbcfs.adfs_host_file(bbcfs.adfs_name(f)): d for f, d in files.items() if not f.endswith(('.lo', '.li'))}
        self.assertEqual(sorted(written), sorted(want))
        for f in want:
            self.assertTrue(written[f] == want[f], f + ' differs')
        self.assertEqual(report[:2], (2, 1))
        if REPORT:
            print('\nouttest link: most open %d, writing %d; %s' % (report[:2] + ('; '.join(account(catalogue(disk), report)),)))


SVC_MAIN = '''module svcmain
import svcbank
pub func main()
  svcbank.go()
end
'''

SVC_BANK = '''module svcbank
import bbc
extern func osbyte(code: byte in a, xv: byte in x, yv: byte in y)  at $FFF4
pub func go()
  bbc.put_byte('0' + bbc.open("a/b"))   ; a bad name on every filing system: an error, caught
  bbc.put_byte(10)
  osbyte(143, 9, 0)                     ; *HELP's service call, offered to every marked ROM
  osbyte(143, 4, 0)                     ; an unknown command's
  bbc.put_byte('o')
  bbc.put_byte('k')
  bbc.put_byte(10)
end
'''


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class AfterLoadmod(unittest.TestCase):
    """A user's banked program in the developer's form (`*RUN`, bbc-bank.env, its code in bank 1
    of the module's RAM form) run after `*RUN LOADMOD MODULE`, which entered the module in the
    MOS's table of ROM types: the MOS offers an error (service call 6, before BRKV) and the
    service calls the program makes through OSBYTE 143 (9, *HELP's, and 4, an unknown command's)
    to the ROMs the table marks. Until 2026-11-17 they went to $8003 of the program's bank, which
    has no header: the run did not end well. rt_bbc.start now clears the slot's entry before it
    loads a bank. Under the host's names, the DFS's and ADFS's (each with its PAGE), in the
    sixteen-bank and the eight-bank module."""

    def test_service_calls_after_loadmod_do_not_reach_the_programs_banks(self):
        import bbcrom
        import dataclasses
        import test_bbc_bank
        work = tempfile.mkdtemp(prefix='lathe-bbc-svc-')
        self.addCleanup(shutil.rmtree, work, True)
        src = os.path.join(work, 'src')
        os.makedirs(src)
        for name, text in (('svcmain', SVC_MAIN), ('svcbank', SVC_BANK)):
            with open(os.path.join(src, name + '.lth'), 'w') as f:
                f.write(text)
        hello = os.path.join(LATHE, 'tests', 'cases', 'e2e', 'hello.lth')
        rom = os.path.join(work, 'rom')
        os.makedirs(rom)
        build.build(hello, os.path.join(rom, 'HELLO'), os.path.join(LATHE, 'env', 'bbc-rom.env'),
                    keep=os.path.join(rom, 'work'))
        spec = [('HELLO', os.path.join(rom, 'HELLO'), os.path.join(LATHE, 'env', 'bbc-rom.env'),
                 os.path.join(rom, 'work', 'hello.map'))]
        lines = ['bank      WIN 1 $81 SVC1.BIN', 'place     svcbank WIN 1']
        for fs, n, page in (('host', 0, 0x1900), ('dfs', 1, 0x1900), ('adfs', 2, PAGE)):
            d = os.path.join(work, fs)
            os.makedirs(d)
            env = test_bbc_bank.bank_env(os.path.join(d, 'svc.env'), lines)
            with open(env) as f:
                text = f.read().replace('define    BBCFS 0', 'define    BBCFS %d' % n)
            if fs == 'adfs':
                text = text.replace('define    ADFS 0', 'define    ADFS 1')
            with open(env, 'w') as f:
                f.write(text)
            build.build(os.path.join(src, 'svcmain.lth'), os.path.join(d, 'PROG'), env, keep=os.path.join(d, 'work'))
            for banks in (16, 8):
                with self.subTest(fs=fs, banks=banks):
                    disk = os.path.join(d, 'disk%d' % banks)
                    os.makedirs(disk)
                    image = os.path.join(d, 'MODULE%d' % banks)
                    bbcrom.image(spec, image, banks=banks)
                    bbcrom.loader(os.path.join(d, 'LOADMOD'), page)
                    names = {'PROG': os.path.join(d, 'PROG'), 'SVC1.BIN': os.path.join(d, 'SVC1.BIN'),
                             'LOADMOD': os.path.join(d, 'LOADMOD'), 'MODULE': image}
                    for name, path in names.items():
                        host = {'host': lambda x: os.path.join(disk, x), 'dfs': lambda x: bbcfs.host_path(disk, x),
                                'adfs': lambda x: bbcfs.adfs_host_path(disk, x)}[fs](name)
                        os.makedirs(os.path.dirname(host), exist_ok=True)
                        shutil.copy(path, host)
                        if name in ('PROG', 'LOADMOD'):
                            with open(host + '.inf', 'w') as f:
                                f.write(boards.inf_text(name, page, os.path.getsize(path)))
                    b = boards.BOARDS['bbc']
                    b = dataclasses.replace(b, options=b.options + (() if fs == 'host' else ('--bbc-fs', fs))
                                            + ('--bbc-page', '%X' % page))
                    code, out, err, cycles = boards.run_module(b, None, disk, 'RUN', tail='PROG', ram=True,
                                                               before=['RUN LOADMOD MODULE'], raw=True,
                                                               scheme=bbcrom.SCHEMES[banks], cap=100_000_000)
                    status, said, cycles = boards.bbc_status(code, err.decode('latin-1'))
                    self.assertEqual((status, boards.bbc_output(out), said), (0, b'0\nok\n', b''))


@unittest.skipUnless(HAVE_TOOLS and (ALL or REPORT), 'LATHE_BBC_ADFS=1 runs it')
class DeveloperForms(unittest.TestCase):
    """Both tools in the developer's form (`*RUN`), built with BBCFS 2 and ADFS 1 from
    lathec-bbc.env and linker-bbc.env as committed, start at $1F00 under --bbc-fs adfs (their
    start-up loads their banks through bbc.open and bbcfs.map) and compile and link hello as the
    host's tools do; and what each has free in main RAM."""

    def test_both_tools_start_in_the_developers_form(self):
        import test_bbc_toolchain as toolchain
        work = tempfile.mkdtemp(prefix='lathe-bbc-adfs-dev-')
        self.addCleanup(shutil.rmtree, work, True)
        module, _ = build_image(os.path.join(work, 'image'))
        case = [c for c in toolchain.corpus() if c[0] == 'hello'][0]
        disk, compiles, link, files, said, load = toolchain.prepare(adfs_case(case, os.path.join(work, 'case')),
                                                                     os.path.join(work, 'w'))
        to_adfs(disk)
        for tool, source, env in (('LATHEC', 'lathec.lth', COMPILER_ENV), ('LLINK', 'link.lth', LINKER_ENV)):
            d = os.path.join(work, tool)
            os.makedirs(d)
            dev = adfs_env(env, os.path.join(d, os.path.basename(env)))
            build.build(os.path.join(LATHE, 'src', source), os.path.join(d, tool), env=dev, keep=os.path.join(d, 'work'))
            m = os.path.join(d, 'work', os.path.splitext(source)[0] + '.map')
            code_end, lo, hi, more, free = room(m)
            self.assertLessEqual(code_end, mapenv.read_env(dev).code[1] + 1)
            self.assertGreaterEqual(free, 0)
            if REPORT:
                print('\n%s, developer\'s form: code $%04X-$%04X, variables $%04X-$%04X: %d bytes free'
                      % (tool, PAGE, code_end - 1, lo, hi - 1, free))
            for f in os.listdir(d):
                if f == tool or f.upper().endswith('.BIN'):
                    with open(os.path.join(d, f), 'rb') as fh:
                        put(disk, f, fh.read())
            with open(bbcfs.adfs_host_path(disk, tool) + '.inf', 'w') as fh:
                fh.write(boards.inf_text(tool, PAGE, os.path.getsize(os.path.join(d, tool))))
        lines = [boards.module_command('RUN', ['LATHEC'] + args) for args in compiles]
        lines.append(boards.module_command('RUN', ['LLINK'] + link))
        status, out, mos, written, cycles, report = run_adfs(module, disk, lines, ram=True)
        self.assertEqual((status, out, mos), (0, b'', b''))
        want = {bbcfs.adfs_host_file(bbcfs.adfs_name(f)): data for f, data in files.items()}
        self.assertEqual(sorted(written), sorted(want))
        for f in want:
            self.assertTrue(written[f] == want[f], f + ' differs')
        # With the module's RAM holding the image, as LOADMOD leaves it, the MOS's table said the
        # slot was a ROM, and it offered a filing system's error to the ROMs (service call 6)
        # before BRKV: at $8003 of whatever bank the developer's form had latched, its code (bbc.md,
        # "ADFS", "Faults found"; until 2026-11-17 the second run did not end well). A name that is
        # no name (Bad name) is such an error. Now both runs say error 62, as the host does.
        bad = boards.module_command('RUN', ['LATHEC'] + compiles[0][:-2] + ['2/x.lth', '.'])
        for image in (None, module):
            status, out, mos, written, cycles, report = run_adfs(image, disk, [bad], ram=True)
            self.assertIn(b'error 62', out)


@unittest.skipUnless(HAVE_TOOLS and (SELFHOST or REPORT), 'LATHE_BBC_SELFHOST=1 runs it')
class SelfHost(unittest.TestCase):
    """The compiler built with BBCFS 2 and ADFS 1 compiles each of its own modules on the B+128
    with --bbc-fs adfs, `*LATHE OPTIONS NAME.lth .` on a disc that holds lth.NAME and li.* of the
    host's interfaces of what it imports: status, output and every file written are the host's,
    under their ADFS names."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-bbc-adfs-self-')
        cls.module, _ = build_image(os.path.join(cls.dir, 'image'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_the_compiler_compiles_itself_under_adfs_names(self):
        import memory_report
        import test_src_selfhost as selfhost
        most = (0, 0)
        for name in selfhost.MODULES:
            options = tuple(memory_report.options_of(os.path.join(LATHE, 'src', name + '.lth')))
            disk, host = selfhost.prepare(name, os.path.join(self.dir, 'work-' + name), options)
            to_adfs(disk)
            args = list(options) + [name + '.lth', '.']
            status, out, mos, written, cycles, report = run_adfs(self.module, disk, [boards.module_command('LATHE', args)])
            most = tuple(max(a, b) for a, b in zip(most, report[:2]))
            if REPORT:
                print('\n%-9s most open %d, writing %d, %d cycles; %s' % (
                    (name,) + report[:2] + (cycles, '; '.join(account(catalogue(disk), report)))), end='')
            with self.subTest(module=name):
                self.assertEqual((status, out, mos), (host[0], host[1] + host[2], b''))
                want = {bbcfs.adfs_host_file(bbcfs.adfs_name(f)): d for f, d in host[3].items()}
                self.assertEqual(sorted(written), sorted(want))
                for f in want:
                    self.assertTrue(written[f] == want[f], f + ' differs')
        self.assertEqual(most, (2, 1))


def rebuild_on_two_discs(case, module, work, title, message_file=False):
    """Loop's run with the module image `module` (built by build_image(), in the module scheme in
    force) in work, checked by the test case `case`; with message_file, the message file LATHERR
    in drive 0's root, beside the sources, where the tools look for it (lathe/docs/bbc.md, "The
    message file"). Prints the account under `title` with LATHE_BBC_ADFS_LOOP or _REPORT.
    Returns (cycles, the emulator's adfs report, catalogue())."""
    import subprocess
    import test_bbc_selflink as selflink
    import test_bbc_toolchain as toolchain
    env = adfs_env(COMPILER_ENV, os.path.join(work, 'lathec.env'))
    steps = toolchain.recorded(os.path.join(LATHE, 'src', 'lathec.lth'), env, os.path.join(work, 'build'))
    flat = os.path.join(work, 'flat')
    os.makedirs(flat)
    compiles, link = toolchain.lay_out(steps, flat)
    disk = os.path.join(work, 'host')
    for d in ('0', '1'):
        os.makedirs(os.path.join(disk, d))
    shutil.copy(os.path.join(flat, os.path.basename(env)), disk)
    moved = []
    for args in compiles:             # the source from drive 0, the object and interface to 1
        name = args[-2]
        shutil.copy(os.path.join(flat, name), os.path.join(disk, '0', name))
        moved.append(args[:-2] + ['0/' + name, '1'])
    compiles = moved
    link = link[:2] + ['1/' + link[2], '1/' + link[3]] + ['1/' + o for o in link[4:]]
    with open(os.path.join(disk, selflink.COMMAND_FILE), 'w') as f:
        f.write(''.join(a + '\n' for a in link))
    again = [args for args in compiles if os.path.splitext(os.path.basename(args[-2]))[0] in selflink.LOOP_AGAIN]
    case.assertEqual(len(again), len(selflink.LOOP_AGAIN))
    host = os.path.join(work, 'hostrun')
    shutil.copytree(disk, host)
    before = set(files_of(host))
    for args in compiles:
        r = subprocess.run([sys.executable, build.COMPILER] + args, cwd=host, capture_output=True)
        case.assertEqual((r.returncode, r.stdout + r.stderr), (0, b''), args)
    r = subprocess.run([sys.executable, build.LINKER] + link, cwd=host, capture_output=True)
    case.assertEqual((r.returncode, r.stdout + r.stderr), (0, b''))
    files = {f: d for f, d in files_of(host).items() if f not in before}
    want = {bbcfs.adfs_host_file(bbcfs.adfs_name(f)): d for f, d in files.items()}
    bbc = os.path.join(work, 'bbc')
    os.makedirs(bbc)
    for f, d in files_of(disk).items():
        put(bbc, f, d)
    if message_file:
        import test_msgfile
        test_msgfile.put_on(bbc, 2)
    image = link[2]
    lines = [boards.module_command('LATHE', args) for args in compiles]
    lines.append(boards.module_command('LLINK', ['@' + selflink.COMMAND_FILE]))
    name = os.path.basename(image)
    lines += ['DIR :1', 'LOAD %s %X' % (name, PAGE), 'SAVE %s %X +%X %X' % (name, PAGE, len(files[image]), PAGE)]
    lines += [boards.module_command('RUN', [name] + args) for args in again]
    global CAP
    saved, CAP = CAP, selflink.CAP
    try:
        status, out, mos, written, cycles, report = run_adfs(module, bbc, lines, ram=True)
    finally:
        CAP = saved
    case.assertEqual((status, out, mos), (0, b'', b''))
    case.assertEqual(sorted(written), sorted(want))
    for f in want:
        case.assertTrue(written[f] == want[f], f + ' differs')
    case.assertEqual(report[:2], (2, 1))
    cat = catalogue(bbc)
    case.assertEqual(sorted(cat), [0, 1])
    for d, (_, _, n, most) in cat.items():
        case.assertEqual(report[3][d][0], n, d)        # the emulator's count is the disc's
        case.assertLessEqual(report[3][d][1], SECTORS)
        case.assertLessEqual(most, 47)
    if REPORT or LOOP:
        print('\n%s: %d cycles, %.1f minutes at 2 MHz; most open %d, writing %d,'
              ' most entries %d' % ((title, cycles, cycles / 2e6 / 60) + report[:3]))
        for line in account(cat, report):
            print('  ' + line)
    return cycles, report, cat


@unittest.skipUnless(HAVE_TOOLS and (LOOP or REPORT), 'LATHE_BBC_ADFS_LOOP=1 runs it')
class Loop(unittest.TestCase):
    """The compiler rebuilt on two ADFS discs (L, 640 KB each), with the tools built with BBCFS 2
    and ADFS 1 and the compiler they make too: in one run of the emulator with --bbc-fs adfs,
    PAGE $1F00, `*LATHE` compiles the compiler's modules from their sources, `*LLINK @LINKARG`
    links them, and the compiler just made, `*RUN LATHEC` from the module's RAM form, compiles two
    of them again. Every file written is the host tools' of the same arguments, under its ADFS
    name; one file is written at a time; nothing is deleted and no disc is changed.

    The module's RAM form holds the image from the start (board_ram: LOADMOD has filled it from a
    disc of its own, which test_loadmod_at_adfs_page shows; the short image is 768 sectors, more
    than the two discs have left). Drive 0: the 25 sources (lth), the environment (env) and the
    command file; drive 1: every object and interface (lo, li), the image (in the root, run with
    `*DIR :1` first, since the developer's form loads its banks from the CSD), its bank files (bin)
    and the map (map). Drive 0 has 66 KB left beside the sources, too little to keep 64 KB free
    for a new file (ADFS reserves 256 sectors at OPENOUT) after the first object, so it takes
    none (lathe/docs/boards.md, "On two ADFS discs", is the recipe)."""

    def test_the_compiler_rebuilds_itself_on_two_adfs_discs(self):
        work = tempfile.mkdtemp(prefix='lathe-bbc-adfs-loop-')
        self.addCleanup(shutil.rmtree, work, True)
        module, _ = build_image(os.path.join(work, 'image'))
        rebuild_on_two_discs(self, module, work, 'the loop on two ADFS discs')


if __name__ == '__main__':
    unittest.main()
