"""Capacities set as a tool starts (lathe/docs/bbc.md, "Capacities set at start-up", "Two banks"):
in Image A (test_bbc_adapt.py) the placer gives the compiler's name heap, region NAMES, the largest
area of free memory left when the other regions are placed, all of it, and INLINE's saved tokens,
region TOKENS, from 768 to 2,048 bytes of main RAM's largest area or of the sideways RAM gap that
fits them closest; it writes in kernel.name_room and kernel.token_room how many bytes that is,
which the compiler tests where the other builds test NAME_HEAP_SIZE and SAVED_SIZE.

SameObjects: the host compiler with name heaps of many sizes, from the least a module compiles
with up, with room for 768 to 2,048 bytes of saved tokens, and with the heap begun at offsets
other than 1 (STARTS; lathec_heap.py), gives the same files for every module: what the compiler
writes does not depend on its capacities, nor on where in the heap its names begin (Image B's
compiler begins them at PAGE: test_bbc_image_b.py). By default the
quick modules of test_src_selfhost and a module of long names; LATHE_BBC_ROOMS_ALL=1 every module
of the compiler and the modules of a generated program (gen_program.py) too.

OnTheBBC: what the compiler gets on each machine, by the model of the placer (places.plan); a
module whose names need more than the 9,216 bytes of the heap as linked gives, on each machine
the emulator has (four banks, three, two; DFS, ADFS, a shadow mode), what the host compiler gives
with that machine's capacities; with two banks the compiler compiles three of its own modules
(all of them with LATHE_BBC_ROOMS_SELFHOST=1) under the DFS and ADFS, every file the host's.
LATHE_BBC_ROOMS_REPORT=1 prints every machine's capacities and the cycles.

TheLinker: what Image A's linker gets on each machine (its symbols of the object files, slots and
calls are planes sized as it starts: lathe/docs/bbc.md, "The linker's tables on two banks"), by the
model of the placer; *LLINK starts with two banks of sideways RAM and is refused with one; on two
banks, under the DFS and ADFS, it links a program, every file what the host linker writes at those
capacities (lk_rooms.py). With LATHE_BBC_ROOMS_SELFHOST=1 it links the compiler on three banks,
every file the host's, and on two refuses it as the host linker at those capacities does.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import src_support as support  # noqa: E402

ALL = os.environ.get('LATHE_BBC_ROOMS_ALL') == '1'
REPORT = os.environ.get('LATHE_BBC_ROOMS_REPORT') == '1'
SELFHOST = os.environ.get('LATHE_BBC_ROOMS_SELFHOST') == '1'
HEAP_TOOL = os.path.join(HERE, 'lathec_heap.py')
ONE_BANK_FUNCTIONS = 20         # functions a module of the generated program test_one_bank compiles
ONE_BANK_LARGEST = 82           # with LATHE_BBC_ROOMS_SELFHOST=1: the most with which one bank compiles
                                # them (its members are full at 84: error 72)
LINKED = 9216                   # kernel.NAME_HEAP_SIZE, the heap as linked
STARTS = (2, 1537, 3001)        # where the heap begins (name_top's first value, 1 in every build but
                                # Image B's, which begins it at PAGE less $1900): the same files, from
                                # the same room above the start; less is error 70
BIG_NAMES = 330                 # bignames: 12,923 bytes of the heap at most


def big_names_source(count=BIG_NAMES):
    """A module of `count` variables with names of 31 characters, and a main that uses a few."""
    lines = ['module bignames', '',
             '; %d variables with long names: more of the name heap than %d bytes.' % (count, LINKED), '']
    for i in range(count):
        lines.append('pub var a_variable_with_a_long_name_%03d: byte' % i)
    lines += ['', 'pub func main()']
    for i in range(0, count, 37):
        lines.append('  a_variable_with_a_long_name_%03d = %d' % (i, i & 255))
    lines += ['end', '']
    return '\n'.join(lines)


def read(path):
    with open(path, 'rb') as f:
        return f.read()


class Module:
    """A module to compile: its source, the options it is compiled with and the interfaces of what
    it imports, made once by the host compiler, in a directory of its own."""

    def __init__(self, work, name, source, options=(), interfaces=()):
        self.name, self.options = name, tuple(options)
        self.dir = os.path.join(work, 'module-' + name)
        os.makedirs(self.dir)
        shutil.copy(source, os.path.join(self.dir, name + '.lth'))
        for li in interfaces:
            shutil.copy(li, self.dir)
        self.count = 0

    def compile(self, heap, need=None, tokens=None, caps=None, start=None):
        """The host compiler with a heap of `heap` bytes, room for `tokens` bytes of saved tokens
        (else inline.SAVED_SIZE) and the capacities `caps` ({'syms': rows, 'buffer': ..., 'table':
        ..., 'string': ...}, lathec_heap.py), the heap begun at offset `start` (else 1):
        (status, error output, {file: bytes}); with `need`, the most the heap was asked for, too."""
        self.count += 1
        d = os.path.join(self.dir, 'at-%d-%d' % (heap, self.count))
        shutil.copytree(self.dir, d, ignore=shutil.ignore_patterns('at-*'))
        before = set(os.listdir(d))
        environ = dict(os.environ, LATHE_NAME_HEAP=str(heap))
        if need:
            environ['LATHE_NAME_HEAP_NEED'] = os.path.join(self.dir, 'need')
        if tokens:
            environ['LATHE_SAVED_TOKENS'] = str(tokens)
        if caps:
            environ['LATHE_CAPACITIES'] = ','.join('%s=%d' % kv for kv in sorted(caps.items()))
        if start:
            environ['LATHE_NAME_START'] = str(start)
        done = subprocess.run([sys.executable, HEAP_TOOL] + list(self.options) + [self.name + '.lth', '.'],
                              cwd=d, capture_output=True, env=environ)
        files = {f: read(os.path.join(d, f)) for f in sorted(os.listdir(d)) if f not in before}
        shutil.rmtree(d)
        result = (done.returncode, done.stderr, files)
        if need:
            with open(os.path.join(self.dir, 'need')) as f:
                result += (int(f.read()),)
        return result

    def least(self):
        """The least heap the module compiles with, and what it writes with a heap of 61,440."""
        status, said, files, need = self.compile(0xF000, need=True)
        assert status == 0, said
        heap = need
        for _ in range(64):
            if self.compile(heap)[0] == 0:
                return heap, files
            heap += 16
        raise AssertionError('%s: no heap from %d compiles it' % (self.name, need))


def selfhost_module(work, name):
    """Module NAME of lathe/src/, as test_src_selfhost.py compiles it."""
    import memory_report
    import test_src_selfhost
    options = tuple(memory_report.options_of(os.path.join(support.SRC, name + '.lth')))
    disk, host = test_src_selfhost.prepare(name, os.path.join(work, 'prepare-' + name), options)
    lis = [os.path.join(disk, f) for f in os.listdir(disk) if f.endswith('.li')]
    return Module(work, name, os.path.join(support.SRC, name + '.lth'), options, lis)


def generated_modules(work, functions=20):
    """The modules of a generated program (gen_program.py: four modules of `functions` functions,
    and its main), each with the interfaces of the modules before it, made by the host
    compiler."""
    import gen_program
    out = os.path.join(work, 'generated-%d' % functions)
    os.makedirs(out)
    gen_program.main([out, '4', str(functions)])
    sys.path.insert(0, os.path.join(support.LATHE, 'host', 'driver'))
    import build
    modules = []
    lis = []
    for name, path in build.module_order(os.path.join(out, 'genmain.lth')):
        if os.path.dirname(os.path.abspath(path)) == out:
            modules.append(Module(work, build.module_name(path), path, (), lis))
        subprocess.run([sys.executable, build.COMPILER, path, out], check=True, capture_output=True)
        lis = lis + [os.path.join(out, build.module_name(path) + '.li')]
    return modules


class SameObjects(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.mkdtemp(prefix='lathe-rooms-')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def check(self, module):
        least, expected = module.least()
        sizes = sorted(s for s in {least, least + 1, least + 1000, LINKED, 16128, 30000} if s >= least)
        for heap in sizes:
            with self.subTest(module=module.name, heap=heap):
                status, said, files = module.compile(heap)
                self.assertEqual((status, said), (0, b''))
                self.assertEqual(sorted(files), sorted(expected))
                for f in files:
                    self.assertTrue(files[f] == expected[f], f + ' differs')
        for caps in CAPACITY_SETS:
            with self.subTest(module=module.name, caps=caps):
                status, said, files = module.compile(30000, tokens=768, caps=caps)
                if status == 0:
                    self.assertEqual(sorted(files), sorted(expected))
                    for f in files:
                        self.assertTrue(files[f] == expected[f], f + ' differs')
                else:
                    self.assertRegex(said, CAPACITY_ERROR)
        for heap, tokens in ((least, 768), (30000, 1120), (16128, 1312)):
            with self.subTest(module=module.name, heap=heap, tokens=tokens):
                status, said, files = module.compile(heap, tokens=tokens)
                self.assertEqual((status, said), (0, b''))
                self.assertEqual(sorted(files), sorted(expected))
                for f in files:
                    self.assertTrue(files[f] == expected[f], f + ' differs')
        if least > 16:
            status, said, files = module.compile(least - 16)
            self.assertEqual(status, 1)
            self.assertIn(b'error 70: too many names', said)
        for start in STARTS:
            with self.subTest(module=module.name, start=start):
                status, said, files = module.compile(least + start - 1, start=start)
                self.assertEqual((status, said), (0, b''))
                self.assertEqual(sorted(files), sorted(expected))
                for f in files:
                    self.assertTrue(files[f] == expected[f], f + ' differs')
                if least > 16:
                    status, said, files = module.compile(least + start - 1 - 16, start=start)
                    self.assertEqual(status, 1)
                    self.assertIn(b'error 70: too many names', said)
        return least

    def test_the_same_files_at_every_heap(self):
        import test_src_selfhost
        names = test_src_selfhost.MODULES if ALL else test_src_selfhost.QUICK
        modules = [selfhost_module(self.work, name) for name in names]
        if ALL:
            modules += generated_modules(self.work)
        source = os.path.join(self.work, 'bignames.lth')
        with open(source, 'w') as f:
            f.write(big_names_source())
        modules.append(Module(self.work, 'bignames', source))
        least = {}
        for m in modules:
            least[m.name] = self.check(m)
        self.assertGreater(least['bignames'], LINKED)
        if REPORT or ALL:
            print('\nthe least name heap of each module: ' + ', '.join('%s %d' % kv for kv in least.items()))


# Capacities of the symbols (rows), the function buffer, the constant table and the string that
# machines get: a module gives the same files with each, or is refused for a capacity (error 7,
# a string too long, and 70 to 98).
CAPACITY_SETS = ({'syms': 768, 'buffer': 4096, 'table': 2048, 'string': 2048},
                 {'syms': 512, 'buffer': 4096, 'table': 2048, 'string': 2048},
                 {'syms': 256, 'buffer': 1792, 'table': 768, 'string': 768},
                 {'syms': 256, 'buffer': 1280, 'table': 512, 'string': 512})
CAPACITY_ERROR = b'error (7|7[0-9]|8[0-9]|9[0-8]): '                 # 7: a string too long

# Machines: (name, PAGE, HIMEM, the free sideways RAM, the emulator's options for it or None). The
# Master-like ones are the emulator's --bbc-model master (PAGE $0E00, its module in slot 8).
MACHINES = (
    ('B+128, DFS', 0x1900, 0x7C00, (0, 1, 12, 13), ('1900', False, ())),
    ('B+128, DFS, shadow mode', 0x1900, 0x8000, (0, 1, 12, 13), ('1900', True, ())),
    ('B+128, ADFS and DFS', 0x1F00, 0x7C00, (0, 1, 12, 13), ('1F00', False, ())),
    ('Model B, RAM in 8 to 11', 0x1900, 0x7C00, (8, 9, 10, 11),
     ('1900', False, ('--bbc-model', 'b', '--bbc-sideways-ram', '8,9,10,11'))),
    ('Master-like, shadow mode', 0x0E00, 0x8000, (4, 5, 6, 7), ('0E00', True, ('--bbc-model', 'master'))),
    ('Master-like, mode 7', 0x0E00, 0x7C00, (4, 5, 6, 7), ('0E00', False, ('--bbc-model', 'master'))),
    ('Master-like, two banks', 0x0E00, 0x7C00, (4, 5),
     ('0E00', False, ('--bbc-model', 'master', '--bbc-sideways-ram', '4,5'))),
    ('three banks', 0x1900, 0x7C00, (8, 9, 10), ('1900', False, ('--bbc-model', 'b', '--bbc-sideways-ram', '8,9,10'))),
    ('two banks, DFS', 0x1900, 0x7C00, (8, 9), ('1900', False, ('--bbc-model', 'b', '--bbc-sideways-ram', '8,9'))),
    ('two banks, ADFS', 0x1F00, 0x7C00, (8, 9), ('1F00', False, ('--bbc-model', 'b', '--bbc-sideways-ram', '8,9'))),
    ('one bank, DFS', 0x1900, 0x7C00, (8,), ('1900', False, ('--bbc-model', 'b', '--bbc-sideways-ram', '8'))),
    ('one bank, ADFS', 0x1F00, 0x7C00, (8,), ('1F00', False, ('--bbc-model', 'b', '--bbc-sideways-ram', '8'))),
)


def capacities(tool, machine):
    """{region: (where, slot or None for main RAM, capacity or None)} for a tool on a machine, by
    the model of the placer (places.plan); None if it is refused."""
    import places
    name, page, himem, slots, _ = machine
    p, names = places.of_tool(*tool[1:4])
    done = places.plan(p, page, himem, slots)
    if done is None:
        return None
    return {names[i]: (d.where, d.slot, d.room if p.regions[i].room else None) for i, d in done.items()}


@unittest.skipUnless(os.path.isfile(support.EMULATOR), 'emulator missing')
class OnTheBBC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import test_bbc_adapt
        cls.dir = tempfile.mkdtemp(prefix='lathe-bbc-rooms-')
        cls.tools, cls.account, cls.image, cls.listing = test_bbc_adapt.build_image(cls.dir)
        source = os.path.join(cls.dir, 'bignames.lth')
        with open(source, 'w') as f:
            f.write(big_names_source())
        cls.big = Module(cls.dir, 'bignames', source)
        if REPORT:
            for tool in cls.tools:
                for m in MACHINES:
                    print('\n%s on %s: %s' % (tool[0], m[0], capacities(tool, m)))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_what_the_compiler_gets_on_each_machine(self):
        """By the model of the placer: with three banks or more every table at its most (the name
        heap a slot to itself, 16,128 bytes; the symbols 768 rows); with two the name heap 8,704
        and the symbols 512 rows, the rest at its most but the saved tokens; with one bank the
        tables between the 32K Model B's and the full ones, more under the DFS than ADFS."""
        full = {'names': 16128, 'syms': 768, 'funcbuf': 4096, 'outtab': 2048, 'string': 2048, 'tokens': 2048}
        expected = {3: full, 4: full,
                    2: dict(full, names=8704, syms=512, tokens=1024),
                    (1, 0x1900): dict(names=4096, syms=256, funcbuf=1792, outtab=768, string=768, tokens=768),
                    (1, 0x1F00): dict(names=4096, syms=256, funcbuf=1280, outtab=512, string=512, tokens=768)}
        for m in MACHINES:
            with self.subTest(machine=m[0]):
                got = capacities(self.tools[0], m)
                want = COMPILER_ON.get(m[0]) or expected[len(m[3]) if len(m[3]) > 1 else (1, m[1])]
                self.assertEqual({k: v[2] for k, v in got.items() if v[2] is not None}, want)

    def host_compile(self, module, m):
        """The host compiler on Module `module` with machine m's capacities."""
        caps = capacities(self.tools[0], m)
        return module.compile(caps['names'][2], tokens=caps['tokens'][2],
                              caps={'syms': caps['syms'][2], 'buffer': caps['funcbuf'][2],
                                    'table': caps['outtab'][2], 'string': caps['string'][2]})

    def bbc_compile(self, module, m):
        """Image A's compiler on Module `module` on machine m, as the emulator has it:
        (status, output, what the MOS said, {file: bytes}, cycles)."""
        import test_bbc_adapt
        import test_bbc_selfhost as bbc_selfhost
        at, shadow, model = m[4]
        with test_bbc_adapt.machine(at, shadow, model):
            disk = tempfile.mkdtemp(dir=self.dir, prefix='disk-')
            os.rmdir(disk)
            shutil.copytree(module.dir, disk, ignore=shutil.ignore_patterns('at-*', 'need'))
            got = bbc_selfhost.report_run('rom', self.image, disk, list(module.options) + [module.name + '.lth', '.'])
        return got[:4] + (got[4],)

    def check_on(self, module, m):
        """The BBC gives what the host gives with m's capacities; the status, and the cycles."""
        status, said, expected = self.host_compile(module, m)
        got = self.bbc_compile(module, m)
        with self.subTest(machine=m[0], module=module.name):
            self.assertEqual(got[:3], (status, said, b''))
            self.assertEqual(sorted(got[3]), sorted(expected))
            for f in expected:
                self.assertTrue(got[3][f] == expected[f], f + ' differs')
        return status, got[4]

    def test_a_module_of_more_names_than_the_heap_as_linked(self):
        """The module of long names, refused by the compiler with a fixed heap (error 70): on
        each machine the emulator has, the BBC's compiler gives what the host compiler gives with
        that machine's capacities (by the model of the placer): its files with three banks or
        more, error 70 with two, error 71 (its 330 symbols) with one."""
        status, said, files = self.big.compile(LINKED)
        self.assertEqual(status, 1)
        self.assertIn(b'error 70: too many names', said)
        for m in MACHINES:
            if m[4] is None:
                continue
            status, cycles = self.check_on(self.big, m)
            self.assertEqual(status != 0, len(m[3]) < 3)
            if REPORT:
                print('\nbignames on %s: %d cycles' % (m[0], cycles))

    def test_the_compiler_compiles_itself_with_two_banks(self):
        """With two banks of sideways RAM, under the DFS and ADFS: the compiler's own modules (all
        of them with LATHE_BBC_ROOMS_SELFHOST=1; else three, decl among them, whose names need the
        most of the heap), every file the host compiler's."""
        import test_bbc_adapt
        import test_bbc_rom128 as rom128
        modules = rom128.selfhost_modules() if SELFHOST else ('err', 'sys', 'decl')
        for name, page, himem, slots, run in MACHINES:
            if run is None or len(slots) != 2:
                continue
            at, shadow, model = run
            base = self.dir
            self.dir = os.path.join(base, 'self-' + at)
            os.makedirs(self.dir, exist_ok=True)
            try:
                with test_bbc_adapt.machine(at, shadow, model):
                    cycles = rom128.compile_modules(self, self.image, ('rom',), modules)
            finally:
                self.dir = base
            if REPORT or SELFHOST:
                print('\nImage A on %s: %d compiles, %d cycles' % (name, len(cycles),
                                                                   sum(c['rom'] for c in cycles.values())))

    def test_one_bank(self):
        """With one bank of sideways RAM, under the DFS and ADFS: the compiler's own modules (all
        of them with LATHE_BBC_ROOMS_SELFHOST=1; else five) and the modules of a generated
        program each give what the host compiler gives with the machine's capacities, its files
        or the same capacity's error; the modules that compile are printed."""
        import test_src_selfhost
        names = test_src_selfhost.MODULES if SELFHOST else ('err', 'sys', 'src', 'typetab', 'fold')
        work = tempfile.mkdtemp(dir=self.dir, prefix='one-')
        functions = ONE_BANK_LARGEST if SELFHOST else ONE_BANK_FUNCTIONS
        modules = [selfhost_module(work, n) for n in names] + generated_modules(work, functions)
        for m in MACHINES:
            if m[4] is None or len(m[3]) != 1:
                continue
            compiled, refused, cycles = [], [], 0
            for module in modules:
                status, c = self.check_on(module, m)
                (refused if status else compiled).append(module.name)
                cycles += c
            print('\nImage A on %s: compiles %s; refuses %s; %d cycles' % (m[0], ', '.join(compiled),
                                                                       ', '.join(refused) or 'none', cycles))
            self.assertTrue(compiled)


