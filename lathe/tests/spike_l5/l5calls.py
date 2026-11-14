"""Spike L5, question 3: which modules of the compiler call which, how big each is, and how
many far calls a placement in banks would make while compiling.

    python3 lathe/tests/spike_l5/l5calls.py [SOURCE.lth]

1. Sizes. The ten modules written in Lathe (the "twins") are measured: code bytes of every
   function some test program of lathe/src keeps (as size_report.py --report counts them).
   The six still to write are estimated from their lines of Python code at the bytes per
   code line the middle layers measured (7.4 to 8.6).
2. Static calls. For each pair of modules, the number of distinct (caller, callee) function
   pairs: from the CALL records of the twins' object files, and from the call sites in the
   host Python for all sixteen modules.
3. Dynamic calls. The host compiler compiles SOURCE (default lathe/src/reg.lth, the largest
   module written so far) in this process under sys.setprofile; every call from a function
   of one compiler module to one of another is counted, by pair of modules and by pair of
   functions. env (the host interface) counts as module sys.
4. Placements. For each placement in PLACEMENTS, the far calls the compile would make (a
   call is far when the callee is in a bank and the caller is not in the same bank), per
   line and per token of the source, and the cycles they cost at the measured 130 and 182
   cycles a far call; and the bytes of code resident (fixed) and in each bank.
5. Tables. Which modules name each table; where each can go under a placement (fixed
   memory, the bank of the only code that names it, or a data bank when only fixed code
   names it); and how often the compile enters, from another module, a function that
   touches a table proposed for the data bank (each entry would switch the data bank in).
"""
import ast
import os
import sys
import tempfile
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.dirname(HERE)
LATHE = os.path.dirname(TESTS)
HOST = os.path.join(LATHE, 'host')
sys.path.insert(0, TESTS)

import size_report  # noqa: E402

TWINS = size_report.MODULES
TO_WRITE = ('inline', 'gen', 'asmblock', 'expr', 'decl', 'lathec')
COMPILER = TWINS + TO_WRITE
RUNTIME = ('sys', 'rt_math', 'rt_frame')     # always fixed; measured where the twins use them
BYTES_PER_LINE = (7.4, 8.6)    # measured range of fbuf, cond, out, reg (bytes a code line)
FAR_CYCLES = (130, 182)         # measured far call and return: fast stub, compact stub
ROUTINE = 101                   # measured bytes of the compact far-call routine (rt_bank.s)
STUB = 6                        # measured bytes of a compact stub
RESIDENT = 16384                # goal 15: compiler code resident at once
WINDOW = 0x7000                 # Wendy 2's window, $8000-$EFFF

# Placements to try: module -> bank number, or 0 for fixed memory. sys (env) is always fixed.
LOW = {'err': 0, 'kernel': 0, 'src': 0, 'typetab': 0, 'fold': 0}
PLACEMENTS = {
    'D (proposed): lex, fbuf fixed; front end bank 1; code generation bank 2; asm bank 3':
        dict(LOW, lex=0, fbuf=0, lathec=1, decl=1, expr=1, inline=1, asmblock=3,
             gen=2, reg=2, cond=2, out=2),
    'E (fallback of D): as D with cond in bank 3 beside asmblock':
        dict(LOW, lex=0, fbuf=0, lathec=1, decl=1, expr=1, inline=1, asmblock=3,
             gen=2, reg=2, cond=3, out=2),
    'A: lex and fbuf fixed; front end in bank 1; code generation in bank 2':
        dict(LOW, lex=0, fbuf=0, lathec=1, decl=1, expr=1, inline=1, asmblock=1,
             gen=2, reg=2, cond=2, out=2),
    'B: fbuf and out fixed; lex with the front end in bank 1; gen, reg, cond in bank 2':
        dict(LOW, fbuf=0, out=0, lex=1, lathec=1, decl=1, expr=1, inline=1, asmblock=1,
             gen=2, reg=2, cond=2),
    'C: three banks: front end, gen+cond, reg+out; lex and fbuf fixed':
        dict(LOW, lex=0, fbuf=0, lathec=1, decl=1, expr=1, inline=1, asmblock=1,
             gen=2, cond=2, reg=3, out=3),
    'by phase: lex+decl, expr, gen+cond, reg+fbuf+out': {
        'err': 0, 'kernel': 0, 'src': 0, 'typetab': 0, 'fold': 0,
        'lex': 1, 'decl': 1, 'inline': 1, 'lathec': 0,
        'expr': 2, 'asmblock': 2,
        'gen': 3, 'cond': 3,
        'reg': 4, 'fbuf': 4, 'out': 4},
    'front and back: lex+src+decl+expr+inline, gen+cond+reg+fbuf+out+asm': {
        'err': 0, 'kernel': 0, 'typetab': 0, 'fold': 0, 'lathec': 0, 'src': 0,
        'lex': 1, 'decl': 1, 'expr': 1, 'inline': 1,
        'gen': 2, 'cond': 2, 'reg': 2, 'fbuf': 2, 'out': 2, 'asmblock': 2},
    'one bank of upper layers, the rest fixed': {
        'err': 0, 'kernel': 0, 'src': 0, 'lex': 0, 'typetab': 0, 'fold': 0, 'fbuf': 0,
        'out': 0, 'reg': 0, 'cond': 0, 'lathec': 0,
        'gen': 1, 'expr': 1, 'decl': 1, 'inline': 1, 'asmblock': 1},
    'code generation fixed, front end and declarations banked': {
        'err': 0, 'kernel': 0, 'src': 0, 'typetab': 0, 'fold': 0, 'lathec': 0,
        'reg': 0, 'fbuf': 0, 'gen': 0, 'cond': 0, 'out': 0,
        'lex': 1, 'expr': 1, 'inline': 1,
        'decl': 2, 'asmblock': 3},
}


