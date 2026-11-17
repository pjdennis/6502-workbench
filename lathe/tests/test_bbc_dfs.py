"""File names on the BBC (lathe/docs/bbc.md, "File names on the BBC"): with `define BBCFS 1` the
BBC's build of a program gives every name it opens to lathe/rt/bbc/bbcfs.lth's map(), which makes
the Acorn DFS's name of it (expr.lth is L.EXPR), and the emulator's --bbc-fs dfs takes only the
DFS's names, five files open and 31 a drive.

- Names: the host's twin (lathe/host/driver/bbcfs.py) on the rules, and the tools' own modules
  and the compiler's test programs all map to names apart.
- Map: map() on the BBC gives the twin's name for each of many names.
- The tool chain under --bbc-fs dfs: a program compiled, linked and run on the B+128 with every
  file under its DFS name, byte for byte the host's; a module with a long name; two modules whose
  names meet, refused by the compiler and by the linker; the compiler's self-compile in the ROM
  form (LATHE_BBC_SELFHOST=1), every module.
"""
import dataclasses
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
BBC_ENV = os.path.join(LATHE, 'env', 'bbc.env')
HAVE_TOOLS = os.path.isfile(boards.EMULATOR) and os.path.isfile(build.COMPILER)
DFS_BOARD = dataclasses.replace(boards.BOARDS['bbc'], options=boards.BOARDS['bbc'].options + ('--bbc-fs', 'dfs'))


ALL = os.environ.get('LATHE_BBC_DFS') == '1'
SELFHOST = os.environ.get('LATHE_BBC_SELFHOST') == '1'
REPORT = os.environ.get('LATHE_BBC_DFS_REPORT') == '1'
COMPILER_ENV = os.path.join(LATHE, 'src', 'lathec-bbc.env')
LINKER_ENV = os.path.join(LATHE, 'src', 'linker-bbc.env')
# BBCFS 1 adds 22 bytes of fixed code to the linker (bbc.open_mode's call of bbcfs.map, and its
# stub); since its work area went into sideways RAM (2026-11-16) the split of linker-bbc.env has
# room for them in both forms, and the DFS build no longer moves it (it moved by 16 bytes).
CAP = 4_000_000_000
DFS_RE = re.compile(r'dfs: most-open=(\d+)\s+most-writing=(\d+)')


def dfs_env(source, path, room=0):
    """Write to path the environment source with `define BBCFS 1`: the same build, the DFS's
    names; with room, the split between code and data moved up by that many bytes."""
    with open(source) as f:
        text = f.read()
    text, n = re.subn(r'(?m)^define\s+BBCFS\s+0\b', 'define    BBCFS 1', text)
    assert n == 1, source
    if room:
        import test_bbc_selfhost
        text = test_bbc_selfhost.moved_split(text, room)
    with open(path, 'w') as f:
        f.write(text)
    return path


def to_dfs(disk):
    """Move every file of disk, named as the host's tools name them, to where the emulator's
    --bbc-fs dfs keeps the file bbcfs maps that name to."""
    for f in sorted(os.listdir(disk)):
        if os.path.isfile(os.path.join(disk, f)):
            dst = bbcfs.host_path(disk, f)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.rename(os.path.join(disk, f), dst)


def put(disk, name, data):
    """A file the BBC reads as `name`, in disk as --bbc-fs dfs keeps it."""
    path = bbcfs.host_path(disk, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)


def files_of(disk):
    """{path relative to disk: bytes} of every file in disk and its drives' subdirectories, but
    the .inf files."""
    found = {}
    for top, _, names in os.walk(disk):
        for f in names:
            if not f.endswith('.inf'):
                p = os.path.join(top, f)
                with open(p, 'rb') as fh:
                    found[os.path.relpath(p, disk)] = fh.read()
    return found


def catalogue(disk):
    """{drive: (files, bytes)} of what disk holds, as a DFS's catalogues would count it."""
    drives = {}
    for rel, data in files_of(disk).items():
        drive = int(rel[1]) if rel.startswith(':') else 0
        n, size = drives.get(drive, (0, 0))
        drives[drive] = (n + 1, size + len(data))
    return drives


def run_dfs(module, disk, lines, ram=False, loaded=False):
    """Runs the * commands on the BBC under --bbc-fs dfs with the module image (in its RAM form
    through LOADMOD with ram; with loaded, the module's RAM form filled by the lines themselves),
    in disk, on memory that starts filled with bytes that are not 0
    (the emulator's --fill-ram, which boards.run_module passes): (status, output, what the MOS
    said, {file: bytes} written, CPU cycles, (most files open, most open for output))."""
    before = set(files_of(disk))
    first = []
    if ram:
        for name in ('LOADMOD', 'MODULE'):
            # The loader's MODULE is the short image (bbcrom --short), as on a disc.
            src = os.path.join(os.path.dirname(module), name) if name == 'LOADMOD' else module + '.disc'
            with open(src, 'rb') as f:
                put(disk, name, f.read())
        with open(bbcfs.host_path(disk, 'LOADMOD') + '.inf', 'w') as f:
            f.write(boards.inf_text('$.LOADMOD', 0x1900, os.path.getsize(bbcfs.host_path(disk, 'LOADMOD'))))
        first = ['RUN LOADMOD MODULE'] + first
    copied = set(files_of(disk)) - before
    command, _, tail = lines[-1].partition(' ')
    code, out, err, cycles = boards.run_module(DFS_BOARD, module, disk, command, tail=tail, ram=ram or loaded,
                                               before=first + lines[:-1], raw=True, cap=CAP)
    text = err.decode('latin-1')
    status, said, cycles = boards.bbc_status(code, text)
    m = DFS_RE.findall(text)
    most = tuple(int(n) for n in m[-1]) if m else (0, 0)
    written = {f: d for f, d in files_of(disk).items() if f not in before and f not in copied}
    for f in copied:
        os.unlink(os.path.join(disk, f))
    return status, boards.bbc_output(out), said, written, cycles, most


