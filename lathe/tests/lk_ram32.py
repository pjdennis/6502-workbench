#!/usr/bin/env python3
"""The linker on a 32K BBC Model B (lathe/docs/bbc.md, "The linker on a 32K BBC"): what it can
link. The 32K build is lathe/src/linker-bbc.env with `define RAM32 1`: no sideways RAM, every table
in main RAM, the capacities of `LKSMALL 2` (lathe/src/lk_tab.lth).

    python3 lathe/tests/lk_ram32.py shape         the shape of the compiler's and the linker's own
                                                  object files, and of the programs below
    python3 lathe/tests/lk_ram32.py real          the real programs: which the 32K build links
    python3 lathe/tests/lk_ram32.py series        programs made of real ones, grown a piece at a
                                                  time until the 32K build refuses them
    python3 lathe/tests/lk_ram32.py bbc NAME...   NAME (a real program, or pieces joined by +) linked
                                                  on the emulated BBC by the 32K build in the eight-
                                                  bank image, against the host linker; its cycles

--cache DIR keeps the compiled programs (default: a directory in the system's temporary directory).

The real programs are the compiler's and the linker's test programs of lathe/src (each the tools'
own modules with a driver) and the end-to-end cases, each compiled for the BBC all in one by
build.py with an environment that has room for any size (MEASURE_ENV), so that a program larger
than a 32K BBC holds is compiled too; the objects and the link are kept. A synthetic program is
made of real ones (glue): each piece's own modules renamed, so that two pieces can hold the same
module, the run-time modules (SHARED) once, and a main that calls each piece's main, so that what
each piece keeps is kept. Its shape is the tools' own by construction; `shape` compares them.

What a link needs of each table is the host linker's use of it (probe), at the full capacities,
and whether the 32K build links it is the host linker at the 32K build's capacities
(lk_small.load(2)), which refuses exactly where the Lathe-written linker does (test_lk_ram32.py
links some on the BBC and compares every file)."""
import concurrent.futures
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LATHE = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(LATHE, 'host'))
sys.path.insert(0, os.path.join(LATHE, 'host', 'driver'))

import src_support as support  # noqa: E402

SRC = support.SRC

# Compiles any program for the BBC all in one: code and variables have room for any size, so the
# size of what is linked can be measured; the defines are every one a program here tests.
MEASURE_ENV = '''cpu       6502
zeropage  $00 $8F
code      $1900 $BFFF
data      $C000 $FFF0
more      data $0401 $06FF
exit      return $0400
output    raw
define    BOARD 3
define    PORTS 2
define    SMALL 1
define    BBCFS 0
define    TEXTS_IN_MODULE 0
define    LKSMALL 1
define    ROMFORM 0
define    ADFS 0
define    ROM128 0
define    RAM32 0
define    MODULE_SLOT 4
'''

# A 32K BBC in mode 7: PAGE $1900 (the DFS), HIMEM $7C00, and $0401-$06FF; in mode 4 HIMEM is $5800.
HIMEM = {7: 0x7C00, 4: 0x5800}
PAGE = 0x1900
MORE = (0x0401, 0x06FF)

# The test programs of lathe/src, smallest first, and the end-to-end cases.
PROGRAMS = ('copytest', 'errtest', 'srctest', 'typetest', 'foldtest', 'lextest', 'fbuftest', 'kerneltest',
            'lktest1', 'outtest', 'regtest', 'condtest', 'asmtest')
SHARED = ('bbcfs', 'bbc', 'disk', 'host', 'sys', 'rt_math', 'rt_with', 'rt_bbc', 'rt_bank', 'rt_frame')

RECORDER = '''import json, os, shutil, sys
d = os.environ['LK_DIR']
os.makedirs(d, exist_ok=True)
args = sys.argv[1:]
objs = []
for p in args[4:]:
    shutil.copy(p, d)
    objs.append(os.path.basename(p))
with open(os.path.join(d, 'link.json'), 'w') as f:
    json.dump({'main': args[1], 'objects': objs}, f)
os.execv(sys.executable, [sys.executable, os.environ['LK_REAL']] + args)
'''


