#!/usr/bin/env python3
"""The functions a tool keeps in fixed memory because of `with` blocks, from a linked build
(lathe/docs/spikes.md, "One ROM for every BBC: a study (measured)").

The linker keeps in fixed memory, when their module is placed in a bank, every function with a
`with` block (a kind 6 fix-up) and everything that runs inside one (lathe/docs/configurations.md,
"Functions kept in fixed memory"); the map ends the F line of each with `k=N`. For each such
function this gives:

  - its bytes as placed (the map);
  - the regions of its own blocks (the region of the variable or constant each kind 6 fix-up
    names, from the RGN records of every object), or, for a function kept only because it runs
    inside another's block, the regions of the blocks it runs inside (the callers' regions,
    followed down the calls);
  - why it is kept: `block` (it has one), `inside` (only because a call inside a block reaches
    it), or both;
  - whether it loops while a region is mapped: for a function with a block, a `loop`, `for` or
    `while` inside one of its blocks, or a call inside a block of a kept function that does; for
    a function kept only for running inside a block, any loop in its body (all of it runs with
    the region mapped). Read from the twin's source, whose blocks and loops are indented
    two spaces a level and end with `end` at the same indentation;
  - how often it was entered and the cycles spent in it, when histograms of a run are given (the
    study's emulator writes one per run with LATHE_PCHIST: index, count, cycles a line; the index
    of an address below $8000 is the address).

And the rest of the resident part: fixed functions not kept, by module, the stubs and the fixed
constants.

    python3 lathe/tests/with_census.py WORK_DIR MAP [--hist FILE...] [--tsv OUT]

census() and resident() are the functions; the command prints both.
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'host', 'driver'))

import lo  # noqa: E402

LATHE = os.path.join(HERE, '..')
SOURCE_DIRS = [os.path.join(LATHE, 'src'), os.path.join(LATHE, 'rt', 'bbc'), os.path.join(LATHE, 'rt')]
CALL_INSIDE = 4                     # CALL flag bit 2: the call is made inside a block
LOOP_WORDS = ('loop', 'for', 'while')


class Kept:
    __slots__ = ('name', 'module', 'address', 'size', 'bank', 'kept', 'block', 'inside', 'regions',
                 'loop', 'loop_why', 'calls', 'cycles', 'inside_callees', 'callers_inside')

    def __init__(self, name, address, size, bank):
        self.name, self.address, self.size, self.bank = name, address, size, bank
        self.module = name.split('.')[0]
        self.kept = bank is not None        # k=N: kept; else fixed because its module is
        self.block = False
        self.inside = False
        self.regions = set()
        self.loop = False
        self.loop_why = ''
        self.calls = None
        self.cycles = None
        self.inside_callees = set()
        self.callers_inside = set()

    def why(self):
        w = 'block+inside' if self.block and self.inside else 'block' if self.block else 'inside'
        return w if self.kept else w + ' (fixed module)'


def read_map(map_path):
    """F lines: [(name, address, size, rest)], T lines: [(name, address, size)], D lines."""
    funcs, stubs, data = [], [], []
    with open(map_path) as f:
        lines = f.readlines()
    for line in lines:
        p = line.split()
        if len(p) < 4 or p[0] not in ('F', 'T', 'D'):
            continue
        row = (p[3], int(p[1], 16), int(p[2], 16), p[4:])
        (funcs if p[0] == 'F' else stubs if p[0] == 'T' else data).append(row)
    return funcs, stubs, data


def load_objects(work_dir):
    mods = {}
    for f in sorted(os.listdir(work_dir)):
        if f.endswith('.lo'):
            m = lo.load(os.path.join(work_dir, f))
            mods[m.name] = m
    return mods


def source_of(module, dirs=SOURCE_DIRS):
    for d in dirs:
        p = os.path.join(d, module + '.lth')
        if os.path.exists(p):
            return p
    return None


def _code_lines(path):
    """(indentation, text) of each line, comments and strings blanked."""
    out = []
    with open(path, encoding='latin-1') as f:
        raws = f.read().split('\n')
    for raw in raws:
        line = re.sub(r'"[^"]*"', '""', raw.rstrip('\n'))
        line = re.sub(r"'[^']*'", "''", line)
        line = line.split(';', 1)[0].rstrip()
        out.append((len(line) - len(line.lstrip(' ')), line.strip()))
    return out


FUNC_RE = re.compile(r'^(?:pub\s+)?(?:inline\s+|asm\s+|recursive\s+|interrupt\s+)*func\s+([A-Za-z_$][\w$]*)')


def functions_of(path):
    """{function name: [(indent, text)] of its body} from a twin's source."""
    lines = _code_lines(path)
    out = {}
    i = 0
    while i < len(lines):
        ind, text = lines[i]
        m = FUNC_RE.match(text) if ind == 0 else None
        if m:
            j = i + 1
            while j < len(lines) and not (lines[j][0] == 0 and lines[j][1] == 'end'):
                j += 1
            out[m.group(1)] = lines[i + 1:j]
            i = j
        i += 1
    return out


