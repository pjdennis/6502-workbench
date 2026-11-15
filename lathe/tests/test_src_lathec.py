"""The compiler written in Lathe: lathe/src/lathec.lth, the main module, with the twins of all
seventeen host modules, built banked on Wendy 2 with --disk (lathe/src/compiler-bank.env with
SMALL 1: the small build's capacities; test_src_selfhost.py runs it at full size) and run on the emulator over the corpus, against the host compiler
(lathe/host/lathec.py) at the same capacities (lathec_small.py, script_host.SMALL).

The inputs are every module of the corpus memory_report.py compiles: the snapshot cases
(cases/snap), the error cases (cases/err), the end-to-end cases and the modules beside them
(cases/e2e*, and cases/linkerr), the run-time modules (lathe/rt) and the modules of lathe/src,
the twins among them. Each is compiled with the options memory_report.options_of() gives it, on
a directory that holds the source and the interface files of the modules it imports (made by
the host compiler at full size), named by their base names: `lathec OPTIONS NAME.lth .`. The
status, the output, the error output and the files written (NAME.lo, NAME.li) must be the same.

An input "fits" if the host compiler at the small capacities compiles it without a capacity
error (CAPACITY), or is an error case that gives the error its first line names; one that does not fit is compared too, and its capacity error must be the
same. Nothing here lists what fits: when the capacities grow, more inputs fit by themselves.
test_report() prints the counts (LATHE_LATHEC_REPORT=1), and with LATHE_LATHEC_COVERAGE=1 the
statements of decl.py and lathec.py that the inputs reach on the host side.

By default a part of the inputs runs (SUBSET: every input that fits and every STRIDE-th that
does not, the first of each kind among them); LATHE_BANKED_ALL=1 runs all of them."""
import concurrent.futures
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import src_support as support
import memory_report

ALL = os.environ.get('LATHE_BANKED_ALL') == '1'
# LATHE_LATHEC_FULL=1: the banked build at full size against the host compiler at full size
# (stage 11, step 10), over the same inputs; the checks of what the small inputs reach are not
# made then.
FULL = os.environ.get('LATHE_LATHEC_FULL') == '1'
HERE = os.path.dirname(os.path.abspath(__file__))
LATHE = os.path.dirname(HERE)
SMALL_LATHEC = os.path.join(HERE, 'lathec_small.py')
STRIDE = 12             # of the inputs that do not fit, every STRIDE-th runs by default
STRIDES = {'err': 6, 'e2e': 3, 'snap': 2}   # of those that fit, every N-th of these kinds
# The errors about a capacity: 70 to 98, those memory_report.CAPACITY adds, and 7, a string
# longer than the small build's (lex.MAX_STRING) where the language allows 2,048 bytes
CAPACITY = re.compile(rb': error (7\d|8\d|9[0-8]|%s|7): ' % b'|'.join(b'%d' % n for n in memory_report.CAPACITY))
ERROR = re.compile(rb': error (\d+): ')


LETTERS = b'abcdefghijklmnopqrstuvwxyz'
M = b'module m\n'                   # a module that compiles, called m.lth
BAD = b'module m\nimport bad\n'    # one that imports `bad`, whose interface is damaged
LI = b'LI\x02\x03bad'               # the header of bad.li

# Modules for the inputs about import lists (lathe/docs/language.md, "Modules"): j has a type of
# every kind, a table and a variable in a region and inline functions, one of them pure; k
# imports j and exports inline functions that name j's, one with a string; a's inline function
# names k's. Their interfaces are made by the host compiler when this file is loaded.
LISTS_J = b"""module j
pub const X = 1
pub var y: byte
pub var z: byte
type Priv = record
  a: byte
end
pub type W = word
pub type H = func(n: byte)
pub enum E
  A
end
pub type T = record
  a: byte
  b: word
end
pub var r: [4]byte in R
pub const K: [2]byte in R = [1, 2]
pub inline func g(n: byte): byte
  return n + X
end
pub inline func zap()
  z = 5
end
pub func q()
end
"""
LISTS_K = b"""module k
import j
pub var c: byte
pub inline func inl(n: byte)
  c += j.g(n)
  j.y = n
end
pub inline func other(): ^byte
  return "ab"
end
"""
LISTS_A = b"module a\nimport k\npub inline func ai()\n  k.c = 1\nend\n"