def measured_sizes(out_dir):
    """{module: code bytes} of the twins, and {module: {function: bytes}}."""
    maps = {name: size_report.read_map(size_report.build(name, out_dir))
            for name in size_report.PROGRAMS}
    fsize = {}
    for items in maps.values():
        for kind, _, size, name in items:
            if kind == 'F' and size_report.module_of(name) in TWINS + RUNTIME \
                    and '@' not in name:
                fsize[name] = max(size, fsize.get(name, 0))
    per = Counter()
    for name, size in fsize.items():
        per[size_report.module_of(name)] += size
    return per, fsize


def object_calls(out_dir):
    """Counter of (caller module, callee module): distinct function pairs in the CALL records."""
    import lo
    pairs = Counter()
    for m in TWINS:
        module = None
        for name in size_report.PROGRAMS:
            path = os.path.join(out_dir, name, 'work', m + '.lo')
            if os.path.exists(path):
                module = lo.load(path)
                break
        if module is None:
            continue
        for f in module.functions():
            seen = set()
            for c in f.calls:
                callee = size_report.module_of(module.sym_name(c.callee))
                key = (module.sym_name(f.sym), module.sym_name(c.callee))
                if callee != m and key not in seen:
                    seen.add(key)
                    pairs[(m, callee)] += 1
    return pairs


def host_calls():
    """Counter of (caller module, callee module): distinct function pairs in the host Python;
    and {caller module: set of (callee module, function)}."""
    pairs = Counter()
    callees = defaultdict(set)
    for m in COMPILER:
        with open(os.path.join(HOST, m + '.py')) as f:
            tree = ast.parse(f.read())
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef)]:
            seen = set()
            for node in ast.walk(fn):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                        and isinstance(node.func.value, ast.Name):
                    callee = node.func.value.id
                    callee = 'sys' if callee == 'env' else callee
                    if callee in COMPILER + ('sys',) and callee != m:
                        key = (fn.name, callee, node.func.attr)
                        callees[m].add((callee, node.func.attr))
                        if key not in seen:
                            seen.add(key)
                            pairs[(m, callee)] += 1
    return pairs, callees


def stubs_needed(callees, place):
    """Functions in a bank called from outside that bank: each needs a stub in fixed memory."""
    need = set()
    for caller, targets in callees.items():
        for callee, f in targets:
            pb = place.get(callee, 0)
            if pb and place.get(caller, 0) != pb:
                need.add((callee, f))
    return len(need)