# Where a machine's compiler gets other than what its number of banks gives: a Master-like machine
# with two banks has the 4,352 bytes from PAGE $0E00 to $1F00, which hold OUTTAB, so that the name
# heap gets 11,776 (8,704 with PAGE $1900) and the saved tokens 1,536 (1,024).
COMPILER_ON = {'Master-like, two banks': {'names': 11776, 'syms': 512, 'funcbuf': 4096, 'outtab': 2048,
                                          'string': 2048, 'tokens': 1536}}

# What Image A's linker gets (lathe/src/linker-bbc.env, ADAPT): the rows of lk_name.local, of the
# slots' columns and of the calls (`locals`, `slots`, `calls`: lk_rooms.py), by the number of banks.
LINKER_FULL = {'locals': 4096, 'slots': 4096, 'calls': 3584}
LINKER_GETS = {4: LINKER_FULL, 3: dict(LINKER_FULL, slots=3840),
               2: {'locals': 1536, 'slots': 2304, 'calls': 1280}, 1: None}
LINKER_ON = {'Master-like, two banks': {'locals': 2304, 'slots': 2304, 'calls': 2048}}   # LKNODES below $1F00
LINKER_REGIONS = {'lklocal': 'locals', 'lkslots': 'slots', 'lkcalls': 'calls'}
ROOMS_LINKER = os.path.join(HERE, 'lk_rooms.py')