def first_word(text):
    m = re.match(r'[A-Za-z_]+', text)
    return m.group(0) if m else ''


def blocks_of(body):
    """[(lines of the block)] for each outermost `with ... do` of a body."""
    out = []
    i = 0
    while i < len(body):
        ind, text = body[i]
        if first_word(text) == 'with' and text.endswith(' do'):
            j = i + 1
            while j < len(body) and not (body[j][0] == ind and body[j][1] == 'end'):
                j += 1
            out.append(body[i + 1:j])
            i = j
        i += 1
    return out


def loops_in(lines):
    return any(first_word(t) in LOOP_WORDS for _, t in lines)


def census(work_dir, map_path, hists=(), source_dirs=SOURCE_DIRS):
    """[Kept] in map order: every function in fixed memory that is kept, has a block or runs
    inside one; source_dirs are where the modules' sources are looked for."""
    funcs, _, _ = read_map(map_path)
    mods = load_objects(work_dir)
    region_of = {}                  # variable or constant name -> region
    for m in mods.values():
        for x in m.items:
            if isinstance(x, (lo.Var, lo.Data)) and x.region:
                region_of[m.sym_name(x.sym)] = x.region.upper()
    func_obj = {}
    for m in mods.values():
        for fn in m.functions():
            func_obj[m.sym_name(fn.sym)] = (m, fn)
    kept = {}                       # every function in fixed memory (below $8000)
    for name, address, size, rest in funcs:
        k = [r for r in rest if r.startswith('k=')]
        if address < 0x8000 and name in func_obj:
            kept[name] = Kept(name, address, size, int(k[0][2:]) if k else None)
    all_calls = {}                  # name -> [(callee, inside)]
    for name, (m, fn) in func_obj.items():
        all_calls[name] = [(m.sym_name(c.callee), bool(c.flags & CALL_INSIDE)) for c in fn.calls]
    for name, k in kept.items():
        m, fn = func_obj[name]
        for x in fn.fixes:
            if x.kind == lo.FX_BANK:
                k.block = True
                target = m.sym_name(x.sym)
                k.regions.add(region_of.get(target, '?' + target))
        for callee, inside in all_calls[name]:
            if inside and callee in kept:
                k.inside_callees.add(callee)
                kept[callee].callers_inside.add(name)
    # Inside: reached by a call inside a block, at any depth (as lk_scan.keep_called has it).
    inside_regions = {}             # name -> the regions of the blocks it runs inside
    for k in kept.values():
        for c in k.inside_callees:
            inside_regions.setdefault(c, set()).update(k.regions)
    changed = True
    while changed:                  # what an inside function calls runs inside too
        changed = False
        for n in list(inside_regions):
            for callee, _ in all_calls.get(n, ()):
                if callee in kept:
                    have = inside_regions.setdefault(callee, set())
                    if not inside_regions[n] <= have or not have and callee not in inside_regions:
                        have |= inside_regions[n]
                        changed = True
    for n, rs in inside_regions.items():
        if n in kept:
            kept[n].inside = True
            if not kept[n].block:
                kept[n].regions |= rs
    # Loops, from the source.
    bodies = {}
    for k in kept.values():
        if k.module not in bodies:
            p = source_of(k.module, source_dirs)
            bodies[k.module] = functions_of(p) if p else {}
    for k in kept.values():
        body = bodies[k.module].get(k.name.split('.', 1)[1])
        if body is None:
            k.loop_why = 'no source'
            continue
        if k.block:
            for b in blocks_of(body):
                if loops_in(b):
                    k.loop, k.loop_why = True, 'loop in its block'
        if not k.loop and k.inside and not k.block and loops_in(body):
            k.loop, k.loop_why = True, 'loop in its body, run inside a block'
    changed = True
    while changed:          # a block that calls (inside it) a kept function that loops
        changed = False
        for k in kept.values():
            if k.block and not k.loop and any(kept[c].loop for c in k.inside_callees):
                k.loop, k.loop_why, changed = True, 'calls a looping function in its block', True
    if hists:
        counts, cycles = read_hists(hists)
        for k in kept.values():
            k.calls = counts.get(k.address, 0)
            k.cycles = sum(cycles.get(a, 0) for a in range(k.address, k.address + k.size))
    return [kept[n] for n, *_ in funcs if n in kept and (kept[n].kept or kept[n].block or kept[n].inside)]