def build_image(out_dir):
    """The module image of both tools built with BBCFS 1, in out_dir/MODULE, with LOADMOD beside
    it and the banks in use alone in MODULE.disc (bbcrom --short), the file LOADMOD loads on a
    disc: test_bbc_toolchain.build_image's, the DFS's names. Returns (image, {tool: its map})."""
    import bbcrom
    tools = []
    first = 1
    for command, source, env, room in (('LATHE', 'lathec.lth', COMPILER_ENV, 0),
                                       ('LLINK', 'link.lth', LINKER_ENV, 0)):
        d = os.path.join(out_dir, command.lower())
        os.makedirs(d)
        dev = dfs_env(env, os.path.join(d, 'dev.env'), room)
        rom = os.path.join(d, os.path.basename(env))
        first = bbcrom.rom_env(dev, rom, first)
        resident = os.path.join(d, command)
        build.build(os.path.join(LATHE, 'src', source), resident, env=rom, keep=os.path.join(d, 'work'))
        tools.append((command, resident, rom, os.path.join(d, 'work', os.path.splitext(source)[0] + '.map')))
    image = os.path.join(out_dir, 'MODULE')
    bbcrom.image(tools, image, os.path.join(out_dir, 'listing'), short=image + '.disc')
    bbcrom.loader(os.path.join(out_dir, 'LOADMOD'))
    return image, {t[0]: t[3] for t in tools}


class Names(unittest.TestCase):
    def test_the_rules(self):
        for name, dfs in (('expr.lth', 'L.EXPR'), ('expr.lo', 'O.EXPR'), ('expr.li', 'I.EXPR'),
                          ('./err.lo', 'O.ERR'), ('././err.li', 'I.ERR'), ('EXPR.LTH', 'L.EXPR'),
                          ('asmblock.lth', 'L.ASMBLOC'), ('lk_alloc.lo', 'O.LK_ALLO'),
                          ('prog.map', 'M.PROG'), ('HELLO.map', 'M.HELLO'), ('bbc.env', 'E.BBC'),
                          ('LATHE1.BIN', 'B.LATHE1'), ('lathe33.bin', 'B.LATHE33'),
                          ('gen.txt', 'X.GEN'), ('a.lthx', 'X.A'), ('a.', 'X.A'),
                          ('HELLO', 'HELLO'), ('hello', 'hello'), ('LOADMOD', 'LOADMOD'),
                          ('2/expr.lo', ':2.O.EXPR'), ('./1/x.li', ':1.I.X'), ('3/IMAGE', ':3.IMAGE'),
                          ('0/a.lth', ':0.L.A'),
                          ('lib/k.li', None), ('4/x.lo', None), ('a/b', None), ('.lth', None),
                          ('a.b.lth', None), ('ABCDEFGHIJKLM', None), ('ABCDEFGHIJKL', 'ABCDEFGHIJKL')):
            with self.subTest(name=name):
                self.assertEqual(bbcfs.dfs_name(name), dfs)

    def test_where_the_emulator_keeps_a_file(self):
        self.assertEqual(bbcfs.host_file('L.EXPR'), 'L.EXPR')
        self.assertEqual(bbcfs.host_file('HELLO'), '$.HELLO')
        self.assertEqual(bbcfs.host_file(':2.O.EXPR'), ':2/O.EXPR')
        self.assertEqual(bbcfs.host_file(':0.L.A'), 'L.A')
        self.assertEqual(bbcfs.host_file(':3.IMAGE'), ':3/$.IMAGE')

    def test_the_tools_and_their_test_programs_map_apart(self):
        """Every module of lathe/src and lathe/rt (and lathe/rt/bbc) and every test program has a
        DFS name no other has: cutting to seven characters is safe for them today."""
        stems = set()
        for d in (os.path.join(LATHE, 'src'), os.path.join(LATHE, 'rt'), os.path.join(LATHE, 'rt', 'bbc')):
            stems |= {os.path.splitext(f)[0] for f in os.listdir(d) if f.endswith('.lth')}
        seen = {}
        for stem in sorted(stems):
            seen.setdefault(bbcfs.dfs_name(stem + '.lth'), []).append(stem)
        self.assertEqual({k: v for k, v in seen.items() if len(v) > 1}, {})
        self.assertGreater(len(stems), 60)
        self.assertIn('L.ASMBLOC', seen)


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class Map(unittest.TestCase):
    """bbcfs.map() itself, on the BBC: a program prints what it makes of each argument."""

    SOURCE = '''
module mapnames
import bbc
import bbcfs
var buf: [128]byte
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
    i = 0
    while buf[i] != 13 do
      bbc.put_byte(buf[i])
      i += 1
    end
    bbc.put_byte(10)
  end
end
'''

    NAMES = ['expr.lth', 'expr.lo', 'expr.li', './err.lo', '././err.li', 'EXPR.LTH', 'Expr.Lth',
             'asmblock.lth', 'lk_alloc.lo', 'prog.map', 'HELLO.map', 'bbc.env', 'LATHE1.BIN',
             'lathe33.bin', 'gen.txt', 'a.lthx', 'a.lt', 'a.l', 'a.', 'a.MAP', 'x.Env', 'HELLO',
             'hello', 'LOADMOD', '2/expr.lo', './1/x.li', '3/IMAGE', '0/a.lth', 'lib/k.li',
             '4/x.lo', 'a/b', '.lth', 'a.b.lth', 'ABCDEFGHIJKLM', 'ABCDEFGHIJKL', 'z_9.lth',
             'abcdefghijklmnop.lo', '1/abcdefghij.bin', 'q.li', 'q.lo', 'q.map', 'q.bin', 'q.env']

    def test_map_gives_the_twins_names(self):
        with tempfile.TemporaryDirectory(prefix='lathe-bbcfs-') as d:
            src = os.path.join(d, 'mapnames.lth')
            with open(src, 'w') as f:
                f.write(self.SOURCE)
            env = os.path.join(LATHE, 'env', 'bbc-dfs.env')
            image = os.path.join(d, 'mapnames')
            build.build(src, image, env=env, keep=os.path.join(d, 'work'))
            disk = os.path.join(d, 'disk')
            os.makedirs(disk)
            names = list(self.NAMES)
            while names:
                chunk = []
                while names and len(' '.join(chunk + [names[0]])) < 200:
                    chunk.append(names.pop(0))
                status, out, err, cycles = boards.run_mos(boards.BOARDS['bbc'], image, disk, chunk)
                self.assertEqual((status, err), (0, b''))
                want = ''.join((bbcfs.dfs_name(n) or '') + '\n' for n in chunk)    # no name: empty
                self.assertEqual(out.decode('latin-1'), want)


