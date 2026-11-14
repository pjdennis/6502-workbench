"""The whole linker written in Lathe (lathe/src/link.lth and the twins it imports), built banked
with lathe/src/linker-bank.env and run on emulated Wendy 2 with files (lk_banked.py), against the
host linker (lathe/host/link.py) over the host modules at the same capacities (lk_small.py).

Each case is a real link: an environment file, object files and the linker's command line. The
banked linker runs in a directory holding the case's files, the host linker in another; the
error output, the exit status and every file each writes (the image, the map, the bank and
overlay files) must be identical, byte for byte. The cases:

    programs        the end-to-end corpus built by build.py with its link recorded: every case of
                    tests/cases/e2e (the default machine), e2e-michael, e2e-wendy2, e2e-wendy2disk,
                    each configuration of e2e-config (banks, overlays, regions, interrupts),
                    lathe/src/lextest.lth, and the link errors of tests/cases/linkerr
    links           every link the linker's own tests make (test_src_lk.recorded_links), good and
                    bad: test_lk_errors, test_lk_windows and the others; but for the two whose
                    command line the board cannot give (cannot_be_given): one names files in
                    directories, one has 41 object files, more than disk.lth's 256 bytes of
                    arguments hold
    by hand         test_src_lk's links made by hand and its graph links, and edge_links below, for
                    what the others do not reach of placement, fix-ups, the map and the image
    synthetic       lk_synthetic's program at the largest size the small build links, and one
                    size larger, which both must refuse alike

By default a representative part runs (SUBSET below; every tenth of the recorded links and
every third of test_src_lk's links made by hand; the graph links, edge_links and the synthetic
pair); LATHE_LK_ALL=1 runs everything. With LATHE_LK_COVERAGE=1
the lines of lk_fix, lk_place, lk_map, lk_emit and link that the host runs reach are printed (the
Lathe runs take the same paths, since every output agrees).
"""
import collections
import concurrent.futures
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import src_support as support
import lk_banked
import lk_small
import link
import test_src_lk as lk

ALL = os.environ.get('LATHE_LK_ALL') == '1'
CASES = os.path.join(support.LATHE, 'tests', 'cases')
MODULES = ('lk_fix', 'lk_place', 'lk_map', 'lk_emit', 'link')

# The programs of the default run: one of each kind (source relative to lathe/, environment).
SUBSET = [
    ('src/lextest.lth', 'src/compiler.env'),
    ('tests/cases/e2e/fp_dispatch.lth', 'host'),
    ('tests/cases/e2e/rec_eval.lth', 'host'),
    ('tests/cases/e2e-michael/irq_shared.lth', 'michael'),
    ('tests/cases/e2e-wendy2/ticks.lth', 'wendy2'),
    ('tests/cases/e2e-wendy2disk/copy.lth', 'wendy2disk'),
    ('tests/cases/e2e-config/farcall.lth', 'tests/cases/e2e-config/farcall_banks.env'),
    ('tests/cases/e2e-config/farcall.lth', 'tests/cases/e2e-config/farcall_ovl.env'),
    ('tests/cases/e2e-config/regions.lth', 'tests/cases/e2e-config/regions_banks.env'),
    ('tests/cases/e2e-config/withirq.lth', 'tests/cases/e2e-config/withirq_banks.env'),
    ('tests/cases/linkerr/unmarked_cycle.lth', 'host'),
]


def headers(path, word):
    """The words of each of a case's `; WORD ...` lines before `module`."""
    found = []
    with open(path) as f:
        for line in f:
            if line.startswith('module'):
                break
            if line.startswith('; %s ' % word):
                found.append(line[len('; %s ' % word):].split())
    return found


def is_case(path):
    with open(path) as f:
        return not os.path.basename(path).startswith('lib') and not f.read().startswith('; imported by')