def trace_compile(source, work):
    """Compiles SOURCE with the host compiler in this process, counting calls between modules.
    Returns (module pairs, function pairs, calls of lex.next, all calls)."""
    sys.path.insert(0, HOST)
    import env
    import lathec
    names = {os.path.join(HOST, m + '.py'): m for m in COMPILER}
    names[os.path.join(HOST, 'env.py')] = 'sys'
    mods = Counter()
    funcs = Counter()
    total = [0]
    ntokens = [0]

    def profile(frame, event, arg):
        if event != 'call':
            return
        callee = names.get(frame.f_code.co_filename)
        if callee is None:
            return
        total[0] += 1
        if callee == 'lex' and frame.f_code.co_name == 'next':
            ntokens[0] += 1
        back = frame.f_back
        caller = names.get(back.f_code.co_filename) if back else None
        if caller is not None and caller != callee:
            mods[(caller, callee)] += 1
            funcs[(caller + '.' + back.f_code.co_name,
                   callee + '.' + frame.f_code.co_name)] += 1

    env.start(['-c6502', source, work, work])
    sys.setprofile(profile)
    try:
        lathec.main()
    except SystemExit as e:
        if e.code not in (0, None):
            raise
    finally:
        sys.setprofile(None)
    return mods, funcs, ntokens[0], total[0]


def table_users():
    """[(module, table, bytes, set of modules that name it)] for every module-level array of
    the compiler (sized as memory_report.py sizes them), and the text memory (env.mem)."""
    sys.path.insert(0, HOST)
    import memory_report
    named = defaultdict(set)
    for m in COMPILER + ('env',):
        with open(os.path.join(HOST, m + '.py')) as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                named[(node.value.id, node.attr)].add(m)
    rows = []
    for m in COMPILER:
        for name, n, width in memory_report.arrays(m):
            rows.append((m, name, n * width, named[(m, name)] | {m}))
    rows.append(('kernel', 'text memory (env.mem)', memory_report.text_size(),
                 named[('env', 'mem')] | {'kernel'}))
    return rows


def touching(module, tables):
    """Functions of host MODULE whose body indexes one of TABLES (names of its arrays)."""
    with open(os.path.join(HOST, module + '.py')) as f:
        tree = ast.parse(f.read())
    found = set()
    for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef)]:
        for node in ast.walk(fn):
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) \
                    and node.value.id in tables:
                found.add(module + '.' + fn.name)
    return found


# The tables placement D puts in a data bank, by owner: each entry into a function that
# touches one, from another module, is a map block (switch the data bank in and back).
DATA_BANK = {'kernel': ('names',), 'fbuf': ('buffer', 'label_offset', 'label_uses')}


def table_placement(rows, place):
    """Where each table can go under a placement: 'own bank N' when its users are all in bank
    N; 'data bank' when its users are all in fixed memory (they would reach it in a map
    block); else 'fixed'."""
    out = []
    for m, name, size, users in rows:
        where = {place.get(u, 0) for u in users if u in COMPILER}
        if where == {0}:
            kind = 'data bank'
        elif len(where) == 1:
            kind = 'own bank %d' % where.pop()
        else:
            kind = 'fixed'
        out.append((kind, m, name, size, users))
    return out


def far_calls(mods, place):
    n = 0
    for (a, b), count in mods.items():
        pa, pb = place.get(a, 0), place.get(b, 0)
        if pb and pa != pb:
            n += count
        elif pa and not pb:
            pass                    # into fixed memory: a plain JSR
    return n


