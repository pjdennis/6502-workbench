#!/usr/bin/env python3
"""How much memory the linker's tables take, laid out as the Lathe linker will lay them out.

    python3 lathe/tests/lk_memory_report.py            the tables, per module and in total
    python3 lathe/tests/lk_memory_report.py --corpus   also the peak use of each table, over every
                                                       end-to-end case and lextest
    python3 lathe/tests/lk_memory_report.py --synthetic    the same for lk_synthetic's program

Every module-level array of a linker module counts: 2 bytes per element of a list (a Lathe word
column), 1 per element of a bytearray. An array that two modules name counts once. Byte
strings are constants (code), not tables.

The corpus is compiled once into --cache DIR (default: a directory in the system's temporary
directory), by build.py with a stand-in linker that keeps each link's command line and objects.
Each program is then linked again by `--probe`, which runs the host linker in this process and,
when it exits, appends the use of every table (USAGE) to the file named by $LK_PROBE_OUT.

test_lk_memory.py keeps the total within CEILING, which comes down as the work goes on until it
reaches BUDGET.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LATHE = os.path.abspath(os.path.join(HERE, '..'))
HOST = os.path.join(LATHE, 'host')
sys.path.insert(0, HOST)

BUDGET = 24 * 1024                  # the goal (architecture.md, "Memory in the linker")
CEILING = 96 * 1024                 # what the linker takes now must not grow past this

MODULES = ['lk_err', 'lk_file', 'lk_op', 'lk_rec', 'lk_sym', 'lk_envf', 'lk_tab', 'lk_scan',
           'lk_out', 'lk_boot', 'lk_graph', 'lk_alloc', 'lk_fix', 'lk_place', 'lk_map', 'lk_emit']

# The use of each table at the end of a link: name -> (module, expression for the rows used,
# expression for the capacity). The expressions are evaluated with the linker's modules as names.
USAGE = [
    ('objects', 'lk_scan', 'lk_scan.object_count', 'lk_scan.MAX_OBJECTS'),
    ('locals', 'lk_scan', 'lk_scan.local_count', 'lk_scan.MAX_LOCALS'),
    ('symbols', 'lk_sym', 'lk_sym.count', 'lk_sym.MAX_SYMS'),
    ('name heap', 'lk_sym', 'lk_sym.heap_top', 'lk_sym.HEAP_SIZE'),
    ('functions', 'lk_tab', 'lk_tab.fn_count', 'lk_tab.MAX_FUNCS'),
    ('slots', 'lk_tab', 'lk_tab.slot_count', 'lk_tab.MAX_SLOTS'),
    ('calls', 'lk_tab', 'lk_tab.edge_count', 'lk_tab.MAX_EDGES'),
    ('nodes', 'lk_tab', 'lk_tab.node_count', 'lk_tab.MAX_NODES'),
    ('defs', 'lk_tab', 'lk_tab.def_count', 'lk_tab.MAX_DEFS'),
    ('classes', 'lk_tab', 'lk_tab.cls_count', 'lk_tab.MAX_CLASSES'),
    ('class params', 'lk_tab', 'lk_tab.cp_count', 'lk_tab.MAX_CPARAMS'),
    ('members', 'lk_tab', 'lk_tab.memb_count', 'lk_tab.MAX_MEMBERS'),
    ('contexts', 'lk_tab', 'lk_tab.ctx_count', 'lk_tab.MAX_CONTEXTS'),
    ('pending weights', 'lk_scan', 'lk_scan.pend_count', 'lk_scan.MAX_PENDING'),
    ('fix-ups held', 'lk_fix', 'PEAK_FIXES', 'lk_fix.MAX_FIXES'),
]


def modules():
    import importlib
    return [(m, importlib.import_module(m)) for m in MODULES]


def table_bytes():
    """[(module, bytes, [(array, bytes)...])] and the total, each array counted once."""
    seen = set()
    rows = []
    total = 0
    for name, mod in modules():
        arrays = []
        for k, v in sorted(vars(mod).items()):
            if k.startswith('__') or id(v) in seen:
                continue
            if isinstance(v, bytearray):
                size = len(v)
            elif isinstance(v, list):
                size = 2 * len(v)
            else:
                continue
            seen.add(id(v))
            arrays.append((k, size))
        sub = sum(s for _, s in arrays)
        total += sub
        rows.append((name, sub, sorted(arrays, key=lambda a: -a[1])))
    return rows, total


def print_tables():
    rows, total = table_bytes()
    for name, sub, arrays in rows:
        if sub:
            print('%-10s %7d  %s' % (name, sub, ' '.join('%s=%d' % a for a in arrays[:8])))
    print('%-10s %7d  (ceiling %d, goal %d)' % ('total', total, CEILING, BUDGET))
    return total


# ---- the corpus

RECORDER = '''import json, os, shutil, sys
d = os.path.join(os.environ['LK_CACHE'], os.environ['LK_NAME'])
os.makedirs(d, exist_ok=True)
args = sys.argv[1:]
objs = []
for p in args[4:]:
    shutil.copy(p, d)
    objs.append(os.path.basename(p))
shutil.copy(args[0], os.path.join(d, 'env'))
with open(os.path.join(d, 'link.json'), 'w') as f:
    json.dump({'main': args[1], 'objects': objs}, f)
os.execv(sys.executable, [sys.executable, os.environ['LK_REAL']] + args)
'''


def corpus_sources():
    cases = [(os.path.join(LATHE, 'src', 'lextest.lth'), os.path.join(LATHE, 'src', 'compiler.env'))]
    for d, e in (('e2e', 'host'), ('e2e-michael', 'michael'), ('e2e-wendy2', 'wendy2')):
        for p in sorted(glob.glob(os.path.join(LATHE, 'tests', 'cases', d, '*.lth'))):
            with open(p, encoding='latin-1') as f:
                first = f.readline()
            if os.path.basename(p).startswith('lib') or first.startswith('; imported by'):
                continue
            cases.append((p, e))
    return cases


def build_corpus(cache):
    """Compile every program of the corpus into cache/NAME/ once. Returns the names."""
    sys.path.insert(0, os.path.join(HOST, 'driver'))
    import build
    names = []
    rec = os.path.join(cache, 'recorder.py')
    os.makedirs(cache, exist_ok=True)
    with open(rec, 'w') as f:
        f.write(RECORDER)
    for path, env in corpus_sources():
        name = os.path.relpath(path, LATHE).replace(os.sep, '_')[:-4]
        names.append(name)
        if os.path.exists(os.path.join(cache, name, 'link.json')):
            continue
        environ = dict(os.environ, LK_CACHE=cache, LK_NAME=name, LK_REAL=build.LINKER,
                       LATHE_LINKER=rec)
        with tempfile.TemporaryDirectory() as t:
            r = subprocess.run([sys.executable, os.path.join(HOST, 'driver', 'build.py'), path,
                                '-o', os.path.join(t, 'o.bin'), '--env', env], env=environ,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if r.returncode != 0:
                print('build failed:', name, r.stderr.decode()[-300:])
    return names


def link_args(cache, name, out_dir):
    d = os.path.join(cache, name)
    with open(os.path.join(d, 'link.json')) as f:
        j = json.load(f)
    return [os.path.join(d, 'env'), j['main'], os.path.join(out_dir, 'o.bin'),
            os.path.join(out_dir, 'o.map')] + [os.path.join(d, o) for o in j['objects']]


def probe(args):
    """Link with the host linker in this process; at its exit, record the use of each table."""
    import env
    import lk_fix
    import link
    peak = [0]
    hold = lk_fix.hold

    def counting_hold(*a):
        r = hold(*a)
        peak[0] = max(peak[0], lk_fix.fix_count)
        return r
    lk_fix.hold = counting_hold
    names = dict(modules())
    real_exit = env.exit

    def recording_exit(code):
        values = dict(names, PEAK_FIXES=peak[0])
        use = {t: [eval(u, values), eval(c, values)] for t, _, u, c in USAGE}
        with open(os.environ['LK_PROBE_OUT'], 'a') as f:
            f.write(json.dumps({'status': code, 'use': use}) + '\n')
        real_exit(code)
    env.exit = recording_exit
    env.start(args)
    link.main()


def corpus_peaks(cache):
    names = build_corpus(cache)
    out = os.path.join(cache, 'probe.out')
    if os.path.exists(out):
        os.remove(out)
    for name in names:
        if not os.path.exists(os.path.join(cache, name, 'link.json')):
            continue
        with tempfile.TemporaryDirectory() as t:
            subprocess.run([sys.executable, os.path.abspath(__file__), '--probe'] + link_args(cache, name, t),
                           env=dict(os.environ, LK_PROBE_OUT=out))
    peaks = {}
    count = 0
    with open(out) as f:
        for line in f:
            j = json.loads(line)
            count += 1
            for t, (u, c) in j['use'].items():
                p = peaks.setdefault(t, [0, c])
                p[0] = max(p[0], u)
    return count, peaks


def print_peaks(cache):
    count, peaks = corpus_peaks(cache)
    print('\npeak use over %d programs' % count)
    for t, _, _, _ in USAGE:
        if t in peaks:
            print('    %-16s %6d of %6d' % (t, peaks[t][0], peaks[t][1]))


def synthetic_peaks():
    """The use of every table, and the host linker's time, for lk_synthetic's program."""
    import time
    import lk_synthetic
    builders, calls = lk_synthetic.program(1)
    with tempfile.TemporaryDirectory() as t:
        paths = [b.save(os.path.join(t, b.module_.name + '.lo')) for b in builders]
        env_path = os.path.join(t, 'env')
        with open(env_path, 'w') as f:
            f.write('cpu 6502\nzeropage $00 $FF\ncode $0200 $BFFF\ndata $C000 $EFFF\nstack $FF\n'
                    'exit call $F00F\n')
        out = os.path.join(t, 'probe.out')
        args = [env_path, 'p00', os.path.join(t, 'o.bin'), os.path.join(t, 'o.map')] + paths
        start = time.time()
        subprocess.run([sys.executable, os.path.abspath(__file__), '--probe'] + args,
                       env=dict(os.environ, LK_PROBE_OUT=out))
        took = time.time() - start
        with open(out) as f:
            j = json.loads(f.readline())
        size = sum(os.path.getsize(p) for p in paths)
    print('\nsynthetic program: %d object files, %d bytes; status %d; host linker %.2f s'
          % (len(paths), size, j['status'], took))
    for t, _, _, _ in USAGE:
        print('    %-16s %6d of %6d' % (t, j['use'][t][0], j['use'][t][1]))


def main(argv):
    if argv[:1] == ['--probe']:
        probe(argv[1:])
        return
    cache = os.path.join(tempfile.gettempdir(), 'lathe-lk-corpus')
    if '--cache' in argv:
        cache = argv[argv.index('--cache') + 1]
    print_tables()
    if '--corpus' in argv:
        print_peaks(cache)
    if '--synthetic' in argv:
        synthetic_peaks()


if __name__ == '__main__':
    main(sys.argv[1:])