# ---- The tool chain under --bbc-fs dfs ---------------------------------------------------------

def host_run(compiles, link, disk, where, drive):
    """The host's compiler and linker with these arguments in a copy (where) of disk, the
    directory `drive` made in it: {path relative to where: bytes} of what they wrote."""
    import subprocess
    shutil.copytree(disk, where)
    os.makedirs(os.path.join(where, drive))
    before = set(files_of(where))
    for args in compiles:
        r = subprocess.run([sys.executable, build.COMPILER] + args, cwd=where, capture_output=True)
        assert (r.returncode, r.stdout + r.stderr) == (0, b''), r
    r = subprocess.run([sys.executable, build.LINKER] + link, cwd=where, capture_output=True)
    assert (r.returncode, r.stdout + r.stderr) == (0, b''), r
    return {f: d for f, d in files_of(where).items() if f not in before}


QUICK = ('hello', 'calls')
BANKED_QUICK = ('farcall',)

# A program with a module whose name is longer than seven characters (L.AVERYLO), and two whose
# names meet in their first seven (AVERYLONGONE and AVERYLONGTWO).
LONG = {
    'longname.lth': '''module longname
import host
import averylongone
pub func main()
  averylongone.say()
  host.put_byte(10)
end
''',
    'averylongone.lth': '''module averylongone
import host
pub func say()
  host.put_byte('1')
end
''',
    'averylongtwo.lth': '''module averylongtwo
import host
pub func say()
  host.put_byte('2')
end
''',
    'meeting.lth': '''module meeting
import host
import averylongone
import averylongtwo
pub func main()
  averylongone.say()
  averylongtwo.say()
end
''',
}


