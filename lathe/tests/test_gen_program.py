"""Generated programs of real size (lathe/tests/gen_program.py), compiled and linked on the 32K
Model B (lathe/docs/bbc.md, "A program of real size on the 32K Model B").

By default:

- the generator is deterministic, and its programs have the shape it says (the code a function,
  the calls a function) when the host compiles them;
- a small program, built by the host's tools for the BBC and run on the emulated B+128, prints
  what the generator computed for it;
- each of its modules compiles with the host compiler at the 32K form's capacities
  (lathec_ram32.py), and the program links with the host linker at the 32K build's (lk_ram32).

With LATHE_BBC_RAM32_PROGRAMS=1, the programs of about 8, 16 (a mode 4 screen: $1900-$57FF), 20
and 25 KB (mode 7: $1900-$7BFF) on boards.BOARDS['bbc32'] (the Model B, the DFS's names, filled
memory, strict), from the 32K image (test_bbc_ram32.build_image): every module compiled by
*LATHE, the objects and interfaces on drive 1, linked by *LLINK @LINKARG, the image *SAVEd and
run; every file the host tools' and the output what the generator computed.
LATHE_BBC_RAM32_REPORT=1 prints the account of each (the tightest tables, cycles, the disc).
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import src_support as support  # noqa: E402
import bbcfs  # noqa: E402
import boards  # noqa: E402
import build  # noqa: E402
import gen_program  # noqa: E402
import lk_ram32  # noqa: E402
import test_bbc_dfs as dfs  # noqa: E402

PROGRAMS = os.environ.get('LATHE_BBC_RAM32_PROGRAMS') == '1'
REPORT = os.environ.get('LATHE_BBC_RAM32_REPORT') == '1'
HAVE_TOOLS = os.path.isfile(support.EMULATOR) and os.path.isfile(build.COMPILER)
RAM32_COMPILER = os.path.join(HERE, 'lathec_ram32.py')
DFS_ENV = os.path.join(support.LATHE, 'env', 'bbc-dfs.env')
LINK_FILE = 'LINKARG'

# The targets: (name, modules, functions a module, screen mode whose memory it must fit, body).
# A side of a DFS disc holds 31 files: the program's modules, the main and the four run-time
# modules each write an object and an interface on drive 1, so a program has at most 10 modules
# of its own. The first three have the generator's usual functions (about 130 bytes, 3 calls);
# the 25 KB program fewer and larger (body 4: about 145 bytes, the same calls), since at the usual
# size it is more functions, slots and calls than the 32K linker holds (link error 13, the calls).
TARGETS = (('8 KB', 3, 22, 4, None), ('16 KB', 6, 21, 4, None), ('20 KB', 7, 23, 7, None),
           ('25 KB', 8, 17, 7, 4))


def target_env(path, size, mode):
    """bbc-dfs.env with the code from PAGE to the end of a program of `size` (code, variables), the
    data from there to HIMEM in `mode`: path, or None if it does not fit."""
    split = lk_ram32.PAGE + size[0]
    if split + size[1] >= lk_ram32.HIMEM[mode]:       # the code below HIMEM, and the variables after it
        return None
    with open(DFS_ENV) as f:
        text = f.read()
    text, n = re.subn(r'(?m)^code\s.*$', 'code      $%04X $%04X' % (lk_ram32.PAGE, split - 1), text)
    assert n == 1
    text, n = re.subn(r'(?m)^data\s.*$', 'data      $%04X $%04X' % (split, lk_ram32.HIMEM[mode] - 1), text)
    assert n == 1
    with open(path, 'w') as f:
        f.write(text)
    return path


def measure_env(path):
    """bbc-dfs.env with room for any size, to measure a program."""
    with open(DFS_ENV) as f:
        text = f.read()
    text = re.sub(r'(?m)^code\s.*$', 'code      $1900 $BFFF', text)
    text = re.sub(r'(?m)^data\s.*$', 'data      $C000 $FFF0', text)
    with open(path, 'w') as f:
        f.write(text)
    return path


def link_order(objects):
    """The objects as the link reads them: the run-time library's (rt_*) first. A module's WGT
    record weights the parameters of the functions it calls; for a function not read yet the
    weight waits in a table of 16 in the linker's 32K build (lk_scan.MAX_PENDING), which a program
    whose every module multiplies and divides fills when rt_math, which build.py lists last, is
    read after them (link error 41). Read first, nothing waits."""
    first = [o for o in objects if os.path.basename(o).startswith('rt_')]
    return first + [o for o in objects if o not in first]


def compiler_use(steps, work):
    """Each module compiled by the host compiler at the 32K form's capacities, in a process of its
    own, with the peak use of its tables: [(module, status, error output, {table: peak})]."""
    found = []
    out = os.path.join(work, 'ram32')
    os.makedirs(out, exist_ok=True)
    for kind, options, path in [s for s in steps if s[0] == 'compile']:
        name = os.path.basename(path)              # as the BBC compiles it: `NAME.lth .`, the source beside
        shutil.copy(path, os.path.join(out, name))
        r = subprocess.run([sys.executable, os.path.abspath(__file__), '--gauge', '.', name] + list(options),
                           capture_output=True, text=True, cwd=out)
        lines = r.stdout.strip().splitlines()
        use = json.loads(lines[-1]) if lines and lines[-1].startswith('{') else {}
        found.append((build.module_name(path), r.returncode, r.stderr.strip(), use))
    return found


def gauge_main(argv):
    """In a process of its own: the host compiler at the 32K capacities on argv[1] into argv[0],
    with options argv[2:]; prints the peak use of its tables as JSON (memory_report's gauges)."""
    import importlib
    import script_host
    import memory_report as rep
    for module, const, size in script_host.ram32_capacities():
        setattr(importlib.import_module(module), const, size)
    import kernel
    import fbuf
    import lex
    peaks, where = {}, {}
    for name, attrs, functions, use in rep.gauges():
        for a in attrs:
            peaks[(name, a)] = 0
    peaks[('out', 'table')] = 0
    rep.install_gauges(peaks, where)
    status = rep.compile_one(argv[1], argv[0], argv[2:])
    import env
    sys.stderr.write(env._err.getvalue().decode('latin-1') + env._out.getvalue().decode('latin-1'))
    use = {'names': (peaks[('kernel', 'names')], kernel.NAME_HEAP_SIZE),
           'symbols': (peaks[('kernel', rep.SYM_COLUMNS[0])], kernel.MAX_SYMS),
           'function buffer': (peaks[('fbuf', 'buffer')], fbuf.BUFFER_SIZE),
           'string': (peaks[('lex', 'string')], lex.MAX_STRING)}
    print(json.dumps({k: list(v) for k, v in use.items()}))
    sys.exit(status)


def tightest(use):
    """The table of `use` {table: (peak, size)} with the least room left, as text."""
    name, (peak, size) = min(use.items(), key=lambda e: (e[1][1] - e[1][0]) / e[1][1])
    return '%s %d of %d' % (name, peak, size)


class rt_first:
    """While in force, build.py's links read the objects in link_order."""
    def __enter__(self):
        self.real = build.run

        def run(cmd, what, cwd=None):
            if cmd[1] == build.LINKER:
                cmd = cmd[:6] + link_order(cmd[6:])
            return self.real(cmd, what, cwd)
        build.run = run

    def __exit__(self, *exc):
        build.run = self.real


def recorded(main, env, work):
    """test_bbc_toolchain.recorded, the link's objects in link_order."""
    import test_bbc_toolchain as toolchain
    with rt_first():
        steps = toolchain.recorded(main, env, work)
    return steps[:-1] + [steps[-1][:3] + (link_order(steps[-1][3]),)]


def make(work, modules, functions, mode, calls=2.0, seed=1, body=None):
    """A generated program in work/src, measured and given an environment that fits `mode`:
    (main path, environment path or None if it does not fit, (code, variables), the program)."""
    p = gen_program.Program(modules, functions, calls, seed, body)
    main = p.write(os.path.join(work, 'src'))
    measured = os.path.join(work, 'measure')
    with rt_first():
        build.build(main, os.path.join(work, 'measure.bin'), env=measure_env(os.path.join(work, 'measure.env')),
                    keep=measured)
    size = lk_ram32.link_size(os.path.join(measured, 'genmain.map'))
    env = target_env(os.path.join(work, 'genmain.env'), size, mode)
    return main, env, size, p


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class Generated(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-gen-program-')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_the_same_seed_gives_the_same_program(self):
        a, b = gen_program.Program(3, 10, seed=5), gen_program.Program(3, 10, seed=5)
        self.assertEqual([a.source(m) for m in a.modules], [b.source(m) for m in b.modules])
        self.assertEqual(a.evaluate(), b.evaluate())
        c = gen_program.Program(3, 10, seed=6)
        self.assertNotEqual([a.source(m) for m in a.modules], [c.source(m) for m in c.modules])

    def test_a_small_program_runs_as_the_generator_computed_and_fits_the_32k_tools(self):
        import test_bbc_toolchain as toolchain
        work = os.path.join(self.dir, 'small')
        main, env, size, p = make(work, 3, 12, 4)
        image = os.path.join(work, 'IMAGE')
        build.build(main, image, env=env, keep=os.path.join(work, 'build'))
        status, out, err = build.run_program(image, env, [])
        with open(os.path.join(work, 'src', 'genmain.expected.out'), 'rb') as f:
            self.assertEqual((status, out, err), (0, f.read(), b''))
        shape = lk_ram32.shape(sorted(glob.glob(os.path.join(work, 'build', 'gen0*.lo'))))
        self.assertTrue(80 <= shape['code a function'] <= 160, shape)
        self.assertTrue(2.0 <= shape['calls a function'] <= 4.0, shape)
        steps = recorded(main, env, os.path.join(work, 'steps'))
        for name, status, said, use in compiler_use(steps, work):
            with self.subTest(module=name):
                self.assertEqual((status, said), (0, ''))
        link = steps[-1]
        status, said, use, linked = lk_ram32.host_link(2, link[1], link[2], list(link[3]))
        self.assertEqual((status, said), (0, ''))


# ---- On the Model B -----------------------------------------------------------------------------

def model_b(case, image, work, main, env, expected):
    """The tool chain on the 32K Model B, from the 32K image, under the DFS's names: each module
    compiled by *LATHE with its object and interface on drive 1, *LLINK @LINKARG, the image *SAVEd
    and run. Every file written is the host's and the output `expected`. Returns {measure: value}."""
    import test_bbc_ram32 as ram32
    import test_bbc_toolchain as toolchain
    steps = recorded(main, env, os.path.join(work, 'steps'))
    disk = os.path.join(work, 'bbc')
    os.makedirs(disk)
    compiles, link = toolchain.lay_out(steps, disk)
    compiles = [c[:-1] + ['1'] for c in compiles]
    link = link[:4] + ['1/' + o for o in link[4:]]
    files = dfs.host_run(compiles, link, disk, os.path.join(work, 'host'), '1')
    dfs.to_dfs(disk)
    dfs.put(disk, LINK_FILE, (' '.join(link) + '\r').encode())
    before = dict(dfs.files_of(disk))
    tools = [boards.module_command('LATHE', args) for args in compiles]
    status, out, said, cycles_compiles, report = ram32.run(image, disk, tools)
    case.assertEqual((status, out, said), (0, b'', b''))
    status, out, said, cycles_link, report = ram32.run(image, disk, ['LLINK @' + LINK_FILE])
    case.assertEqual((status, out, said), (0, b'', b''))
    load = lk_ram32.PAGE
    lines = toolchain.bbc_lines(compiles, link, load, len(files[link[2]]))[len(compiles) + 1:]
    status, out, said, cycles_run, report = ram32.run(image, disk, lines)
    case.assertEqual((status, out, said), (0, expected, b''))
    written = {f: d for f, d in dfs.files_of(disk).items() if before.get(f) != d}
    want = {bbcfs.host_file(bbcfs.dfs_name(f)): data for f, data in files.items()}
    case.assertEqual(sorted(written), sorted(want))
    for f in want:
        case.assertTrue(written[f] == want[f], f + ' differs')
    return {'compiles': len(compiles), 'cycles compiles': cycles_compiles, 'cycles link': cycles_link,
            'cycles run': cycles_run, 'disc': dfs.catalogue(disk), 'image': len(files[link[2]]),
            'steps': steps, 'link': link}


@unittest.skipUnless(HAVE_TOOLS and PROGRAMS, 'LATHE_BBC_RAM32_PROGRAMS=1 compiles and links the programs on the Model B')
class OnTheModelB(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import test_bbc_ram32 as ram32
        cls.dir = tempfile.mkdtemp(prefix='lathe-gen-model-b-')
        cls.image = ram32.build_image(os.path.join(cls.dir, 'image'))[0]
        cls.rows = []
        cls.capacities = link_capacities()

    @classmethod
    def tearDownClass(cls):
        if REPORT:
            print('\n' + '\n'.join(cls.rows))
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_the_programs(self):
        for name, modules, functions, mode, body in TARGETS:
            with self.subTest(program=name):
                work = os.path.join(self.dir, name.replace(' ', ''))
                main, env, size, p = make(work, modules, functions, mode, body=body)
                self.assertIsNotNone(env, '%s: %r does not fit mode %d' % (name, size, mode))
                with open(os.path.join(work, 'src', 'genmain.expected.out'), 'rb') as f:
                    expected = f.read()
                result = model_b(self, self.image, work, main, env, expected)
                use = compiler_use(result['steps'], work)
                program = [u for u in use if u[0] == 'genmain' or u[0].startswith('gen')]
                link = result['steps'][-1]
                status, said, link_use, linked = lk_ram32.host_link(2, link[1], link[2], list(link[3]))
                room = lk_ram32.HIMEM[mode] - lk_ram32.PAGE - size[0] - size[1]
                shape = lk_ram32.shape(sorted(glob.glob(os.path.join(work, 'measure', 'gen*.lo'))))
                self.rows.append(
                    '%s (mode %d): %d modules of the program and the main, %d lines, %d functions (%.0f bytes '
                    'and %.1f calls a function); code and '
                    'constants %d, variables %d, %d bytes of $1900-$%04X left for data; %d compiles %.1f million '
                    'cycles (%.2f min at 2 MHz), the link %.1f million (%.2f min); the image %d bytes; the disc %r; '
                    'the compiler\'s tightest table, module by module: %s; the linker\'s: %s' % (
                        name, mode, modules + 1, p.lines(), p.functions(), shape['code a function'],
                        shape['calls a function'], size[0], size[1], room,
                        lk_ram32.HIMEM[mode] - 1, result['compiles'], result['cycles compiles'] / 1e6,
                        result['cycles compiles'] / 2e6 / 60, result['cycles link'] / 1e6,
                        result['cycles link'] / 2e6 / 60, result['image'], result['disc'],
                        ', '.join('%s %s' % (u[0], tightest(u[3])) for u in program if u[3]),
                        link_tightest(link_use or {}, self.capacities)))


def link_capacities():
    """{table: capacity} of the linker's 32K build (LKSMALL 2), from a process of its own, as
    lk_ram32.host_link measures the use (lk_memory_report.USAGE)."""
    code = ('import sys, json; sys.path.insert(0, %r); import lk_small; lk_small.load(2); '
            'import lk_memory_report as rep; names = dict(rep.modules()); '
            'print(json.dumps({t: eval(c, names) for t, _, u, c in rep.USAGE}))' % HERE)
    r = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, cwd=HERE)
    return json.loads(r.stdout)


def link_tightest(use, capacities):
    """The linker's three tightest tables, from lk_ram32.host_link's use."""
    rows = [(1 - use[t] / c, '%s %d of %d' % (t, use[t], c)) for t, c in capacities.items()
            if t in use and c and t not in ('classes', 'class params', 'members', 'contexts', 'objects')]
    return ', '.join(r[1] for r in sorted(rows)[:3])


if __name__ == '__main__':
    if sys.argv[1:2] == ['--gauge']:
        gauge_main(sys.argv[2:])
    else:
        unittest.main()