def ram32_env(path, bbcfs=0, source=None):
    """Write to path linker-bbc.env (or source) with `define RAM32 1` and BBCFS as given."""
    with open(source or os.path.join(SRC, 'linker-bbc.env')) as f:
        text = f.read()
    text, n = re.subn(r'(?m)^define\s+RAM32\s+0\b', 'define    RAM32 1', text)
    assert n == 1
    text, n = re.subn(r'(?m)^define\s+BBCFS\s+0\b', 'define    BBCFS %d' % bbcfs, text)
    assert n == 1
    with open(path, 'w') as f:
        f.write(text)
    return path


# ---- The real programs ------------------------------------------------------------------------

def sources():
    """[(name, path)] of the real programs."""
    found = [(p, os.path.join(SRC, p + '.lth')) for p in PROGRAMS]
    for p in sorted(glob.glob(os.path.join(LATHE, 'tests', 'cases', 'e2e', '*.lth'))):
        with open(p, encoding='latin-1') as f:
            first = f.readline()
        if os.path.basename(p).startswith('lib') or first.startswith('; imported by'):
            continue
        found.append(('e2e_' + os.path.basename(p)[:-4], p))
    return found


def build_programs(cache, names=None):
    """Compile every real program (or those named) into cache/NAME/ once: its objects and
    link.json (main, objects in link order). Returns the names that built."""
    import build
    os.makedirs(cache, exist_ok=True)
    env = os.path.join(cache, 'measure.env')
    with open(env, 'w') as f:
        f.write(MEASURE_ENV)
    rec = os.path.join(cache, 'recorder.py')
    with open(rec, 'w') as f:
        f.write(RECORDER)
    chosen = [(n, p) for n, p in sources() if names is None or n in names]

    def one(item):
        name, path = item
        d = os.path.join(cache, name)
        if os.path.exists(os.path.join(d, 'link.json')):
            return name
        environ = dict(os.environ, LK_DIR=d, LK_REAL=build.LINKER, LATHE_LINKER=rec)
        with tempfile.TemporaryDirectory() as t:
            # A program too large for the measuring environment still leaves its objects.
            subprocess.run([sys.executable, os.path.join(LATHE, 'host', 'driver', 'build.py'), path,
                            '-o', os.path.join(t, 'o.bin'), '--env', env], env=environ,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return name if os.path.exists(os.path.join(d, 'link.json')) else None
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        return [n for n in pool.map(one, chosen) if n]


def program(cache, name):
    """(main, [object paths]) of a real program built in cache."""
    d = os.path.join(cache, name)
    with open(os.path.join(d, 'link.json')) as f:
        j = json.load(f)
    return j['main'], [os.path.join(d, o) for o in j['objects']]


# ---- Programs made of real ones ---------------------------------------------------------------

def rename(module, own, prefix):
    """The object module with every name of a module in `own` prefixed."""
    def renamed(name):
        head, dot, rest = name.partition('.')
        return prefix + head + dot + rest if head in own else name
    module.name = renamed(module.name)
    module.imports = [renamed(i) for i in module.imports]
    for s in module.symbols:
        s.name = renamed(s.name)
    return module


def glue(cache, pieces, out_dir, main='glue'):
    """A program of the real programs `pieces` (names in cache) in out_dir: (main, [objects] in
    link order). The first piece keeps its names, the others' modules are named gK...; the
    run-time modules, the same in every piece, are linked once, first."""
    import lo
    os.makedirs(out_dir, exist_ok=True)
    shared, own_objects, mains = {}, [], []
    for k, name in enumerate(pieces):
        piece_main, objects = program(cache, name)
        prefix = 'g%d' % k if k else ''
        names = [os.path.basename(o)[:-3] for o in objects]
        own = set(n for n in names if n not in SHARED)
        for n, path in zip(names, objects):
            with open(path, 'rb') as f:
                data = f.read()
            if n in SHARED:
                if n in shared:
                    assert shared[n][1] == data, (name, n)
                    continue
                out = os.path.join(out_dir, n + '.lo')
                shared[n] = (out, data)
            else:
                out = os.path.join(out_dir, prefix + n + '.lo')
                data = lo.write(rename(lo.read(data, path), own, prefix))
                own_objects.append(out)
            with open(out, 'wb') as f:
                f.write(data)
        mains.append(prefix + piece_main + '.main')
    b = lo.Builder(main)
    fb = b.func(main + '.main')
    for m in mains:
        fb.call(m).op('JSR', 'abs', m)
    fb.op('RTS')
    own_objects.append(b.save(os.path.join(out_dir, main + '.lo')))
    return main, [shared[n][0] for n in SHARED if n in shared] + own_objects


# ---- What a link needs ------------------------------------------------------------------------

# The use of each table, as lk_memory_report.USAGE has it, and what lk_ram32.py's probe adds:
# the reading's bytes of the work area (from its first word to the end of the names and the
# symbols' words), and the bytes of one file's names held for the map.
COLUMNS = ('functions', 'slots', 'big slots', 'calls', 'nodes', 'locals', 'symbols', 'defs', 'classes',
           'class params', 'members', 'pending weights', 'fix-ups held', 'reading bytes', 'map names bytes',
           'objects')


def probe_main(argv):
    """In a process of its own: the host linker at the capacities of level argv[0] (0 full, 2 the
    32K build's), linking argv[2:], with the use of every table appended to argv[1] as JSON."""
    import lk_small
    level, out = int(argv[0]), argv[1]
    lk_small.load(level or False)
    import env
    import lk_fix
    import lk_map
    import lk_memory_report as rep
    import lk_name
    import lk_sym
    import lk_tab
    peaks = {'fixes': 0, 'reading': 0, 'held': 0}
    hold, name_add, buf_keep, hold_begin = lk_fix.hold, lk_name.name_add, lk_name.buf_keep, lk_map.hold_begin
    held_from = [0]

    def counting_hold(*a):
        r = hold(*a)
        peaks['fixes'] = max(peaks['fixes'], lk_fix.fix_count)
        return r

    def counting_name_add(c):
        r = name_add(c)
        peaks['reading'] = max(peaks['reading'], lk_name.heap_top + lk_name.ENTRY + lk_name.pending
                               + 4 * lk_sym.count)
        return r

    def counting_buf_keep():
        r = buf_keep()
        peaks['held'] = max(peaks['held'], lk_name.buf_top - 2 * held_from[0])
        return r

    def counting_hold_begin(obj, start, limit):
        held_from[0] = start
        peaks['held'] = max(peaks['held'], 2 * (lk_name.obj_first[obj + 1] - lk_name.obj_first[obj]))
        return hold_begin(obj, start, limit)
    lk_fix.hold, lk_name.name_add, lk_name.buf_keep = counting_hold, counting_name_add, counting_buf_keep
    lk_map.hold_begin = counting_hold_begin
    names = dict(rep.modules())
    real_exit = env.exit

    def recording_exit(code):
        values = dict(names, PEAK_FIXES=peaks['fixes'])
        use = {t: eval(u, values) for t, _, u, c in rep.USAGE}
        use.update({'big slots': lk_tab.big_count, 'symbols': lk_sym.count, 'reading bytes': peaks['reading'],
                    'map names bytes': peaks['held']})
        with open(out, 'a') as f:
            f.write(json.dumps({'status': code, 'use': use}) + '\n')
        real_exit(code)
    env.exit = recording_exit
    env.start(argv[2:])
    import link
    link.main()


def link_size(map_path):
    """(code and constants from PAGE, variables) of an all-in-one map: its bytes in main RAM."""
    code_end, variables = PAGE, 0
    with open(map_path) as f:
        for line in f:
            w = line.split()
            if len(w) < 4 or len(w[0]) != 1 or w[0] not in 'FDVS':
                continue
            a, s = int(w[1], 16), int(w[2], 16)
            if w[0] in 'FD' and PAGE <= a < 0xC000:
                code_end = max(code_end, a + s)
            elif w[0] in 'VS' and a >= 0x100:
                variables += s
    return code_end - PAGE, variables


def host_link(level, env_path, main, objects):
    """The host linker at the capacities of `level` (0 or 2): (status, its first line of error
    output, {table: use}, (code, variables) linked or None)."""
    with tempfile.TemporaryDirectory() as t:
        out = os.path.join(t, 'use')
        r = subprocess.run([sys.executable, os.path.abspath(__file__), '--probe', str(level), out, env_path, main,
                            os.path.join(t, 'o.bin'), os.path.join(t, 'o.map')] + objects,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        use = None
        if os.path.exists(out):
            with open(out) as f:
                use = json.loads(f.readline())['use']
        size = link_size(os.path.join(t, 'o.map')) if r.returncode == 0 else None
        return r.returncode, r.stderr.decode('latin-1').strip().split('\n')[0], use, size


def read_bytes(path):
    with open(path, 'rb') as f:
        return f.read()


def object_bytes(objects):
    return sum(os.path.getsize(o) for o in objects)


# ---- The shape of Lathe code ------------------------------------------------------------------

def shape(objects):
    """The shape of the object files `objects` (run-time modules left out): {measure: value}."""
    import lo
    funcs, mods = [], []
    for path in objects:
        n = os.path.basename(path)[:-3]
        if n in SHARED:
            continue
        with open(path, 'rb') as f:
            data = f.read()
        m = lo.read(data, path)
        fs = m.functions()
        defined = set(x.sym for x in m.items if isinstance(x, (lo.Func, lo.Var, lo.Data, lo.Clas)))
        vs, ds = m.of_type(lo.Var), m.of_type(lo.Data)
        mods.append((len(fs), len(m.symbols), len(m.symbols) - len(defined), len(m.imports), len(vs),
                     sum(v.size for v in vs), sum(len(d.data) for d in ds), len(data)))
        for f in fs:
            funcs.append((len(f.code), len(f.slots), sum(1 for s in f.slots if s.kind == lo.SK_PARAM),
                          len(f.calls), len(f.fixes)))
    nf, nm = len(funcs), len(mods)

    def mean(rows, i, n):
        return sum(r[i] for r in rows) / n

    code = sum(f[0] for f in funcs)
    return {'modules': nm, 'functions': nf, 'code bytes': code, 'object bytes': sum(m[7] for m in mods),
            'code a function': code / nf, 'median code a function': sorted(f[0] for f in funcs)[nf // 2],
            'slots a function': mean(funcs, 1, nf), 'parameters a function': mean(funcs, 2, nf),
            'calls a function': mean(funcs, 3, nf), 'fix-ups a function': mean(funcs, 4, nf),
            'most fix-ups of a function': max(f[4] for f in funcs),
            'functions a module': nf / nm, 'symbols a module': mean(mods, 1, nm),
            'symbols named from outside a module': mean(mods, 2, nm), 'imports a module': mean(mods, 3, nm),
            'variables a module': mean(mods, 4, nm), 'variable bytes a module': mean(mods, 5, nm),
            'constant bytes a module': mean(mods, 6, nm),
            'object bytes a code byte': sum(m[7] for m in mods) / code}


def print_shape(cache):
    import build
    rows = []
    with tempfile.TemporaryDirectory() as t:
        for tool, source, env in (('the linker', 'link.lth', 'linker-bbc.env'),
                                  ('the compiler', 'lathec.lth', 'lathec-bbc.env')):
            work = os.path.join(t, tool.split()[1])
            build.build(os.path.join(SRC, source), os.path.join(t, 'image'), env=os.path.join(SRC, env), keep=work)
            rows.append((tool, shape(glob.glob(os.path.join(work, '*.lo')))))
    for name in ('lextest', 'kerneltest'):
        rows.append((name, shape(program(cache, name)[1])))
    keys = list(rows[0][1])
    print('%-38s' % '' + ''.join('%14s' % r[0] for r in rows))
    for k in keys:
        print('%-38s' % k + ''.join(('%14.2f' if isinstance(r[1][k], float) else '%14d') % r[1][k] for r in rows))


# ---- On the BBC ------------------------------------------------------------------------------

COMMAND_FILE = 'LINKARG'


def build_image(out_dir, bbcfs=0):
    """The eight-bank module image of the compiler (lathe/src/lathec-bbc.env, banks 0 to 4) and the
    32K build of the linker (banks 5 to 7) in out_dir/MODULE, as test_bbc_rom128.py lays the
    tools out: (image, the account, the linker's map, the error of its link or None). The image
    is None if they do not fit."""
    import test_bbc_rom128 as rom128
    import bbcrom
    import build
    os.makedirs(out_dir, exist_ok=True)
    source = ram32_env(os.path.join(out_dir, 'linker-ram32.env'), bbcfs)
    tools = rom128.build_tools(out_dir, rom128.TOOLS[:1])
    # The linker as build_tools builds it, from the 32K environment.
    d = os.path.join(out_dir, 'llink')
    os.makedirs(d)
    rom = os.path.join(d, 'linker-bbc.env')
    bbcrom.rom_env(source, rom, 5, rom128.BANKS)
    notes = os.path.join(d, 'judged')
    saved, os.environ['LK_JUDGED_OUT'] = build.LINKER, notes
    build.LINKER = rom128.JUDGED
    error = None
    try:
        build.build(os.path.join(SRC, 'link.lth'), os.path.join(d, 'LLINK'), env=rom, keep=os.path.join(d, 'work'))
    except build.BuildError as e:
        error = str(e).strip().splitlines()[-1]
    finally:
        build.LINKER = saved
        del os.environ['LK_JUDGED_OUT']
    tools.append(('LLINK', os.path.join(d, 'LLINK'), rom, os.path.join(d, 'work', 'link.map'), error,
                  rom128.read_judged(notes)))
    account = rom128.Account(tools)
    image = None
    if account.fits():
        image = os.path.join(out_dir, 'MODULE')
        bbcrom.image([t[:4] for t in tools], image, os.path.join(out_dir, 'listing'), banks=rom128.BANKS)
    return image, account, tools[1][3], error


def target_env(path, code, variables, mode=7):
    """Write to path the environment of a program of `code` bytes of code and constants on a 32K
    BBC in `mode`: code from PAGE, the variables after it to HIMEM, and $0401-$06FF. Returns path,
    or None if the program cannot fit."""
    split = PAGE + code
    if split >= HIMEM[mode] or not fits((code, variables), mode):
        return None
    with open(path, 'w') as f:
        f.write(MEASURE_ENV.replace('code      $1900 $BFFF\ndata      $C000 $FFF0\n',
                                    'code      $1900 $%04X\ndata      $%04X $%04X\n' % (split - 1, split,
                                                                                        HIMEM[mode] - 1)))
    return path


def bbc_link(image, objects, main, env_path, work, dfs=False):
    """The 32K build links the objects on the emulated BBC from the module image (`*LLINK @LINKARG`),
    and the host linker the same in a copy of the disc: (the BBC's status, output and what its MOS
    said, {file: bytes} it wrote, {file: bytes} the host wrote, cycles, file traffic). With dfs,
    under the DFS's names and limits (--bbc-fs dfs; the image built with BBCFS 1), the files
    where the DFS keeps them, and the traffic is (most files open, most open for writing)."""
    import test_bbc_rom128 as rom128
    import test_bbc_toolchain as chain
    import boards
    disk = os.path.join(work, 'bbc')
    host = os.path.join(work, 'host')
    os.makedirs(disk)
    for o in objects + [env_path]:
        shutil.copy(o, disk)
    image_name = main.upper()[:7]
    link = ([os.path.basename(env_path), main, image_name, image_name + '.map']
            + [os.path.basename(o) for o in objects])
    with open(os.path.join(disk, COMMAND_FILE), 'w') as f:
        f.write(''.join(a + '\n' for a in link))
    shutil.copytree(disk, host)
    r = subprocess.run([sys.executable, os.path.join(LATHE, 'host', 'link.py')] + link, cwd=host,
                       capture_output=True)
    expected = {f: read_bytes(os.path.join(host, f)) for f in os.listdir(host) if f not in os.listdir(disk)}
    lines = [boards.module_command('LLINK', ['@' + COMMAND_FILE])]
    with rom128.scheme():
        if not dfs:
            status, out, mos, written, cycles, traffic = chain.bbc_run(image, disk, lines)
            return (status, out, mos), written, (r.returncode, expected), cycles, traffic
        import bbcfs
        import test_bbc_dfs
        test_bbc_dfs.to_dfs(disk)
        status, out, mos, written, cycles, traffic = test_bbc_dfs.run_dfs(image, disk, lines)
    expected = {os.path.relpath(bbcfs.host_path(disk, f), disk): d for f, d in expected.items()}
    return (status, out, mos), written, (r.returncode, expected), cycles, traffic


# ---- Reports ----------------------------------------------------------------------------------

def fits(size, mode):
    """True if a program of `size` (code, variables) fits a 32K BBC with the screen of `mode`."""
    return size[0] + size[1] <= HIMEM[mode] - PAGE + MORE[1] + 1 - MORE[0]


def describe(name, objects, full, small):
    """A line: the objects (count and bytes), the program's size, whether the 32K build links it."""
    status, error, use, size = small
    _, _, need, full_size = full
    total = full_size[0] + full_size[1] if full_size else 0
    return ('%-34s %2d objects %7d bytes; code %6s variables %6s total %6s  %s' % (
        name, len(objects[0]), objects[1], full_size and full_size[0], full_size and full_size[1], total,
        'links' if status == 0 else error))


def print_real(cache):
    names = build_programs(cache)
    env_path = os.path.join(cache, 'measure.env')

    def one(name):
        main, objects = program(cache, name)
        return (name, (objects, object_bytes(objects)), host_link(0, env_path, main, objects),
                host_link(2, env_path, main, objects))
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        for name, objects, full, small in pool.map(one, names):
            print(describe(name, objects, full, small))


# Each series starts from a real program and adds pieces in order until the 32K build refuses it.
SERIES = (('lextest', ['errtest', 'copytest', 'e2e_compare', 'e2e_reg_args', 'e2e_record_copy', 'e2e_control',
                       'e2e_words', 'e2e_signed', 'e2e_strings_long', 'e2e_shared_types', 'e2e_rec_eval']),
          ('fbuftest', ['errtest', 'copytest', 'e2e_compare', 'e2e_reg_args', 'e2e_control', 'e2e_words',
                        'e2e_signed', 'e2e_strings_long', 'e2e_shared_types', 'e2e_rec_eval']),
          ('kerneltest', ['copytest', 'e2e_compare', 'e2e_reg_args', 'e2e_control', 'e2e_words', 'e2e_signed']),
          ('srctest', ['typetest', 'copytest', 'e2e_compare', 'e2e_reg_args', 'e2e_control', 'e2e_words',
                       'e2e_signed']),
          ('lktest1', ['srctest', 'copytest', 'e2e_compare', 'e2e_reg_args', 'e2e_control', 'e2e_words',
                       'e2e_signed']),
          ('errtest', ['srctest', 'copytest', 'e2e_compare', 'e2e_reg_args', 'e2e_record_copy', 'e2e_control',
                       'e2e_words', 'e2e_signed', 'e2e_strings_long', 'e2e_shared_types', 'e2e_rec_eval',
                       'e2e_arith_ops', 'e2e_math_word', 'e2e_symbols']))


def grow(cache, base, more, out_dir):
    """The series: [(pieces, objects, full link, 32K link)] up to and with the first refused."""
    env_path = os.path.join(cache, 'measure.env')
    steps = []
    for k in range(0, len(more) + 1):
        pieces = [base] + more[:k]
        d = os.path.join(out_dir, '%s-%d' % (base, k))
        main, objects = glue(cache, pieces, d)
        full, small = host_link(0, env_path, main, objects), host_link(2, env_path, main, objects)
        steps.append((pieces, (objects, object_bytes(objects)), full, small))
        if small[0] != 0:
            break
    return steps


def print_series(cache):
    build_programs(cache)
    with tempfile.TemporaryDirectory() as t:
        with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
            done = list(pool.map(lambda s: grow(cache, s[0], s[1], t), SERIES))
    for steps in done:
        for pieces, objects, full, small in steps:
            print(describe('+'.join(pieces), objects, full, small))
            need = full[2]
            if small[0] != 0 or pieces is steps[-1][0]:
                print('    needs: ' + ', '.join('%s %s' % (c, need.get(c)) for c in COLUMNS if need))
        print()


def main(argv):
    if argv[:1] == ['--probe']:
        probe_main(argv[1:])
        return
    cache = os.path.join(tempfile.gettempdir(), 'lathe-lk-ram32')
    if '--cache' in argv:
        i = argv.index('--cache')
        cache = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    what = argv[0] if argv else 'real'
    if what == 'shape':
        build_programs(cache, ('lextest', 'kerneltest'))
        print_shape(cache)
    elif what == 'real':
        print_real(cache)
    elif what == 'series':
        print_series(cache)
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
