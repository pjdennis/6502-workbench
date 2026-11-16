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

LATHE = os.path.join(ROOT, 'lathe')
BBC_ENV = os.path.join(LATHE, 'env', 'bbc.env')
HAVE_TOOLS = os.path.isfile(boards.EMULATOR) and os.path.isfile(build.COMPILER)
DFS_BOARD = dataclasses.replace(boards.BOARDS['bbc'], options=boards.BOARDS['bbc'].options + ('--bbc-fs', 'dfs'))


ALL = os.environ.get('LATHE_BBC_DFS') == '1'
SELFHOST = os.environ.get('LATHE_BBC_SELFHOST') == '1'
REPORT = os.environ.get('LATHE_BBC_DFS_REPORT') == '1'
COMPILER_ENV = os.path.join(LATHE, 'src', 'lathec-bbc.env')
LINKER_ENV = os.path.join(LATHE, 'src', 'linker-bbc.env')
# The linker on the BBC has 6 bytes of fixed code to spare in its developer form, whose split
# sets the ROM form's (linker-bbc.env); BBCFS 1 adds 22 (bbc.open_mode's call of bbcfs.map, and
# its stub): its DFS build moves the split up by LINKER_ROOM (bbc.md, "File names on the BBC").
LINKER_ROOM = 0x10
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
        split = int(re.search(r'(?m)^data\s+\$(\w+)', text).group(1), 16) + room
        text = re.sub(r'(?m)^code\s.*$', 'code      $1900 $%04X' % (split - 1), text)
        text = re.sub(r'(?m)^data\s+\$\w+', 'data      $%04X' % split, text)
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


def run_dfs(module, disk, lines, ram=False):
    """Runs the * commands on the BBC under --bbc-fs dfs with the module image (in its RAM form
    through LOADMOD with ram), in disk, on memory that starts filled with bytes that are not 0
    (the emulator's --fill-ram, which boards.run_module passes): (status, output, what the MOS
    said, {file: bytes} written, CPU cycles, (most files open, most open for output))."""
    before = set(files_of(disk))
    first = []
    if ram:
        for name in ('LOADMOD', 'MODULE'):
            src = os.path.join(os.path.dirname(module), name) if name == 'LOADMOD' else module
            with open(src, 'rb') as f:
                put(disk, name, f.read())
        with open(bbcfs.host_path(disk, 'LOADMOD') + '.inf', 'w') as f:
            f.write(boards.inf_text('$.LOADMOD', 0x1900, os.path.getsize(bbcfs.host_path(disk, 'LOADMOD'))))
        first = ['RUN LOADMOD MODULE'] + first
    copied = set(files_of(disk)) - before
    command, _, tail = lines[-1].partition(' ')
    code, out, err, cycles = boards.run_module(DFS_BOARD, module, disk, command, tail=tail, ram=ram,
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
    it: test_bbc_toolchain.build_image's, the DFS's names. Returns (image, {tool: its map})."""
    import bbcrom
    tools = []
    first = 1
    for command, source, env, room in (('LATHE', 'lathec.lth', COMPILER_ENV, 0),
                                       ('LLINK', 'link.lth', LINKER_ENV, LINKER_ROOM)):
        d = os.path.join(out_dir, command.lower())
        os.makedirs(d)
        dev = dfs_env(env, os.path.join(d, 'dev.env'), room)
        rom = os.path.join(d, os.path.basename(env))
        first = bbcrom.rom_env(dev, rom, first)
        resident = os.path.join(d, command)
        build.build(os.path.join(LATHE, 'src', source), resident, env=rom, keep=os.path.join(d, 'work'))
        tools.append((command, resident, rom, os.path.join(d, 'work', os.path.splitext(source)[0] + '.map')))
    image = os.path.join(out_dir, 'MODULE')
    bbcrom.image(tools, image, os.path.join(out_dir, 'listing'))
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

    def chain(self, case, drive=None):
        """Compile, link and run the case under the DFS's names: (output, {DFS host file: bytes}
        written, (most open, most writing), the disc's catalogue at the end, the compiles'
        arguments, the link's). With drive ('1' to '3'), the objects and interfaces are on that
        drive: each compile's directory is `drive` (`*LATHE NAME.lth 1`), each object `1/NAME.lo`,
        as the host's tools are given them too."""
        import test_bbc_toolchain as toolchain
        name, source, _, _, banked = case
        work = os.path.join(self.dir, name)
        os.makedirs(work)
        disk, compiles, link, files, said, load = toolchain.prepare(dfs_case(case, work), os.path.join(work, 'w'))
        self.assertEqual(said, [(0, b'')] * len(said))
        if drive:
            compiles = [c[:-1] + [drive] for c in compiles]
            link = link[:4] + [drive + '/' + o for o in link[4:]]
            files = host_run(compiles, link, disk, os.path.join(work, 'host-' + drive), drive)
        to_dfs(disk)
        lines = toolchain.bbc_lines(compiles, link, load, len(files[link[2]]))
        status, out, mos, written, cycles, most = run_dfs(self.module, disk, lines, ram=banked)
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
            if name in toolchain.BEYOND or not (ALL or name in (BANKED_QUICK if banked else QUICK)):
                continue
            with self.subTest(program=name):
                out, written, most, cat, compiles, link = self.chain(case, '1' if banked else None)
                with open(os.path.splitext(source)[0] + '.expected.out', 'rb') as f:
                    self.assertEqual(out, f.read())
                self.assertIn('M.' + link[2], written)          # the map: IMAGE.map
                self.assertLessEqual(most[0], 5)
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
        self.assertEqual(most, (3, 2))          # the map, the image and an object file; the first two written
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

    def test_two_modules_whose_names_meet_are_refused(self):
        """AVERYLONGONE and AVERYLONGTWO are both L.AVERYLO, O.AVERYLO and I.AVERYLO: the disc holds
        one of each. With averylongone's files there, each tool reads averylongone's file for
        averylongtwo and refuses it, as the host's tools refuse the same files: compiling
        averylongtwo.lth is error 49 (the module's name is not the file's), compiling a module
        that imports averylongtwo error 51 (the interface is another module's), and linking both
        objects reads averylongone's twice, a symbol defined twice. But the compiler creates its
        object file before it reads the module's name, so the compile that is refused has emptied
        averylongone's object: a link then finds it damaged until averylongone is compiled again."""
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
        self.assertEqual(sorted(os.listdir(disk)).count('L.AVERYLO'), 1)
        one = [c for c in compiles if c[-2] == 'averylongone.lth'][0]
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
        self.assertEqual(files_of(disk)['O.AVERYLO'], b'')
        put(disk, 'meeting.lo', files['meeting.lo'])
        status, out, mos, written, _, _ = bbc('LLINK', link)
        empty = host_copy('empty', [('averylongone.lo', b''), ('averylongtwo.lo', b'')])
        self.assertEqual((status, out), toolchain.host_link_at_bbc(link, empty))
        self.assertTrue(out.startswith(b'link error 6: object file is damaged: averylongone.lo'), out)
        # Compiled again: the link reads averylongone's object for both.
        status, out, mos, written, _, _ = bbc('LATHE', one)
        self.assertEqual(status, 0, out)
        status, out, mos, written, _, _ = bbc('LLINK', link)
        twice = host_copy('twice', [('averylongtwo.lo', 'averylongone.lo')])
        self.assertEqual((status, out), toolchain.host_link_at_bbc(link, twice))
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
        self.assertLessEqual(most[0], 5)
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


if __name__ == '__main__':
    unittest.main()