def corpus():
    """Every program of the end-to-end corpus: [(source relative to lathe/, environment)]."""
    found = [('src/lextest.lth', 'src/compiler.env')]
    for kind, env in (('e2e', 'host'), ('e2e-michael', 'michael'), ('e2e-wendy2', 'wendy2'),
                      ('e2e-wendy2disk', 'wendy2disk'), ('linkerr', 'host')):
        for p in sorted(glob.glob(os.path.join(CASES, kind, '*.lth'))):
            if is_case(p):
                found.append((os.path.relpath(p, support.LATHE), env))
    for p in sorted(glob.glob(os.path.join(CASES, 'e2e-config', '*.lth'))):
        if is_case(p):
            for words in headers(p, 'config'):
                e = os.path.join(os.path.dirname(p), words[0])
                found.append((os.path.relpath(p, support.LATHE),
                              os.path.relpath(e, support.LATHE) if os.path.isfile(e) else words[0]))
    return found


def program_case(source, env_name, work):
    """Build a program with build.py, keeping what its link was given, whether the link succeeds
    or fails (test_src_lk.program_case, for a link error too)."""
    import build
    d = tempfile.mkdtemp(dir=work)
    rec = os.path.join(d, 'recorder.py')
    with open(rec, 'w') as f:
        f.write(lk.RECORDER)
    e = env_name if '/' not in env_name else os.path.join(support.LATHE, env_name)
    defines = []
    for words in headers(os.path.join(support.LATHE, source), 'defines'):
        for w in words:
            defines += ['--define', w]
    environ = dict(os.environ, LK_RECORD=d, LK_REAL=build.LINKER, LATHE_LINKER=rec)
    r = subprocess.run([sys.executable, os.path.join(support.DRIVER, 'build.py'),
                        os.path.join(support.LATHE, source), '-o', os.path.join(d, 'o.bin'), '--env', e]
                       + defines, env=environ, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if not os.path.isfile(os.path.join(d, 'link.json')):
        raise AssertionError('build of %s did not link: %s' % (source, r.stderr.decode()[-500:]))
    with open(os.path.join(d, 'link.json')) as f:
        j = json.load(f)
    files = {name: text.encode('latin-1') for name, text in j['files'].items()}
    return lk.Case('%s %s' % (source, env_name), files, ['env', j['main'], 'out.bin', 'out.map'] + j['objects'])


def host_link(case, d):
    """The host linker at the small capacities on the case, in directory d: (status, error output,
    the files it wrote)."""
    for name, data in case.files.items():
        os.makedirs(os.path.dirname(os.path.join(d, name)), exist_ok=True)
        with open(os.path.join(d, name), 'wb') as f:
            f.write(data)
    status, _, err = lk.host_run(link.main, case.args, d)
    written = {k: v for k, v in lk_banked.files_of(d).items() if case.files.get(k) != v}
    return status, err, written


def kind_of(title):
    """What kind of link a case's title names, for the counts LATHE_LK_ALL prints."""
    parts = title.split()
    if '/' not in parts[0]:
        return title.split(' ')[0] if title.startswith(('link ', 'lk_synthetic')) else 'by hand'
    d = os.path.basename(os.path.dirname(parts[0]))
    return d if d != 'src' else 'lextest'


COUNTS = collections.Counter()      # cases linked identically, by kind


def compare(test, image, cases, work, results=None):
    """Link every case with the banked linker (in parallel) and with the host linker, and compare
    all they give. Returns the number of cases; `results`, if given, gets (title, status, cycles)
    for each."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        lathe = list(pool.map(lambda c: lk_banked.run(image, c.files, c.args), cases))
    for n, (case, (status, err, written, cycles)) in enumerate(zip(cases, lathe)):
        d = os.path.join(work, 'h%d' % n)
        os.makedirs(d)
        host = host_link(case, d)
        if results is not None:
            results.append((case.title, status, cycles))
        with test.subTest(case=case.title):
            test.assertEqual(err.decode('latin-1'), host[1].decode('latin-1'))
            test.assertEqual(status, host[0])
            test.assertEqual(sorted(written), sorted(host[2]))
            for name in written:
                if written[name] != host[2][name]:
                    test.fail('%s differs: %s' % (name, lk.first_difference(written[name], host[2][name])))
            COUNTS[(kind_of(case.title), 'refused' if status else 'linked')] += 1
    return len(cases)


def edge_links():
    """Links for what placement, the fix-ups, the map and the image reach that the other links do
    not: bad fix-ups, slots of dropped functions, a call through a pointer inside a `with` block,
    a variable kept off a page boundary in a bank, slot numbers of three digits, class parameters
    named by their CLAS records: [(title, env, objects, main)]."""
    from test_lk_support import (HOST_ENV, Obj, routine, string, word, record, EITHER, NEVER, PARAM,
                                 POINTER, NOBODY)
    import test_lk_windows as tw
    found = []

    def case(title, env_text, *objects, main=None):
        found.append((title, env_text, [o.to_bytes() for o in objects], main or objects[0].name))

    def with_code(o, build_rest):
        """main in Obj o: code from build_rest(c), then RTS."""
        c = o.code()
        build_rest(c)
        c.raw(0x60)
        return c

    # lk_fix: the fix-ups of constant data and of code that name what they cannot.
    o = Obj('t')
    o.var('x', 1)
    o.data('table', b'\0' * 300, [(i, 2, o.v('x'), 0xFF, 0) for i in range(257)])
    o.func('main', with_code(o, lambda c: c.abs(0xAD, o.d('table'))))
    case('constant data with more fix-ups than are held', HOST_ENV, o)
    o = Obj('t')
    o.var('x', 1)
    o.data('table', b'\0\0', [(0, 7, o.v('x'), 0xFF, 0)])
    o.func('main', with_code(o, lambda c: c.abs(0xAD, o.d('table'))))
    case('a fix-up of kind 7 in constant data', HOST_ENV, o)
    o = Obj('t')
    routine(o, 'dropped', slots=[(1, EITHER, 0, PARAM, 'p')])
    routine(o, 'kept', slots=[(2, NEVER, 0, PARAM, 'q')])
    o.data('table', b'\0\0\0\0', [(0, 1, o.f('dropped'), 0, 0), (2, 1, o.f('kept'), 0, 1)])
    o.func('main', with_code(o, lambda c: (c.abs(0xAD, o.d('table')), c.abs(0x20, o.f('kept')))),
           calls=[(o.f('kept'), 0, NOBODY)])
    case('constant data that names slots of a dropped function and of a kept one', HOST_ENV, o)
    o = Obj('t')
    o.var('x', 1)
    o.func('main', with_code(o, lambda c: c.abs(0xAD, o.v('x'), slot=0)))
    case('a fix-up that names a slot of a variable', HOST_ENV, o)
    o = Obj('t')
    o.clas('k', [1])
    o.func('main', with_code(o, lambda c: c.abs(0xAD, o.k('k'), slot=3)))
    case('a fix-up that names a parameter a class lacks', HOST_ENV, o)
    o = Obj('t')
    o.clas('k', [2])
    o.func('main', with_code(o, lambda c: c.abs(0xAD, o.k('k'), slot=0)))
    case('a fix-up that names a parameter of a class nothing calls through', HOST_ENV, o)
    o = Obj('t')
    o.func('main', with_code(o, lambda c: c.byte(0xA9, 6, o.f('main'))))
    case('a fix-up of kind 6 that names a function', HOST_ENV, o)

    # lk_emit: fix-ups in the wrong place in code and in constant data.
    o = Obj('t')
    o.var('x', 1)
    c = o.code()
    c.fixes.append((0, 2, o.v('x'), 0xFF, 0))
    c.raw(0xEA, 0x60)
    o.func('main', c)
    case('a fix-up at an opcode', HOST_ENV, o)
    o = Obj('t')
    o.var('x', 1)
    c = o.code()
    c.fixes.append((2, 1, o.v('x'), 0xFF, 0))
    c.raw(0x20, 0, 0, 0x60)
    o.func('main', c)
    case('a two-byte fix-up at the high byte of an operand', HOST_ENV, o)
    o = Obj('t')
    o.var('x', 1)
    o.data('table', b'\0\0', [(0, 2, o.v('x'), 0xFF, 0), (0, 2, o.v('x'), 0xFF, 0)])
    o.func('main', with_code(o, lambda c: c.abs(0xAD, o.d('table'))))
    case('two fix-ups of constant data at one offset', HOST_ENV, o)
    o = Obj('t')
    o.var('x', 1)
    o.data('table', b'\0\0', [(0, 5, o.v('x'), 0xFF, 0)])
    o.func('main', with_code(o, lambda c: c.abs(0xAD, o.d('table'))))
    case('a fix-up of kind 5 in constant data', HOST_ENV, o)
    o = Obj('t')
    o.var('x', 1)
    o.data('table', b'\0\0', [(4, 2, o.v('x'), 0xFF, 0)])
    o.func('main', with_code(o, lambda c: c.abs(0xAD, o.d('table'))))
    case('a fix-up of constant data after its end', HOST_ENV, o)

    # lk_map: three-digit slot numbers; class parameters named by CLAS records, and by those of
    # a class merged into another.
    o = Obj('t')
    o.func('main', slots=[(1, NEVER, 0, PARAM, 's%d' % i) for i in range(101)])
    case('a function with 101 slots', HOST_ENV, o)
    o = Obj('t')
    o.clas('k', [1, 2], names=['first', 'second'])
    routine(o, 'g', slots=[(1, EITHER, 0, PARAM, 'p'), (2, EITHER, 0, PARAM, 'q')])
    routine(o, 'main', calls=[('k', POINTER, None)])
    o.memb('k', 'g')
    case('a live class whose CLAS record names its parameters', HOST_ENV, o)
    o = Obj('t')
    o.clas('k0', [1])
    o.clas('k1', [1], names=['named'])
    routine(o, 'g', slots=[(1, EITHER, 0, PARAM, 'p')])
    routine(o, 'main', calls=[('k0', POINTER, None)])
    o.memb('k0', 'g')
    o.memb('k1', 'g')
    case('a class merged into another names its parameter', HOST_ENV, o)
    o = Obj('t')
    for i in range(250):
        o.func('f%d' % i)
        o.var('v%d' % i, 1)
    o.func('main', slots=[(1, NEVER, 0, PARAM, 's')])
    case('an object file with more symbols than the image pass holds names of', HOST_ENV, o)

    # lk_place: a call through a pointer inside a `with` block; a bank of the window that has no
    # file and no region's data; a word variable kept off a page boundary at a bank's top.
    t = tw.user()
    k = len(t.numbers)                  # t.cls, whose SYM and CLAS records go before main's FUNC
    at = [r[0] for r in t.records].index(7)
    t.records[at:at] = [record(3, bytes((4,)) + string('t.cls')), record(13, word(k) + bytes((0, 1)) + word(1) + string(''))]
    at = [r[0] for r in t.records].index(10)
    t.records[at:at] = [record(9, word(k) + bytes((POINTER | tw.WITH,)) + word(NOBODY))]
    a = Obj('a')
    routine(a, 'h', slots=[(1, EITHER, 0, PARAM, 'p')])
    a.memb('t.cls', 'h')
    case('a call through a pointer inside a with block reaches a member in a window',
         tw.REGIONS + 'place a WIN 1\n', t, a, tw.farcall_with())
    case('a bank without a file that holds nothing',
         tw.ENV + tw.WINDOW + 'bank WIN 2 $12\nplace a WIN 1\nfarcall fc\n', tw.caller(), tw.banked(),
         tw.farcall())
    m = Obj('m')
    m.var('x', 255, NEVER)
    m.var('y', 2, NEVER)
    m.func('f', with_code(m, lambda c: (c.abs(0xAD, m.v('x')), c.abs(0xAD, m.v('y')))))
    t = Obj('t')
    t.func('main', with_code(t, lambda c: c.abs(0x20, t.f('m.f'))), calls=[(t.f('m.f'), 0, NOBODY)])
    case('a word variable at the top of a bank that would lie across a page',
         tw.ENV + tw.WINDOW + 'place m WIN 1\nfarcall fc\n', t, m, tw.farcall())

    # link: no main function, named in capitals.
    o = Obj('t')
    o.func('other')
    case('no main function, the module named in capitals', HOST_ENV, o, main='T')
    return found


ARGS_SIZE = 256         # lathe/rt/disk.lth: bytes of the arguments, each one's zero included
MAX_ARGS = 48


def cannot_be_given(case):
    """True if the case's command line cannot be given on the board: it names a file in a
    directory, which the file ports do not have (every file is in the one directory of --disk), or
    it is longer than disk.lth holds, which drops the rest."""
    return (any('/' in str(a) for a in case.args) or len(case.args) > MAX_ARGS
            or sum(len(str(a)) + 1 for a in case.args) > ARGS_SIZE)


class WholeLinker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-src-link-')
        cls.image = lk_banked.build_linker(cls.dir)
        cls.trace = None
        if os.environ.get('LATHE_LK_COVERAGE'):
            cls.trace = lk.Coverage()
            cls.trace.files = {os.path.join(support.LATHE, 'host', m + '.py'): m for m in MODULES}
            cls.trace.hit = {m: set() for m in MODULES}
            cls.trace.start()

    @classmethod
    def tearDownClass(cls):
        if cls.trace:
            cls.trace.stop()
            cls.trace.report()
        if ALL:
            print('\nlinked identically: ' + ', '.join('%s %s %d' % (k, how, n)
                                                       for (k, how), n in sorted(COUNTS.items())))
        lk_small.load(False)
        shutil.rmtree(cls.dir, ignore_errors=True)

    def work(self):
        return tempfile.mkdtemp(dir=self.dir)

    def test_programs(self):
        chosen = corpus() if ALL else SUBSET
        work = self.work()
        with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
            cases = list(pool.map(lambda p: program_case(p[0], p[1], work), chosen))
        self.assertEqual(compare(self, self.image, cases, self.work()), len(chosen))

    def test_the_limits_of_the_command_line_are_disks(self):
        import re
        with open(os.path.join(support.LATHE, 'rt', 'disk.lth')) as f:
            text = f.read()
        self.assertEqual(int(re.search(r'^const MAX_ARGS = (\d+)', text, re.M).group(1)), MAX_ARGS)
        self.assertEqual(int(re.search(r'^const ARGS_SIZE = (\d+)', text, re.M).group(1)), ARGS_SIZE)

    def test_links_of_the_linkers_tests(self):
        links = lk.recorded_links()
        cases = [lk.link_case('link %d' % i, e, objects, main, args)
                 for i, (e, objects, main, args) in enumerate(links) if ALL or i % 10 == 0]
        cases = [c for c in cases if not cannot_be_given(c)]
        self.assertGreater(compare(self, self.image, cases, self.work()), 200 if ALL else 20)

    def test_links_made_by_hand(self):
        from test_lk_support import HOST_ENV
        cases = [lk.link_case(title, HOST_ENV, objects, main)
                 for i, (title, objects, main) in enumerate(lk.hand_made_links()) if ALL or i % 3 == 0]
        cases += [lk.link_case(title, e, objects, main) for title, e, objects, main in lk.graph_links()]
        cases += [lk.link_case(title, e, objects, main) for title, e, objects, main in edge_links()]
        self.assertGreater(compare(self, self.image, cases, self.work()), 55 if ALL else 35)

    def test_the_synthetic_program_at_the_largest_size_and_one_larger(self):
        fits, over = lk.synthetic_case(lk.SYNTHETIC_FITS), lk.synthetic_case(lk.SYNTHETIC_OVER)
        results = []
        self.assertEqual(compare(self, self.image, [fits, over], self.work(), results), 2)
        self.assertEqual([r[1] for r in results], [0, 1])


if __name__ == '__main__':
    unittest.main()