def dfs_case(case, work):
    """test_bbc_toolchain's case with the DFS's names: its environment bbc-dfs.env, or a banked
    one made from bbc-bank.env with BBCFS 1."""
    import test_bbc_bank
    name, source, make_env, extra, banked = case
    if banked:
        base = dfs_env(test_bbc_bank.BANK_ENV, os.path.join(work, 'bbc-bank-dfs.env'))
        lines = {'farcall': test_bbc_bank.FARCALL, 'bankdata': test_bbc_bank.BANKDATA,
                 'regions': test_bbc_bank.REGIONS}[name]
        make_env = (lambda path: test_bbc_bank.bank_env(path, lines, base=base, ports=0))
    else:
        make_env = (lambda path: shutil.copy(os.path.join(LATHE, 'env', 'bbc-dfs.env'), path))
    return (name, source, make_env, extra, banked)


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class Toolchain(unittest.TestCase):
    """The program's modules compiled by *LATHE, linked by *LLINK and run by *RUN on the B+128
    with --bbc-fs dfs, the tools built with BBCFS 1: every file the BBC reads and writes has its
    DFS name, and each written is byte for byte the host's file of the name it maps."""
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-bbc-dfs-')
        cls.module, cls.maps = build_image(os.path.join(cls.dir, 'image'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def chain(self, case, drive=None, ram=False):
        """Compile, link and run the case under the DFS's names: (output, {DFS host file: bytes}
        written, (most open, most writing), the disc's catalogue at the end, the compiles'
        arguments, the link's). With drive ('1' to '3'), the objects and interfaces are on that
        drive: each compile's directory is `drive` (`*LATHE NAME.lth 1`), each object `1/NAME.lo`,
        as the host's tools are given them too. With ram (and for a banked case), the tools run
        from the module's RAM form, loaded by LOADMOD from the short image."""
        import test_bbc_toolchain as toolchain
        name, source, _, _, banked = case
        work = os.path.join(self.dir, name + ('-ram' if ram else ''))
        os.makedirs(work)
        disk, compiles, link, files, said, load = toolchain.prepare(dfs_case(case, work), os.path.join(work, 'w'))
        self.assertEqual(said, [(0, b'')] * len(said))
        if drive:
            compiles = [c[:-1] + [drive] for c in compiles]
            link = link[:4] + [drive + '/' + o for o in link[4:]]
            files = host_run(compiles, link, disk, os.path.join(work, 'host-' + drive), drive)
        to_dfs(disk)
        lines = toolchain.bbc_lines(compiles, link, load, len(files[link[2]]))
        status, out, mos, written, cycles, most = run_dfs(self.module, disk, lines, ram=banked or ram)
        self.assertEqual((status, mos), (0, b''), out)
        want = {bbcfs.host_file(bbcfs.dfs_name(f)): data for f, data in files.items()}
        self.assertEqual(sorted(written), sorted(want))
        for f in want:
            self.assertTrue(written[f] == want[f], f + ' differs')
        return out, written, most, catalogue(disk), compiles, link

    def test_programs_are_compiled_linked_and_run_under_dfs_names(self):
        import test_bbc_toolchain as toolchain
        for case in toolchain.corpus():
            name, source, _, _, banked = case
            if not (ALL or name in (BANKED_QUICK if banked else QUICK)):
                continue
            with self.subTest(program=name):
                out, written, most, cat, compiles, link = self.chain(case, '1' if banked else None)
                with open(os.path.splitext(source)[0] + '.expected.out', 'rb') as f:
                    self.assertEqual(out, f.read())
                self.assertIn('M.' + link[2], written)          # the map: IMAGE.map
                self.assertEqual(most, (2, 1))      # the compiles' and the link's (one file written at a time)
                if REPORT:
                    print('\n%-10s most open %d, writing %d; the disc: %s' % (
                        name, most[0], most[1], ', '.join('drive %d %d files %d bytes' % (d, n, s)
                                                          for d, (n, s) in sorted(cat.items()))))

    @unittest.skipUnless(ALL or REPORT, 'LATHE_BBC_DFS=1 runs it')
    def test_the_largest_link_under_dfs_names(self):
        """outtest, the largest program of lathe/src the linker on the BBC takes, compiled by the
        host and linked on the BBC under the DFS's names: the image, map and bank files are the
        host's."""
        import test_bbc_toolchain as toolchain
        files, link, disk = toolchain.link_alone('outtest', os.path.join(self.dir, 'outtest'))
        for f in os.listdir(disk):
            if not f.endswith(('.lo', '.env')):
                os.unlink(os.path.join(disk, f))
        to_dfs(disk)
        status, out, mos, written, cycles, most = run_dfs(self.module, disk, [boards.module_command('LLINK', link)])
        self.assertEqual((status, out, mos), (0, b'', b''))
        want = {bbcfs.host_file(bbcfs.dfs_name(f)): d for f, d in files.items() if not f.endswith(('.lo', '.li'))}
        self.assertEqual(sorted(written), sorted(want))
        for f in want:
            self.assertTrue(written[f] == want[f], f + ' differs')
        # The image or a bank file and an object file; then the map and an object file. One is
        # written at a time: the map after the image and the bank files (lk_emit.write).
        self.assertEqual(most, (2, 1))
        # By a command file: it is read and closed before any other file is opened.
        for f in written:
            os.unlink(os.path.join(disk, f))
        put(disk, 'LINKARG', ''.join(a + '\n' for a in link).encode())
        status, out, mos, by_file, cycles, most_file = run_dfs(self.module, disk, [boards.module_command('LLINK', ['@LINKARG'])])
        self.assertEqual((status, out, mos), (0, b'', b''))
        self.assertEqual(by_file, written)
        self.assertEqual(most_file, (2, 1))
        if REPORT:
            print('\nouttest link: most open %d, writing %d; the disc: %s; written %s' % (
                most + (', '.join('drive %d %d files %d bytes' % (d, n, s) for d, (n, s) in sorted(catalogue(disk).items())),
                        ', '.join('%s %d' % (f, len(d)) for f, d in sorted(written.items())))))

    def long_sources(self, work, names):
        d = os.path.join(work, 'src')
        os.makedirs(d)
        for n in names:
            with open(os.path.join(d, n), 'w') as f:
                f.write(LONG[n])
        return d

    def test_a_module_with_a_long_name(self):
        d = self.long_sources(os.path.join(self.dir, 'long'), ('longname.lth', 'averylongone.lth'))
        out, written, most, cat, compiles, link = self.chain(
            ('longname', os.path.join(d, 'longname.lth'), None, [], False))
        self.assertEqual(out, b'1\n')
        self.assertIn('O.AVERYLO', written)
        self.assertIn('I.AVERYLO', written)
        self.assertIn('averylongone.lth', [c[-2] for c in compiles])     # the command line as on the host

    def test_the_tools_run_from_the_short_image_on_one_side(self):
        """The banks in use of both tools' image, 0 to 11, and LOADMOD fit an 80-track side
        beside the catalogue; through LOADMOD the short image compiles, links and runs hello."""
        import test_bbc_toolchain as toolchain
        short = self.module + '.disc'
        self.assertEqual(os.path.getsize(short), 12 * 0x4000)
        loader = os.path.getsize(os.path.join(os.path.dirname(self.module), 'LOADMOD'))
        sectors = 2 + (os.path.getsize(short) + 255) // 256 + (loader + 255) // 256
        self.assertLessEqual(sectors, 800)
        if REPORT:
            print('\nshort image %d bytes, LOADMOD %d: %d of 800 sectors' % (os.path.getsize(short), loader, sectors))
        case = [c for c in toolchain.corpus() if c[0] == 'hello'][0]
        name, source, make_env, extra, banked = case
        out, written, most, cat, compiles, link = self.chain(('hello', source, make_env, extra, False), ram=True)
        with open(os.path.splitext(source)[0] + '.expected.out', 'rb') as f:
            self.assertEqual(out, f.read())

    def test_an_import_chain_six_deep(self):
        """deep imports host and d1, d1 imports d2, ... d6: each exports an inline function that
        calls the next one's, so that reading d1.li brings in d2.li and so on, six interfaces
        deep. Until 2026-11-16 the compiler kept each open while it read the next, and the
        compile of deep failed on a DFS with Too many open (error 50). The compiles are 2 files
        open at most, and so has the link."""
        import test_compile
        sources = dict(test_compile.deep_chain(6))
        sources['deep.lth'] = ('module deep\nimport host\nimport d1\npub func main()\n'
                               '  host.put_byte(d1.f(0) + 48)\n  host.put_byte(10)\nend\n')
        d = os.path.join(self.dir, 'deep-src')
        os.makedirs(d)
        for n, text in sources.items():
            with open(os.path.join(d, n), 'w') as f:
                f.write(text)
        out, written, most, cat, compiles, link = self.chain(('deep', os.path.join(d, 'deep.lth'), None, [], False), '1')
        self.assertEqual(out, b'6\n')
        self.assertEqual(most, (2, 1))
        self.assertIn(':1/O.D6', written)
        # The compiles alone, again on the disc the chain left.
        disk = os.path.join(self.dir, 'deep', 'w', 'bbc')
        for c in compiles:
            if c[-2] in ('deep.lth', 'd1.lth'):
                status, out, mos, _, _, m = run_dfs(self.module, disk, [boards.module_command('LATHE', c)])
                self.assertEqual((status, out, mos), (0, b'', b''))
                self.assertEqual(m, (2, 1), c)
                if REPORT:
                    print('\n%s: most open %d, writing %d' % ((c[-2],) + m))

    def test_two_modules_whose_names_meet_are_refused(self):
        """AVERYLONGONE and AVERYLONGTWO are both L.AVERYLO, O.AVERYLO and I.AVERYLO: the disc holds
        one of each. With averylongone's files there, each tool reads averylongone's file for
        averylongtwo and refuses it, as the host's tools refuse the same files: compiling
        averylongtwo.lth is error 49 (the module's name is not the file's), compiling a module
        that imports averylongtwo error 51 (the interface is another module's), and linking both
        objects reads averylongone's twice, a symbol defined twice. The compile that is refused
        leaves averylongone's object as it was: the compiler creates its object file only after
        the module line and the imports (until 2026-11-16 it was created first, and the refused
        compile emptied averylongone's object, which a link then found damaged)."""
        import test_bbc_toolchain as toolchain
        work = os.path.join(self.dir, 'meet')
        d = self.long_sources(work, ('averylongone.lth', 'averylongtwo.lth', 'meeting.lth'))
        steps = toolchain.recorded(os.path.join(d, 'meeting.lth'), os.path.join(LATHE, 'env', 'bbc-dfs.env'),
                                   work)
        disk = os.path.join(work, 'bbc')
        os.makedirs(disk)
        compiles, link = toolchain.lay_out(steps, disk)
        host = os.path.join(work, 'host')
        shutil.copytree(disk, host)
        files, said = toolchain.host_files(compiles, link, host)
        self.assertEqual(said, [(0, b'')] * len(said))
        self.assertTrue(files['averylongone.lo'] != files['averylongtwo.lo'])
        os.unlink(os.path.join(disk, 'averylongtwo.lth'))
        to_dfs(disk)
        import test_msgfile
        test_msgfile.put_on(disk, 1)        # the texts of the errors, as $.LATHERR
        self.assertEqual(sorted(os.listdir(disk)).count('L.AVERYLO'), 1)
        two = [c for c in compiles if c[-2] == 'averylongtwo.lth'][0]
        main = [c for c in compiles if c[-2] == 'meeting.lth'][0]
        rest = [c for c in compiles if c not in (two, main)]

        def bbc(tool, args):
            return run_dfs(self.module, disk, [boards.module_command(tool, args)])

        def host_copy(tag, swap):
            """A copy of the host's directory where each `to` of swap holds the file `frm` (bytes
            or the name of a file there), as the disc does."""
            h = os.path.join(work, 'host-' + tag)
            shutil.copytree(host, h)
            for to, frm in swap:
                if isinstance(frm, bytes):
                    with open(os.path.join(h, to), 'wb') as f:
                        f.write(frm)
                else:
                    shutil.copy(os.path.join(h, frm), os.path.join(h, to))
            return h

        def host_compiles(tag, args, swap):
            import subprocess
            r = subprocess.run([sys.executable, build.COMPILER] + args, cwd=host_copy(tag, swap),
                               capture_output=True)
            return r.returncode, r.stdout + r.stderr

        status, out, mos, written, _, _ = run_dfs(self.module, disk, [boards.module_command('LATHE', c)
                                                                       for c in rest])
        self.assertEqual((status, mos), (0, b''), out)
        self.assertTrue(written['O.AVERYLO'] == files['averylongone.lo'])
        # averylongtwo.lth is averylongone's source.
        status, out, mos, written, _, _ = bbc('LATHE', two)
        self.assertEqual((status, out), host_compiles('two', two, [('averylongtwo.lth', 'averylongone.lth')]))
        self.assertIn(b'error 49', out)
        self.assertEqual(written, {})
        self.assertTrue(files_of(disk)['O.AVERYLO'] == files['averylongone.lo'])
        put(disk, 'meeting.lo', files['meeting.lo'])
        # The link reads averylongone's object for both.
        status, out, mos, written, _, _ = bbc('LLINK', link)
        twice = host_copy('twice', [('averylongtwo.lo', 'averylongone.lo')])
        self.assertEqual((status, out), toolchain.host_link(link, twice))
        self.assertTrue(out.startswith(b'link error 17: symbol defined twice'), out)
        # meeting.lth imports averylongtwo, whose interface is averylongone's.
        status, out, mos, written, _, _ = bbc('LATHE', main)
        self.assertEqual((status, out), host_compiles('main', main, [('averylongtwo.li', 'averylongone.li')]))
        self.assertIn(b'error 51', out)


@unittest.skipUnless(HAVE_TOOLS and (SELFHOST or REPORT), 'LATHE_BBC_SELFHOST=1 runs it')
class SelfHost(unittest.TestCase):
    """test_bbc_selfhost.py's ROM form under the DFS's names: the compiler built with BBCFS 1
    compiles each of its own modules on the B+128 with --bbc-fs dfs, `*LATHE OPTIONS NAME.lth .`
    on a disc that holds L.NAME and I.* of the host's interfaces of what it imports; status,
    output and every file written are the host's, under their DFS names."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-bbc-dfs-self-')
        cls.module, cls.maps = build_image(os.path.join(cls.dir, 'image'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_the_compiler_compiles_itself_under_dfs_names(self):
        import memory_report
        import test_src_selfhost as selfhost
        disc = {}                   # every file of the self-compile on one disc: DFS name -> bytes
        most = (0, 0)
        for name in selfhost.MODULES:
            options = tuple(memory_report.options_of(os.path.join(LATHE, 'src', name + '.lth')))
            disk, host = selfhost.prepare(name, os.path.join(self.dir, 'work-' + name), options)
            to_dfs(disk)
            disc.update(files_of(disk))
            args = list(options) + [name + '.lth', '.']
            status, out, mos, written, cycles, m = run_dfs(self.module, disk, [boards.module_command('LATHE', args)])
            most = tuple(max(a, b) for a, b in zip(most, m))
            if REPORT:
                print('\n%-9s most open %d, writing %d; its disc: %d files, %d bytes' % (
                    (name,) + m + (len(files_of(disk)), sum(len(d) for d in files_of(disk).values()))), end='')
            disc.update(written)
            with self.subTest(module=name):
                self.assertEqual((status, out, mos), (host[0], host[1] + host[2], b''))
                want = {bbcfs.host_file(bbcfs.dfs_name(f)): d for f, d in host[3].items()}
                self.assertEqual(sorted(written), sorted(want))
                for f in want:
                    self.assertTrue(written[f] == want[f], f + ' differs')
        # The source and one interface, then the source and the object file (five, the DFS's
        # limit, until 2026-11-16: three interfaces were read inside one another).
        self.assertEqual(most, (2, 1))
        if REPORT:
            kinds = {}
            for f, d in disc.items():
                n, size = kinds.get(f[0], (0, 0))
                kinds[f[0]] = (n + 1, size + len(d))
            print('\nthe self-compile: most open %d, writing %d; on one disc %d files, %d bytes: %s' % (
                most + (len(disc), sum(len(d) for d in disc.values()),
                        ', '.join('%s %d files %d bytes' % (k, n, s) for k, (n, s) in sorted(kinds.items())))))
            for f in sorted(disc, key=lambda f: -len(disc[f]))[:6]:
                print('  %-10s %6d' % (f, len(disc[f])))


LOOP = os.environ.get('LATHE_BBC_DFS_LOOP') == '1'
SIDE = 800 * 256 - 2 * 256      # bytes of an 80-track side beside its catalogue's two sectors
CATALOGUE = 31                  # files a DFS catalogue holds


@unittest.skipUnless(HAVE_TOOLS and (LOOP or REPORT), 'LATHE_BBC_DFS_LOOP=1 runs it')
class Loop(unittest.TestCase):
    """test_bbc_selflink.py's loop under the DFS's names, both tools and the compiler they make
    built with BBCFS 1 from the environments as committed: in one run of the emulator with
    --bbc-fs dfs, `*LATHE` compiles the compiler's modules from their sources, `*LLINK @LINKARG`
    links them, and the compiler just made, `*RUN LATHEC` from the module's RAM form (filled by
    LOADMOD from the short image), compiles two of them again. Every file written is the host
    tools' of the same arguments, under its DFS name; one file is written at a time.

    The four drives, as near to an 80-track side each as the files allow (a catalogue holds 31):
    drive 0 the environment, the command file, LOADMOD, the image and its bank files (the
    developer's form loads its banks from the drive it runs on), which fits a side; drives 1 and 2
    the objects and interfaces (a compile writes both in one directory and names the other drive
    as its directory of interfaces), 413 KB, more than two sides: one of them fits; drive 3 the
    sources, the map and the short image, which cannot fit (the sources alone are 570 KB)."""

    def test_the_compiler_rebuilds_itself_under_dfs_names(self):
        import subprocess
        import test_bbc_selflink as selflink
        import test_bbc_toolchain as toolchain
        work = tempfile.mkdtemp(prefix='lathe-bbc-dfs-loop-')
        self.addCleanup(shutil.rmtree, work, True)
        module, _ = build_image(os.path.join(work, 'image'))
        env = dfs_env(COMPILER_ENV, os.path.join(work, 'lathec.env'))
        steps = toolchain.recorded(os.path.join(LATHE, 'src', 'lathec.lth'), env, os.path.join(work, 'build'))
        flat = os.path.join(work, 'flat')
        os.makedirs(flat)
        compiles, link = toolchain.lay_out(steps, flat)
        # The sizes of each module's object and interface, from a host run on one directory.
        sized = os.path.join(work, 'sized')
        shutil.copytree(flat, sized)
        flat_files, said = toolchain.host_files(compiles, link, sized)
        self.assertEqual(said, [(0, b'')] * len(said))
        # The objects and interfaces are more than two sides hold, so drive 1 takes, largest
        # first, the modules that fit a side and its catalogue, and drive 2 the rest, but no more
        # than its catalogue holds: once it is full, the rest (the smallest) go to drive 1.
        sizes = {}
        for args in compiles:
            stem = os.path.splitext(args[-2])[0]
            sizes[stem] = len(flat_files[stem + '.lo']) + len(flat_files.get(stem + '.li', b''))
        drive = {}
        used = 0
        for stem in sorted(sizes, key=lambda m: -sizes[m]):
            fits = used + sizes[stem] <= SIDE and 2 * (list(drive.values()).count('1') + 1) <= CATALOGUE
            if not fits and 2 * (list(drive.values()).count('2') + 1) > CATALOGUE:
                fits = True
            drive[stem] = '1' if fits else '2'
            used += sizes[stem] if fits else 0
        disk = os.path.join(work, 'host')
        for d in ('1', '2', '3'):
            os.makedirs(os.path.join(disk, d))
        shutil.copy(os.path.join(flat, os.path.basename(env)), disk)
        moved = []
        for args in compiles:
            name = args[-2]
            d = drive[os.path.splitext(name)[0]]
            shutil.copy(os.path.join(flat, name), os.path.join(disk, '3', name))
            moved.append(args[:-2] + ['3/' + name, d, '2' if d == '1' else '1'])
        compiles = moved
        link = link[:3] + ['3/' + link[3]] + ['%s/%s' % (drive[os.path.splitext(o)[0]], o) for o in link[4:]]
        with open(os.path.join(disk, selflink.COMMAND_FILE), 'w') as f:
            f.write(''.join(a + '\n' for a in link))
        again = [args for args in compiles if os.path.splitext(os.path.basename(args[-3]))[0] in selflink.LOOP_AGAIN]
        self.assertEqual(len(again), len(selflink.LOOP_AGAIN))
        # The host's tools on a copy, with the same arguments.
        host = os.path.join(work, 'hostrun')
        shutil.copytree(disk, host)
        before = set(files_of(host))
        for args in compiles:
            r = subprocess.run([sys.executable, build.COMPILER] + args, cwd=host, capture_output=True)
            self.assertEqual((r.returncode, r.stdout + r.stderr), (0, b''), args)
        r = subprocess.run([sys.executable, build.LINKER] + link, cwd=host, capture_output=True)
        self.assertEqual((r.returncode, r.stdout + r.stderr), (0, b''))
        files = {f: d for f, d in files_of(host).items() if f not in before}
        want = {bbcfs.host_file(bbcfs.dfs_name(f)): d for f, d in files.items()}
        # The BBC's disc: each file under its DFS name; LOADMOD on drive 0, the short image on 3.
        bbc = os.path.join(work, 'bbc')
        os.makedirs(bbc)
        for f, d in files_of(disk).items():
            put(bbc, f, d)
        with open(os.path.join(os.path.dirname(module), 'LOADMOD'), 'rb') as f:
            put(bbc, 'LOADMOD', f.read())
        with open(bbcfs.host_path(bbc, 'LOADMOD') + '.inf', 'w') as f:
            f.write(boards.inf_text('$.LOADMOD', 0x1900, os.path.getsize(bbcfs.host_path(bbc, 'LOADMOD'))))
        with open(module + '.disc', 'rb') as f:
            put(bbc, '3/MODULE', f.read())
        image = link[2]
        load = mapenv.read_env(env).code[0]
        lines = ['RUN LOADMOD :3.MODULE']
        lines += [boards.module_command('LATHE', args) for args in compiles]
        lines.append(boards.module_command('LLINK', ['@' + selflink.COMMAND_FILE]))
        lines += ['LOAD %s %X' % (image, load), 'SAVE %s %X +%X %X' % (image, load, len(files[image]), load)]
        lines += [boards.module_command('RUN', [image] + args) for args in again]
        saved = globals()['CAP']
        globals()['CAP'] = selflink.CAP
        try:
            status, out, mos, written, cycles, most = run_dfs(module, bbc, lines, loaded=True)
        finally:
            globals()['CAP'] = saved
        self.assertEqual((status, out, mos), (0, b'', b''))
        self.assertEqual(sorted(written), sorted(want))
        for f in want:
            self.assertTrue(written[f] == want[f], f + ' differs')
        # The compiler has two files open at most (a source or an interface, and the object);
        # the linker two (an object file, and the image, a bank file or the map).
        self.assertEqual(most, (2, 1))
        cat = catalogue(bbc)
        self.assertLessEqual(max(n for n, _ in cat.values()), CATALOGUE)
        self.assertLessEqual(cat[0][1], SIDE)
        self.assertLessEqual(min(cat[1][1], cat[2][1]), SIDE)    # together they are more than two sides
        if REPORT or LOOP:
            print('\nthe loop under DFS names: %d cycles, %.1f minutes at 2 MHz; most open %d, writing %d;'
                  ' the disc: %s' % ((cycles, cycles / 2e6 / 60) + most + (
                      ', '.join('drive %d %d files %d bytes' % (d, n, sz) for d, (n, sz) in sorted(cat.items())),)))


@unittest.skipUnless(HAVE_TOOLS and (ALL or REPORT), 'LATHE_BBC_DFS=1 runs it')
class DeveloperForms(unittest.TestCase):
    """Both tools in the developer's form (`*RUN`), built with BBCFS 1 from lathec-bbc.env and
    linker-bbc.env as committed, start under --bbc-fs dfs: their start-up loads the banks through
    bbc.open and bbcfs.map, which must be in fixed memory there (bbcrom.rom_env puts bbcfs in a
    bank only in the ROM form). The compiler compiles a small module and the linker links hello,
    as the host's tools do."""

    def test_both_tools_start_in_the_developers_form(self):
        import test_bbc_toolchain as toolchain
        work = tempfile.mkdtemp(prefix='lathe-bbc-dfs-dev-')
        self.addCleanup(shutil.rmtree, work, True)
        module, _ = build_image(os.path.join(work, 'image'))
        case = [c for c in toolchain.corpus() if c[0] == 'hello'][0]
        disk, compiles, link, files, said, load = toolchain.prepare(dfs_case(case, os.path.join(work, 'case')),
                                                                     os.path.join(work, 'w'))
        self.assertEqual(said, [(0, b'')] * len(said))
        to_dfs(disk)
        for tool, source, env in (('LATHEC', 'lathec.lth', COMPILER_ENV), ('LLINK', 'link.lth', LINKER_ENV)):
            d = os.path.join(work, tool)
            os.makedirs(d)
            dev = dfs_env(env, os.path.join(d, os.path.basename(env)))
            build.build(os.path.join(LATHE, 'src', source), os.path.join(d, tool), env=dev, keep=os.path.join(d, 'work'))
            for f in os.listdir(d):
                if f == tool or f.upper().endswith('.BIN'):
                    with open(os.path.join(d, f), 'rb') as fh:
                        put(disk, f, fh.read())
            with open(bbcfs.host_path(disk, tool) + '.inf', 'w') as fh:
                fh.write(boards.inf_text('$.' + tool, 0x1900, os.path.getsize(os.path.join(d, tool))))
        lines = [boards.module_command('RUN', ['LATHEC'] + args) for args in compiles]
        lines.append(boards.module_command('RUN', ['LLINK'] + link))
        status, out, mos, written, cycles, most = run_dfs(module, disk, lines, ram=True)
        self.assertEqual((status, out, mos), (0, b'', b''))
        want = {bbcfs.host_file(bbcfs.dfs_name(f)): data for f, data in files.items()}
        self.assertEqual(sorted(written), sorted(want))
        for f in want:
            self.assertTrue(written[f] == want[f], f + ' differs')

if __name__ == '__main__':
    unittest.main()