def linker_capacities(tool, machine):
    """{table: rows} of Image A's linker on a machine, by the model of the placer; None if refused."""
    got = capacities(tool, machine)
    if got is None:
        return None
    return {LINKER_REGIONS[k]: v[2] for k, v in got.items() if v[2] is not None}


def two_banks(page):
    """The machine of MACHINES with two banks at PAGE `page` ('1900' or '1F00')."""
    return [m for m in MACHINES if m[4] and m[4][0] == page and len(m[3]) == 2][0]


def host_link_at(link, disk, caps):
    """The host linker run in disk (a copy of the BBC's) with the capacities `caps` {table: rows}
    (lk_rooms.py): (status, output and error output, {file: bytes} it wrote)."""
    import lk_rooms
    before = set(os.listdir(disk))
    r = subprocess.run([sys.executable, ROOMS_LINKER] + link, cwd=disk, capture_output=True,
                       env=dict(os.environ, LATHE_LK_CAPACITIES=lk_rooms.setting(caps)))
    files = {}
    for f in os.listdir(disk):
        if f not in before:
            with open(os.path.join(disk, f), 'rb') as handle:
                files[f] = handle.read()
    return r.returncode, r.stdout + r.stderr, files


def host_files_at(compiles, link, disk, tools, machine):
    """The host compiler and linker run in disk (a copy of the BBC's) as the BBC runs them, at the
    capacities Image A's tools (`tools`, test_bbc_adapt.build_image's) get on `machine`, by the
    model of the placer (lathec_heap.py, lk_rooms.py): ({file: bytes} of what they wrote,
    [(status, output and error output)] of each run)."""
    import lk_rooms
    caps = capacities(tools[0], machine)
    environ = dict(os.environ, LATHE_NAME_HEAP=str(caps['names'][2]), LATHE_SAVED_TOKENS=str(caps['tokens'][2]),
                   LATHE_CAPACITIES='buffer=%d,string=%d,syms=%d,table=%d' % (
                       caps['funcbuf'][2], caps['string'][2], caps['syms'][2], caps['outtab'][2]),
                   LATHE_LK_CAPACITIES=lk_rooms.setting(linker_capacities(tools[1], machine)))
    before = set(os.listdir(disk))
    said = []
    for args in compiles:
        r = subprocess.run([sys.executable, HEAP_TOOL] + args, cwd=disk, capture_output=True, env=environ)
        said.append((r.returncode, r.stdout + r.stderr))
    r = subprocess.run([sys.executable, ROOMS_LINKER] + link, cwd=disk, capture_output=True, env=environ)
    said.append((r.returncode, r.stdout + r.stderr))
    return {f: read(os.path.join(disk, f)) for f in os.listdir(disk) if f not in before}, said