def read_hists(paths):
    counts, cycles = {}, {}
    for p in paths:
        with open(p) as f:
            lines = f.readlines()
        for line in lines:
            i, c, y = line.split()
            i = int(i)
            counts[i] = counts.get(i, 0) + int(c)
            cycles[i] = cycles.get(i, 0) + int(y)
    return counts, cycles


def resident(map_path, hists=()):
    """The resident part (code, stubs and constants below $8000, from $0800): {group: bytes},
    the kept functions as one group, with the cycles spent in each group when histograms are
    given."""
    funcs, stubs, data = read_map(map_path)
    counts, cycles = read_hists(hists) if hists else ({}, {})
    groups = {}

    def add(g, address, size):
        b, c = groups.get(g, (0, 0))
        groups[g] = (b + size, c + sum(cycles.get(a, 0) for a in range(address, address + size)))
    for name, address, size, rest in funcs:
        if 0x800 <= address < 0x8000:
            add('kept' if any(r.startswith('k=') for r in rest) else name.split('.')[0], address, size)
    for name, address, size, _ in stubs:
        if 0x800 <= address < 0x8000:
            add('stubs', address, size)
    for name, address, size, _ in data:
        if 0x800 <= address < 0x8000:
            add('constants', address, size)
    return groups


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('work_dir')
    ap.add_argument('map')
    ap.add_argument('--hist', nargs='*', default=[])
    ap.add_argument('--tsv')
    a = ap.parse_args(argv)
    rows = census(a.work_dir, a.map, a.hist)
    lines = ['name\tbytes\tregions\twhy\tloop\tloop_why\tcalls\tcycles']
    for k in rows:
        lines.append('\t'.join(str(x) for x in (k.name, k.size, ','.join(sorted(k.regions)), k.why(),
                                               'loop' if k.loop else 'single', k.loop_why,
                                               '' if k.calls is None else k.calls,
                                               '' if k.cycles is None else k.cycles)))
    text = '\n'.join(lines) + '\n'
    if a.tsv:
        open(a.tsv, 'w').write(text)
    print(text)
    tot = {}
    for k in rows:
        key = ('loop' if k.loop else 'single', k.why())
        if not k.kept and not k.block:
            continue                # a fixed module's function called inside a block: not counted
        n, b = tot.get(key, (0, 0))
        tot[key] = (n + 1, b + k.size)
    for key, (n, b) in sorted(tot.items()):
        print('%-8s %-13s %4d functions %6d bytes' % (key[0], key[1], n, b))
    w = [k for k in rows if k.kept or k.block]
    print('kept or with a block: %d functions, %d bytes; loop %d bytes, single %d bytes' % (
        len(w), sum(k.size for k in w), sum(k.size for k in w if k.loop),
        sum(k.size for k in w if not k.loop)))
    g = resident(a.map, a.hist)
    print('resident part by group (bytes, cycles):')
    for name, (b, c) in sorted(g.items(), key=lambda x: -x[1][0]):
        print('  %-12s %6d %14d' % (name, b, c))
    print('  %-12s %6d' % ('total', sum(b for b, _ in g.values())))


if __name__ == '__main__':
    main(sys.argv[1:])