def made_interfaces():
    """{NAME.li: bytes} of j, k and a, compiled by the host compiler."""
    found = {}
    with tempfile.TemporaryDirectory() as d:
        for name, text in (('j', LISTS_J), ('k', LISTS_K), ('a', LISTS_A)):
            path = os.path.join(d, name + '.lth')
            with open(path, 'wb') as f:
                f.write(text)
            subprocess.run([sys.executable, os.path.join(LATHE, 'host', 'lathec.py'), path, d], check=True)
            with open(os.path.join(d, name + '.li'), 'rb') as f:
                found[name + '.li'] = f.read()
    return found


LISTS = made_interfaces()


def lists_input(title, source):
    return (title, ['m.lth', '.'], dict([('m.lth', source)] + list(LISTS.items())))


# (title, arguments, {file: bytes}) of the inputs that the corpus does not have. The command
# lines of lathe/host/README.md, "Command lines", that are errors; file names that cannot be a
# module's; a source in a directory and an import directory; damaged interfaces
# (README.md, "The interface file"), each read by `import bad`; a module that exports a
# variable and a table in a region, and one that imports a function that is `interrupt`, a
# variable and a table in a region (an interface made by hand); and one with so many initial
# values that they are written out in parts (gen.INIT_FLUSH).
MADE = [
    ('no arguments', [], {}),
    ('-c of no CPU', ['-c8080', 'm.lth', '.'], {'m.lth': M}),
    ('-d of no name', ['-d', 'm.lth', '.'], {'m.lth': M}),
    ('-d of a name that starts with a digit', ['-d1x', 'm.lth', '.'], {'m.lth': M}),
    ('-d of a name with a minus', ['-dA-B', 'm.lth', '.'], {'m.lth': M}),
    ('-d of a keyword', ['-dwith', 'm.lth', '.'], {'m.lth': M}),
    ('-d with no number after =', ['-dA=', 'm.lth', '.'], {'m.lth': M}),
    ('-d with a number above 65535', ['-dA=65536', 'm.lth', '.'], {'m.lth': M}),
    ('-d with a letter in the number', ['-dA=1x', 'm.lth', '.'], {'m.lth': M}),
    ('-d with the largest number', ['-dA=65535', '-c65c02', '-c6502', 'm.lth', '.'], {'m.lth': M}),
    ('an option not known', ['-x', 'm.lth', '.'], {'m.lth': M}),
    ('options and no source', ['-c6502'], {}),
    ('no output directory', ['m.lth'], {'m.lth': M}),
    ('a source in a directory', ['sub/m.lth', '.'], {'sub/m.lth': M}),
    ('a source not called .lth', ['m.txt', '.'], {'m.txt': M}),
    ('a source called .lth', ['.lth', '.'], {'.lth': M}),
    ('a source whose name starts with a digit', ['1m.lth', '.'], {'1m.lth': M}),
    ('a source whose name has a minus', ['m-x.lth', '.'], {'m-x.lth': M}),
    ('a source that is not there', ['none.lth', '.'], {}),
    ('an output directory that is not there', ['m.lth', 'none'], {'m.lth': M}),
    ('an import directory', ['m.lth', '.', 'lib'],
     {'m.lth': b'module m\nimport k\n', 'lib/k.li': b'LI\x02\x01k\x00'}),
    ('an interface of another version', ['m.lth', '.'], {'m.lth': BAD, 'bad.li': b'LI\x01\x03bad\x00'}),
    ('an interface of another module', ['m.lth', '.'], {'m.lth': BAD, 'bad.li': b'LI\x02\x03bax\x00'}),
    ('an interface cut short', ['m.lth', '.'], {'m.lth': BAD, 'bad.li': LI}),
    ('an interface with an entry of no known kind', ['m.lth', '.'], {'m.lth': BAD, 'bad.li': LI + b'\x0b'}),
    ('an interface with a type of no known code', ['m.lth', '.'],
     {'m.lth': BAD, 'bad.li': LI + b'\x03\x01v\x55\x00\x00'}),
    ('an interface with a type of a module not imported', ['m.lth', '.'],
     {'m.lth': BAD, 'bad.li': LI + b'\x03\x01v\x13\x02zz\x01t\x00\x00'}),
    ('an interface with a type its module does not have', ['m.lth', '.'],
     {'m.lth': BAD, 'bad.li': LI + b'\x03\x01v\x13\x03bad\x01q\x00\x00'}),
    ('an interface with a placement of no known kind', ['m.lth', '.'],
     {'m.lth': BAD, 'bad.li': LI + b'\x03\x01v\x01\x03\x00'}),
    ('an interface with a function of 65 parameters', ['m.lth', '.'],
     {'m.lth': BAD, 'bad.li': LI + b'\x01\x01f\x00\x41' + b'\x01\x00' * 65 + b'\x00\x00'}),
    ('an interface with an interrupt function and a variable and a table in a region', ['m.lth', '.'],
     {'m.lth': b'module m\nimport bad\nfunc f()\n  with r do\n    bad.v[1] = bad.k[0]\n  end\nend\n',
      'bad.li': LI + b'\x01\x04tick\x10\x00\x00' + b'\x03\x01v\x11\x04\x00\x01\x08\x01r'
      + b'\x09\x01k\x11\x02\x00\x01\x00\x00\x01r\x00'}),
    ('a variable and a table in a region, exported', ['m.lth', '.'],
     {'m.lth': b'module m\npub var t: [4]byte in r\npub const K: [2]byte in r = [1, 2]\n'}),
    ('nine directories', ['m.lth', '.', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'], {'m.lth': M}),
    ('an interface that cannot be created', ['m.lth', '.'], {'m.lth': M, 'm.li/x': b''}),
    # A capacity of the small build reached: each error 70 to 98 and 156 that can be
    ('too many names (70)', ['m.lth', '.'],
     {'m.lth': b'module m\n' + b''.join(b'var v%d: byte\n' % i for i in range(150))}),
    ('too many symbols (71): fields of the same names in ten records', ['m.lth', '.'],
     {'m.lth': b'module m\n' + b''.join(b'type R%d = record\n' % r + b''.join(b'  %c: byte\n' % c for c in LETTERS)
                                         + b'end\n' for r in range(10))}),
    ('too many imports (73)', ['m.lth', '.'],
     dict([('m.lth', b'module m\n' + b''.join(b'import %c\n' % c for c in LETTERS[:17] if c != ord('m')))]
          + [('%c.li' % c, b'LI\x02\x01%c\x00' % c) for c in LETTERS[:17] if c != ord('m')])),
    ('too many types (74)', ['m.lth', '.'],
     {'m.lth': b'module m\n' + b''.join(b'type R%d = record\n  x: byte\nend\n' % r for r in range(30))}),
    ('a function too large (75)', ['m.lth', '.'],
     {'m.lth': b'module m\nvar a: byte\nvar b: byte\nfunc f()\n' + b'a = b + 3\nb = a + 5\n' * 200 + b'end\n'}),
    ('too many labels (76)', ['m.lth', '.'],
     {'m.lth': b'module m\nvar a: byte\nfunc f()\n' + b'if a == 0 then\nend\n' * 130 + b'end\n'}),
    ('too many calls (78)', ['m.lth', '.'],
     {'m.lth': b'module m\n' + b''.join(b'func f%d()\nend\n' % i for i in range(66)) + b'func g()\n'
      + b''.join(b'f%d()\n' % i for i in range(66)) + b'end\n'}),
    ('too many open files (80): interfaces that bring in modules for their inline functions', ['m.lth', '.'],
     dict([('m.lth', b'module m\nimport a\n')] + [('%c.li' % c, b'LI\x02\x01%c' % c + (b'\x08\x01%c' % (c + 1) if c < ord('j') else b'')
                                                 + b'\x00') for c in LETTERS[:10]])),
    ('text memory full (82): the file names of imported inline functions', ['m.lth', '.'],
     {'m.lth': b'module m\nimport bad\n', 'bad.li': LI + b''.join(
         b'\x01\x01%c\x08\x00\x00\x64' % c + b'f' * 100 + b'\x01\x00\x00\x00\x00' for c in b'ghknpq') + b'\x00'}),
    ('a file name too long (83)', ['m.lth', '.', 'd' * 240],
     {'m.lth': b'module m\nimport abcdefghijklmnopqrstuvwxyz01234\n'}),
    ('too many locals in an inline function (85)', ['m.lth', '.'],
     {'m.lth': b'module m\ninline func g()\n' + b''.join(b'  var %c%c\n' % (a, b) for a in b'ab' for b in LETTERS[:17])
      + b'end\n'}),
    ('too many initial values in one function (86)', ['m.lth', '.'],
     {'m.lth': b'module m\nfunc f()\n' + b''.join(b'  static var s%d: byte = 1\n' % i for i in range(34)) + b'end\n'}),
    ('too many saved tokens of inline functions (165)', ['m.lth', '.'],
     {'m.lth': b'module m\nvar a: byte\ninline func g()\n' + b'  a = a + 1\n' * 60 + b'end\n'}),
    ('too many functions taken as function types (156)', ['m.lth', '.'],
     {'m.lth': b'module m\ntype H = func()\n' + b''.join(b'func f%d()\nend\n' % i for i in range(70))
      + b''.join(b'const T%d: [14]H = [' % t + b', '.join(b'@f%d' % (t * 14 + i) for i in range(14)) + b']\n'
                 for t in range(5))}),
    # Import lists: interfaces read again, entries and inline functions passed over
    lists_input('a list, then the module an inline function brought in, with no list',
                b'module m\nimport k (inl)\nimport j\nfunc f()\n  k.inl(1)\n  j.q()\nend\n'),
    lists_input('a list, then the module an inline function brought in, with a list',
                b'module m\nimport k (inl)\nimport j (y, T, q)\nvar t: j.T\nfunc f()\n  k.inl(1)\n'
                b'  j.y = 2\n  j.q()\nend\n'),
    lists_input('a module with a list, then one whose inline function names more of it',
                b'module m\nimport j (X)\nimport k (inl)\nfunc f()\n  k.inl(j.X)\nend\n'),
    lists_input('a listed type that is not pub (102)', b'module m\nimport j (Priv)\n'),
    lists_input('a listed type that is not pub, in a module read before (102)',
                b'module m\nimport k (inl)\nimport j (Priv)\n'),
    lists_input('a listed module of an interface, in a module read before (102)',
                b'module m\nimport a (ai)\nimport k (j)\n'),
    ('too many names in an import list (89)', ['m.lth', '.'],
     {'m.lth': b'module m\nimport j (' + b', '.join(b'n%d' % i for i in range(49)) + b')\n'}),
    ('initial values written out in parts', ['m.lth', '.'],
     {'m.lth': b'module m\n' + b''.join(b'var v%d: byte = %d\n' % (i, i) for i in range(40))}),
]


def kind_of(path):
    d = os.path.basename(os.path.dirname(path))
    if d in ('snap', 'err', 'rt', 'src'):
        return {'rt': 'run-time', 'src': 'twins'}.get(d, d)
    return 'e2e'


def inputs():
    """[(kind, path)] of the corpus, in memory_report's order."""
    return [(kind_of(p), p) for p, _ in memory_report.corpus()]


def imports_of(path):
    """[(name, path)] of the modules `path` imports, in the order to compile them, or None if
    one cannot be found (an error case of a missing module)."""
    sys.path.insert(0, os.path.join(LATHE, 'host', 'driver'))
    import build
    try:
        return build.module_order(path)[:-1]
    except build.BuildError:
        return None


class Corpus:
    """The inputs, each with the directory of what it needs: the source and its imports'
    interfaces."""

    def __init__(self, work):
        sys.path.insert(0, os.path.join(LATHE, 'host', 'driver'))
        import build
        self.work = work
        self.done = {}          # (path, options) -> the directory that has its interface
        self.items = []         # (kind, path, arguments, files: [(name on the disk, path)])
        host_li = None
        for n, (kind, path) in enumerate(inputs()):
            options = tuple(memory_report.options_of(path))
            files = [(os.path.basename(path), path)]
            order = imports_of(path)
            if kind == 'err':
                if host_li is None:
                    host_li = self.interface(os.path.join(LATHE, 'rt', 'host.lth'), ())
                if host_li:
                    files.append((os.path.basename(host_li), host_li))
                order = []
            for name, dep in order or []:
                li = self.interface(dep, options)
                if li:
                    files.append((os.path.basename(li), li))
            self.items.append((kind, path, list(options) + [os.path.basename(path), '.'], files))
        self.made()

    def made(self):
        """The inputs MADE describes: command lines and file names the corpus does not have,
        damaged interfaces, and modules the corpus has nothing like."""
        for n, (title, args, files) in enumerate(MADE):
            where = os.path.join(self.work, 'made-%d' % n)
            listed = []
            for name, data in files.items():
                path = os.path.join(where, name)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'wb') as f:
                    f.write(data)
                listed.append((name, path))
            self.items.append(('made', title, args, listed))

    def interface(self, path, options):
        """The interface file of the module at `path` compiled with `options` by the host at
        full size, with the interfaces of what it imports beside it; None if it does not
        compile."""
        sys.path.insert(0, os.path.join(LATHE, 'host', 'driver'))
        import build
        key = (os.path.abspath(path), options)
        if key not in self.done:
            out = os.path.join(self.work, 'li-%d' % len(self.done))
            os.makedirs(out)
            for name, dep in imports_of(path) or []:
                li = self.interface(dep, options)
                if li:
                    shutil.copy(li, out)
            status = subprocess.run([sys.executable, build.COMPILER] + list(options) + [path, out],
                                    capture_output=True).returncode
            self.done[key] = out if status == 0 else None
        if self.done[key] is None:
            return None
        return os.path.join(self.done[key], build.module_name(path) + '.li')


def outputs(disk, before):
    """{name: bytes} of the files in `disk` that were not there before, but the board's own."""
    import boards
    found = {}
    for name in sorted(os.listdir(disk)):
        if name in before or name in (boards.ARGS_FILE, boards.OUT_FILE, boards.ERRORS_FILE,
                                      boards.STATUS_FILE) or not os.path.isfile(os.path.join(disk, name)):
            continue
        with open(os.path.join(disk, name), 'rb') as f:
            found[name] = f.read()
    return found


def fill(disk, files):
    """Copy the input's files to the directory the compiler runs in. Returns what it holds."""
    for name, path in files:
        os.makedirs(os.path.dirname(os.path.join(disk, name)), exist_ok=True)
        shutil.copyfile(path, os.path.join(disk, name))
    return set(os.listdir(disk))


def run_host(item, work):
    """(status, output, error output, {file: bytes}) of the host compiler at the small
    capacities on one input."""
    kind, path, args, files = item
    with tempfile.TemporaryDirectory(dir=work) as disk:
        before = fill(disk, files)
        oracle = os.path.join(LATHE, 'host', 'lathec.py') if FULL else SMALL_LATHEC
        done = subprocess.run([sys.executable, oracle] + args, cwd=disk, capture_output=True)
        return done.returncode, done.stdout, done.stderr, outputs(disk, before)


def run_lathe(image, item, work, cycles=False):
    """The same of the Lathe-written compiler, run banked on Wendy 2 (src_support.run_banked's
    way, with every file of the directory kept); with `cycles`, the CPU cycles of the run
    follow."""
    import boards
    import dataclasses
    import mapenv
    sys.path.insert(0, os.path.join(LATHE, 'host', 'driver'))
    import build
    kind, path, args, files = item
    env = mapenv.read_env(os.path.splitext(image)[0] + '.env')
    board = dataclasses.replace(boards.BOARDS['wendy2disk'], cycle_cap=support.BANKED_CYCLE_CAP)
    with tempfile.TemporaryDirectory(dir=work) as disk:
        build.window_files(env, os.path.dirname(os.path.abspath(image)), disk)
        before = fill(disk, files)
        with open(os.path.join(disk, boards.ARGS_FILE), 'wb') as f:
            f.write(b''.join(a.encode('latin-1') + b'\n' for a in args))
        report = boards.emulate(board, image, env, disk)
        boards.read_report(board, report)
        found = (boards.read_status(disk), boards.read_file(disk, boards.OUT_FILE),
                 boards.read_file(disk, boards.ERRORS_FILE), outputs(disk, before))
        if cycles:
            m = re.search(r'cpu_cycles=(\d+)', report)
            return found + (int(m.group(1)) if m else 0,)
        return found


def fits(item, host):
    """True if the host's run ended without a capacity error, or an error case gave the error
    its first line names, where it names it (one about a capacity among them)."""
    kind, path, args, files = item
    if kind == 'made':
        return True             # made to be small: a capacity error is what one is about
    if kind == 'err':
        with open(path, 'rb') as f:
            want = f.readline().split()
        if host[2].startswith(b'%s:%s:%s: error %s: ' % (os.path.basename(path).encode(), want[3],
                                                          want[4], want[2])):
            return True
    return not CAPACITY.search(host[2])


class LathecTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-src-lathec-')
        cls.image = support.build_program('lathec', cls.dir, small=not FULL, banked=True)
        cls.corpus = Corpus(os.path.join(cls.dir, 'corpus'))
        with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
            cls.host = list(pool.map(lambda i: run_host(i, cls.dir), cls.corpus.items))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def chosen(self):
        """The inputs this run compares: all of them with LATHE_BANKED_ALL=1, else each kind's
        every STRIDES-th input that fits and every STRIDE-th of the others."""
        picked, seen = [], {}
        for n, (item, host) in enumerate(zip(self.corpus.items, self.host)):
            kind = item[0]
            fit = fits(item, host)
            seen[kind, fit] = seen.get((kind, fit), -1) + 1
            if ALL or seen[kind, fit] % (STRIDES.get(kind, 1) if fit else STRIDE) == 0:
                picked.append(n)
        return picked

    def test_the_lathe_compiler_gives_the_host_compilers_output(self):
        picked = self.chosen()
        with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
            lathe = list(pool.map(lambda n: run_lathe(self.image, self.corpus.items[n], self.dir), picked))
        counts = {}
        for n, got in zip(picked, lathe):
            kind, path, args, files = self.corpus.items[n]
            host = self.host[n]
            verdict = 'fits' if fits(self.corpus.items[n], host) else 'too big'
            same = got == host
            key = (kind, verdict, 'same' if same else 'differs')
            counts[key] = counts.get(key, 0) + 1
            with self.subTest(input=path if kind == 'made' else os.path.relpath(path, LATHE)):
                self.assertEqual(got[0], host[0], 'status; errors: %r / %r' % (got[2], host[2]))
                self.assertEqual(got[2], host[2], 'error output')
                self.assertEqual(got[1], host[1], 'output')
                self.assertEqual(sorted(got[3]), sorted(host[3]), 'files written')
                for name in host[3]:
                    self.assertTrue(got[3][name] == host[3][name], name + ' differs')
        if os.environ.get('LATHE_LATHEC_REPORT') == '1':
            print()
            for key in sorted(counts):
                print('%-9s %-8s %-8s %4d' % (key + (counts[key],)))
            print('%d of %d inputs compared' % (len(picked), len(self.corpus.items)))
        self.assertGreater(sum(1 for n in picked if fits(self.corpus.items[n], self.host[n])), 0)

    @unittest.skipIf(FULL, 'the inputs are sized for the small build')
    def test_every_error_number_is_reached_by_an_input_that_fits(self):
        """Each error the compiler can report (err.py's E_ numbers) is the error of some input
        that fits, but those in NOT_REPORTED."""
        import err
        numbers = {getattr(err, n) for n in dir(err) if n.startswith('E_')}
        reached = set()
        for item, host in zip(self.corpus.items, self.host):
            m = ERROR.search(host[2])
            if m and fits(item, host):
                reached.add(int(m.group(1)))
        if os.environ.get('LATHE_LATHEC_REPORT') == '1':
            print('\n%d of %d error numbers reached; not: %s'
                  % (len(numbers & reached), len(numbers), sorted(numbers - reached)))
        self.assertEqual(sorted(numbers - reached), sorted(NOT_REPORTED))

    @unittest.skipIf(FULL, 'the inputs are sized for the small build')
    def test_the_inputs_that_fit_reach_the_statements_of_decl_and_lathec(self):
        """The statements of decl.py and lathec.py that the inputs which fit run on the host
        side, at the small capacities: those the Lathe-written compiler is tested on. With
        LATHE_LATHEC_COVERAGE=1 it prints how many, and those not reached."""
        import decl
        import lathec
        items = [i for i, h in zip(self.corpus.items, self.host) if fits(i, h)]
        reached = reached_lines(items, self.dir, (decl, lathec))
        missed = {}
        for module in (decl, lathec):
            lines = executable_lines(module)
            missed[module.__name__] = [lines[n] for n in sorted(set(lines) - reached[module.__file__])]
            if os.environ.get('LATHE_LATHEC_COVERAGE') == '1':
                print('\n%d of %d statements of %s reached' % (len(lines) - len(missed[module.__name__]),
                                                              len(lines), os.path.basename(module.__file__)))
                for m in missed[module.__name__]:
                    print('   ', m)
        self.assertEqual(missed, UNREACHED)


# The error numbers no input that fits gives, and why.
NOT_REPORTED = {
    54: 'E_NEEDS_RT: no part of the compiler reports it',
    77: 'too many fix-ups in one function: the small build\'s function buffer is full first',
    79: 'too many operands: the nesting limit (error 88) comes first, as test_src_expr.py says',
    81: 'too many sources: inline expansions nest at most inline.MAX_DEPTH deep, below it',
    99: 'a fault in the compiler',
}


# The statements of decl.py and lathec.py that no input that fits reaches, and why.
UNREACHED = {'decl': [
    # The end of a function with a result must not be reachable: a `return` after err.fatal().
    ('open_interface', 'return 0'),
    ('register', 'return gen.REG_NONE'),
    # Ten functions of initial values written out early need 320 variables with initial
    # values: their names do not fit the small build's name heap.
    ('init_symbol', 'kernel.name_add(C_ZERO + number // 10)'),
], 'lathec': []}


# ---- The corpus on the BBC (LATHE_LATHEC_BBC=1) ---------------------------------------------

BBC = os.environ.get('LATHE_LATHEC_BBC') == '1'


def run_host_full(item, work):
    """(status, output, error output, {file: bytes}) of the host compiler at full size."""
    kind, path, args, files = item
    with tempfile.TemporaryDirectory(dir=work) as disk:
        before = fill(disk, files)
        done = subprocess.run([sys.executable, os.path.join(LATHE, 'host', 'lathec.py')] + args,
                              cwd=disk, capture_output=True)
        return done.returncode, done.stdout, done.stderr, outputs(disk, before)


def run_bbc(image, item, work):
    """(status, output, what the MOS said, {file: bytes}) of the compiler in the ROM form on
    the BBC (test_bbc_selfhost.report_run), or an exception's text in place of the output."""
    import test_bbc_selfhost as bbc_selfhost
    kind, path, args, files = item
    with tempfile.TemporaryDirectory(dir=work) as disk:
        fill(disk, files)
        try:
            got = bbc_selfhost.report_run('rom', image, disk, args)
        except Exception as e:      # an argument the BBC's command line cannot carry
            return None, str(e).encode(), b'', {}
        return got[:4]


# The inputs that cannot give the host's output on the BBC, and why: the emulator's filing
# system has no directories (a name with "/" is the error Bad name, which bbc.open catches, so
# the file is not there), and the module copies a tail of 239 bytes at most (bbc.md).
BBC_DIFFERENT = {
    'a source in a directory': 'no directories: sub/m.lth cannot be opened (error 62)',
    'an import directory': 'no directories: lib/k.li cannot be opened (error 50)',
    'a file name too long (83)': 'its command line is 248 bytes, more than the 239 *LATHE copies',
}


@unittest.skipUnless(BBC, 'LATHE_LATHEC_BBC=1 runs the corpus on the BBC')
class OnTheBBC(unittest.TestCase):
    """Every input, as LATHE_BANKED_ALL=1 runs them on Wendy 2, compiled by the compiler at full
    size in the ROM form on the BBC Model B+128 (test_bbc_selfhost.build_rom: `*LATHE ARGS` with
    --bbc-strict), against the host compiler at full size. On the BBC the error output is the
    output, so the host's two streams are joined. The inputs that do not agree are listed with
    why (BBC_DIFFERENT); LATHE_LATHEC_REPORT=1 prints them and the count that agrees."""

    @classmethod
    def setUpClass(cls):
        import test_bbc_selfhost as bbc_selfhost
        cls.dir = tempfile.mkdtemp(prefix='lathe-src-lathec-bbc-')
        rom = os.path.join(cls.dir, 'rom')
        os.makedirs(rom)
        cls.image = bbc_selfhost.build_rom(rom)
        cls.corpus = Corpus(os.path.join(cls.dir, 'corpus'))
        with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
            cls.host = list(pool.map(lambda i: run_host_full(i, cls.dir), cls.corpus.items))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_the_compiler_on_the_bbc_gives_the_host_compilers_output(self):
        items = self.corpus.items
        with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
            got = list(pool.map(lambda i: run_bbc(self.image, i, self.dir), items))
        same = 0
        differ = []
        for item, host, bbc in zip(items, self.host, got):
            kind, path, args, files = item
            name = path if kind == 'made' else os.path.relpath(path, LATHE)
            want = (host[0], host[1] + host[2], b'', host[3])
            if bbc == want:
                same += 1
                continue
            differ.append((name, bbc, want))
        if os.environ.get('LATHE_LATHEC_REPORT') == '1':
            print()
            for name, bbc, want in differ:
                print('%s: BBC %r, host %r' % (name, bbc[:3], want[:3]))
            print('%d of %d inputs agree on the BBC' % (same, len(items)))
        self.assertEqual(sorted(name for name, bbc, want in differ), sorted(BBC_DIFFERENT))
        self.assertEqual(same, len(items) - len(BBC_DIFFERENT))


def executable_lines(module):
    """{line: (function, its text)} of the lines of a host module that hold a statement inside
    a function (as test_src_expr.py counts them)."""
    import ast
    with open(module.__file__) as f:
        text = f.read()
    source = text.split('\n')
    lines = {}
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.FunctionDef):
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.stmt) and not isinstance(stmt, (ast.FunctionDef, ast.Global)) \
                        and not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)):
                    lines[stmt.lineno] = (node.name, source[stmt.lineno - 1].strip())
    return lines


def reached_lines(items, work, modules):
    """{path: lines run} of the host modules `modules` over the inputs `items`, compiled in this
    process at the small capacities as lathec_small.py compiles them."""
    import script_host
    import lathec
    paths = {m.__file__: set() for m in modules}

    def tracer(frame, event, arg):
        hit = paths.get(frame.f_code.co_filename)
        if hit is None:
            return None
        if event in ('call', 'line'):
            hit.add(frame.f_lineno)
        return tracer
    here = os.getcwd()
    old = sys.gettrace()
    try:
        for kind, path, args, files in items:
            with tempfile.TemporaryDirectory(dir=work) as disk:
                fill(disk, files)
                os.chdir(disk)
                sys.settrace(tracer)
                try:
                    script_host.host_run(lathec.main, args, True)
                finally:
                    sys.settrace(old)
                    os.chdir(here)
    finally:
        sys.settrace(old)
    return paths


if __name__ == '__main__':
    unittest.main()