@unittest.skipUnless(os.path.isfile(support.EMULATOR), 'emulator missing')
class TheLinker(unittest.TestCase):
    """Image A's linker (lathe/src/linker-bbc.env's order, LKROOMS 1): its five regions packed into
    three slots at full capacities, and into two with the symbols, the slots and the calls sized as
    it starts (lathe/docs/bbc.md, "The linker's tables on two banks"); *LLINK starts on a Model B
    with two banks of sideways RAM and is refused with one. On two banks, under the DFS and ADFS, it
    links a program, every file what the host linker writes at those capacities (and at its own);
    with LATHE_BBC_ROOMS_SELFHOST=1 it links the compiler with three banks, every file the host
    linker's, and with two refuses it as the host linker at those capacities does."""

    @classmethod
    def setUpClass(cls):
        import test_bbc_adapt
        cls.dir = tempfile.mkdtemp(prefix='lathe-bbc-rooms-link-')
        cls.tools, cls.account, cls.image, cls.listing = test_bbc_adapt.build_image(cls.dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_what_the_linker_gets_on_each_machine(self):
        """By the model of the placer: four banks every table at its most (4,096 symbols of the
        object files, 4,096 slots, 3,584 calls); three the slots 3,840; two the tables halved in
        turn until they fit beside the work area, under either filing system; one refused."""
        for m in MACHINES:
            with self.subTest(machine=m[0]):
                self.assertEqual(linker_capacities(self.tools[1], m),
                                 LINKER_ON.get(m[0]) or LINKER_GETS[min(len(m[3]), 4)])

    def test_two_banks_are_enough(self):
        import dataclasses
        import boards
        import test_bbc_rom128 as rom128
        base = boards.BOARDS['bbc']
        for ram, starts in (('8,9,10', True), ('8,9', True), ('8', False)):
            board = dataclasses.replace(base, options=base.options + ('--bbc-model', 'b', '--bbc-sideways-ram', ram))
            with self.subTest(ram=ram), rom128.scheme(), tempfile.TemporaryDirectory() as d:
                code, out, err, cycles = boards.run_module(board, self.image, d, 'LLINK', raw=True)
                self.assertEqual(b'usage: link' in out, starts)
                self.assertEqual(b'Too little sideways RAM' in out + err, not starts)
                if REPORT:
                    print('\nImage A, sideways RAM %s: *LLINK starts in %d cycles' % (ram, cycles))

    def bbc_link(self, page, ram, disk):
        """*LLINK @LINKARG on disk at PAGE `page` on a Model B with sideways RAM `ram`:
        (status, output, what the MOS said, {file: bytes} written, cycles)."""
        import boards
        import test_bbc_adapt
        import test_bbc_rom128 as rom128
        import test_bbc_selflink as selflink
        import test_bbc_toolchain as chain
        with test_bbc_adapt.machine(page, model=('--bbc-model', 'b', '--bbc-sideways-ram', ram)), rom128.scheme():
            lines = [boards.module_command('LLINK', ['@' + selflink.COMMAND_FILE])]
            status, out, mos, written, cycles, traffic = chain.bbc_run(self.image, disk, lines)
        return status, out, mos, written, cycles

    def test_the_linker_links_a_program_on_two_banks(self):
        """A program of the end-to-end cases, its objects the host compiler's, linked on two banks
        under the DFS and ADFS: every file the host linker's at those capacities, and at its own."""
        import test_bbc_selflink as selflink
        import test_bbc_toolchain as chain
        case = [c for c in chain.corpus() if c[0] == 'calls'][0]
        for page in ('1900', '1F00'):
            with self.subTest(page=page):
                caps = linker_capacities(self.tools[1], two_banks(page))
                disk, compiles, link, files, said, load = chain.prepare(case, os.path.join(self.dir, 'calls-' + page))
                for f in files:
                    if f.endswith('.lo'):
                        shutil.copy(os.path.join(os.path.dirname(disk), 'host', f), disk)
                with open(os.path.join(disk, selflink.COMMAND_FILE), 'w') as f:
                    f.write(' '.join(link) + '\r\n')
                at_caps = os.path.join(self.dir, 'calls-host-' + page)
                shutil.copytree(disk, at_caps)
                status, host_said, host_files = host_link_at(link, at_caps, caps)
                self.assertEqual((status, host_said), (0, b''))
                expected = selflink.link_outputs(files)
                self.assertEqual(host_files, expected)
                status, out, mos, written, cycles = self.bbc_link(page, '8,9', disk)
                self.assertEqual((status, out, mos), (0, b'', b''))
                self.assertEqual(sorted(written), sorted(expected))
                for f in expected:
                    self.assertTrue(written[f] == expected[f], f + ' differs')

    @unittest.skipUnless(SELFHOST, 'LATHE_BBC_ROOMS_SELFHOST=1 has the linker link the compiler on three banks')
    def test_the_linker_links_the_compiler_on_three_banks(self):
        import test_bbc_selflink as selflink
        for page in ('1900', '1F00'):
            name, source, env = selflink.TOOLS[0]
            work = os.path.join(self.dir, 'link-%s' % page)
            disk, compiles, link, files = selflink.prepare(name, source, env, work)
            for f in files:
                if f.endswith('.lo'):
                    shutil.copy(os.path.join(work, 'host', f), disk)
            status, out, mos, written, cycles = self.bbc_link(page, '8,9,10', disk)
            self.assertEqual((status, out, mos), (0, b'', b''))
            print('\nImage A, three banks, PAGE &%s: the linker links the compiler in %d cycles' % (page, cycles))
            expected = selflink.link_outputs(files)
            self.assertEqual(sorted(written), sorted(expected))
            for f in expected:
                self.assertTrue(written[f] == expected[f], f + ' differs')

    @unittest.skipUnless(SELFHOST, 'LATHE_BBC_ROOMS_SELFHOST=1 has the linker refuse the compiler on two banks')
    def test_the_compiler_is_too_large_for_two_banks(self):
        """The compiler's link needs more calls than two banks give: the linker on the BBC stops
        with what the host linker at those capacities says."""
        import test_bbc_selflink as selflink
        name, source, env = selflink.TOOLS[0]
        work = os.path.join(self.dir, 'link-two')
        disk, compiles, link, files = selflink.prepare(name, source, env, work)
        for f in files:
            if f.endswith('.lo'):
                shutil.copy(os.path.join(work, 'host', f), disk)
        for page in ('1900', '1F00'):
            with self.subTest(page=page):
                caps = linker_capacities(self.tools[1], two_banks(page))
                at_caps = os.path.join(self.dir, 'link-two-host-' + page)
                shutil.copytree(disk, at_caps)
                status, said, host_files = host_link_at(link, at_caps, caps)
                self.assertNotEqual(status, 0)
                here = os.path.join(self.dir, 'link-two-' + page)
                shutil.copytree(disk, here)
                got = self.bbc_link(page, '8,9', here)
                self.assertNotEqual(got[0], 0)
                self.assertIn(said.strip().splitlines()[0], got[1] + got[2])
                print('\nImage A, two banks, PAGE &%s: the compiler refused, %r, in %d cycles'
                      % (page, said.strip().decode('latin-1'), got[4]))


if __name__ == '__main__':
    unittest.main()