def main(argv):
    source = os.path.abspath(argv[0]) if argv else os.path.join(LATHE, 'src', 'reg.lth')
    with tempfile.TemporaryDirectory(prefix='l5calls_') as d:
        sizes, fsize = measured_sizes(d)
        objpairs = object_calls(d)
        # The interfaces the source imports: the twins' builds hold them all.
        work = os.path.join(d, 'trace')
        os.makedirs(work)
        for name in size_report.PROGRAMS:
            w = os.path.join(d, name, 'work')
            for f in os.listdir(w):
                if f.endswith('.li') and not os.path.exists(os.path.join(work, f)):
                    with open(os.path.join(w, f), 'rb') as src, \
                            open(os.path.join(work, f), 'wb') as dst:
                        dst.write(src.read())
        mods, funcs, tokens, total = trace_compile(source, work)
    with open(source) as f:
        lines = sum(1 for _ in f)

    est = {}
    print('Module sizes (bytes of code; measured for the twins, estimated for the rest)')
    for m in COMPILER:
        if m in sizes:
            est[m] = (sizes[m], sizes[m])
            print('  %-9s %6d  measured' % (m, sizes[m]))
        else:
            _, code_lines = size_report.python_lines(m)
            lo, hi = (int(code_lines * b) for b in BYTES_PER_LINE)
            est[m] = (lo, hi)
            print('  %-9s %6d to %6d  estimated (%d code lines)' % (m, lo, hi, code_lines))
    print('  %-9s %6d to %6d' % ('total', sum(v[0] for v in est.values()),
                                 sum(v[1] for v in est.values())))
    runtime = sum(sizes[m] for m in RUNTIME)
    print('  run-time modules %s (always fixed): %d' % (' '.join(RUNTIME), runtime))
    print()
    print('Static calls, distinct function pairs, caller -> callee (objects of the twins | host)')
    hostpairs, callees = host_calls()
    for (a, b) in sorted(set(hostpairs) | set(objpairs)):
        print('  %-9s -> %-9s %4s | %4d' % (a, b, objpairs.get((a, b), '-'),
                                          hostpairs.get((a, b), 0)))
    print()
    print('Dynamic calls compiling %s: %d lines, %d tokens, %d calls into compiler functions'
          % (os.path.relpath(source, LATHE), lines, tokens, total))
    cross = sum(mods.values())
    print('  between modules: %d (%.0f a line, %.1f a token)' % (cross, cross / lines,
                                                             cross / tokens))
    for (a, b), n in mods.most_common(40):
        print('  %-9s -> %-9s %8d  %7.1f a line' % (a, b, n, n / lines))
    print()
    print('The 30 busiest calls between modules')
    for (a, b), n in funcs.most_common(30):
        print('  %-28s -> %-28s %8d' % (a, b, n))
    print()
    rows = table_users()
    for name, place in PLACEMENTS.items():
        fixed = [m for m in COMPILER if not place.get(m, 0)]
        banks = defaultdict(list)
        for m in COMPILER:
            if place.get(m, 0):
                banks[place[m]].append(m)
        n = far_calls(mods, place)
        stubs = stubs_needed(callees, place)
        tables = Counter()
        for kind, _, _, size, _ in table_placement(rows, place):
            tables[kind] += size
        print('Placement: %s' % name)
        print('  tables: %s' % ', '.join('%s %d' % kv for kv in sorted(tables.items())))
        lo = sum(est[m][0] for m in fixed) + runtime + ROUTINE + STUB * stubs
        hi = sum(est[m][1] for m in fixed) + runtime + ROUTINE + STUB * stubs
        print('  fixed: %s, run-time, far-call routine (%d), %d stubs (%d each): %d to %d bytes%s'
              % (' '.join(fixed), ROUTINE, stubs, STUB, lo, hi,
                 '' if hi <= RESIDENT else '  OVER %d' % RESIDENT))
        for b in sorted(banks):
            lo = sum(est[m][0] for m in banks[b])
            hi = sum(est[m][1] for m in banks[b])
            print('  bank %d: %s: %d to %d bytes%s' % (b, ' '.join(banks[b]), lo, hi,
                                                       '' if hi <= WINDOW else '  OVER %d' % WINDOW))
        print('  far calls: %d, %.1f a line, %.2f a token; %d to %d cycles a line'
              % (n, n / lines, n / tokens, n * FAR_CYCLES[0] / lines,
                 n * FAR_CYCLES[1] / lines))
        print()
    print('Entries from other modules into functions that touch a table of the data bank')
    entries = 0
    for owner, tables in DATA_BANK.items():
        fns = touching(owner, tables)
        n = sum(c for (a, b), c in funcs.items() if b in fns)
        entries += n
        print('  %-7s %-30s %6d (%.1f a line), %d functions' % (owner, ' '.join(tables), n,
                                                                n / lines, len(fns)))
    print('  all: %.1f a line' % (entries / lines))
    print()
    first = next(iter(PLACEMENTS))
    print('Tables under placement %s' % first)
    sums = Counter()
    for kind, m, name, size, users in sorted(table_placement(rows, PLACEMENTS[first])):
        sums[kind] += size
        if size >= 200:
            print('  %-11s %-9s %-24s %6d  named by %s' % (kind, m, name, size,
                                                         ' '.join(sorted(users))))
    for kind, size in sorted(sums.items()):
        print('  total %-11s %6d' % (kind, size))


if __name__ == '__main__':
    main(sys.argv[1:])
