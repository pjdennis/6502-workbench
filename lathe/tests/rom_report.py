#!/usr/bin/env python3
"""Where the bytes of the BBC module image go: both tools, per bank, per module, per function
(lathe/docs/spikes.md, "Size for a 128 KB ROM: the source side, measured").

    python3 lathe/tests/rom_report.py [--dir DIR] [--functions N] [--lines]

Builds the module image as lathe/tests/test_bbc_toolchain.build_image does (the compiler,
`*LATHE`, from lathe/src/lathec-bbc.env, and the linker, `*LLINK`, from linker-bbc.env, each in
its ROM form) in DIR (default: a temporary directory), with lk_judged.py as the linker, which
links as link.py does and notes each bank's contents as the linker judges them (as written,
before zero page shrinks the code: the fit check of lk_place) and as placed. If DIR/listing and
DIR/judged exist already, it reads them instead. Then, from bbcrom.py's listing, the two maps
and those notes:

1. the budget: each bank's bytes in use and left over, the bytes of the two tools in all,
   against eight and seven banks of 16,272 bytes ($8050-$BFDF);
2. each tool's banks as judged and as placed, module by module;
3. each tool's parts: resident code, stubs and constants, banked code and constants, constants
   copied to a sideways slot; per module, with the lines of its source (code lines: not blank,
   not only a comment) and bytes of code per code line;
4. the modules both resident parts hold;
5. the N largest functions of each tool (default 25) with their code lines and bytes per line;
   --lines lists every function's.

A function's code lines are counted from its `func` line to the `end` in column 1 that closes it,
in the .lth file of its module (lathe/src/, lathe/rt/bbc/, lathe/rt/). The copies of a function
for other contexts are added to it.
"""
import argparse
import collections
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LATHE = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(LATHE, 'host', 'driver'))

import mapenv  # noqa: E402

BANK = 0xBFDF - 0x8050 + 1      # a bank's room for programs: $8050-$BFDF, 16,272 bytes
SEARCH = [os.path.join(LATHE, 'src'), os.path.join(LATHE, 'rt', 'bbc'), os.path.join(LATHE, 'rt')]
FUNC_RE = re.compile(r'^(?:pub\s+|inline\s+|recursive\s+|interrupt\s+)*(?:asm\s+)?func\s+(\w+)')
TWIN = {'inline': 'inlines'}
TOOLS = (('LATHE', 'lathe', 'lathec'), ('LLINK', 'llink', 'link'))
PARTS = ('res code', 'stubs', 'res const', 'bank code', 'bank const', 'slot const')


def build(d):
    """The image in d, with the judged sizes in d/judged."""
    os.environ['LATHE_LINKER'] = os.path.join(HERE, 'lk_judged.py')
    os.environ['LK_JUDGED_OUT'] = os.path.join(d, 'judged')
    import test_bbc_toolchain
    test_bbc_toolchain.build_image(d)


def source_of(module):
    name = TWIN.get(module, module)
    for s in SEARCH:
        p = os.path.join(s, name + '.lth')
        if os.path.isfile(p):
            return p
    return None


def code_line(line):
    s = line.strip()
    return bool(s) and not s.startswith(';')


_lines = {}


def lines(module):
    """(code lines of the module, {function: code lines})."""
    if module not in _lines:
        path = source_of(module)
        funcs, total = {}, 0
        if path:
            with open(path) as fh:
                text = fh.read().split('\n')
            total = sum(code_line(l) for l in text)
            cur, n = None, 0
            for l in text:
                m = FUNC_RE.match(l)
                if m:
                    cur, n = m.group(1), 0
                if cur is not None:
                    n += code_line(l)
                    if l.rstrip() == 'end':
                        funcs[cur] = n
                        cur = None
        _lines[module] = (total, funcs)
    return _lines[module]


def module_of(name):
    return name.split('.', 1)[0] if '.' in name else '(start)'


def tool_parts(map_path):
    """({module: Counter(part: bytes)}, [(function, bytes, where)]) of one tool's map."""
    entries = mapenv.read_map(map_path)
    rom = {e.number for e in entries if e.kind == 'W' and e.rom}
    mods = collections.defaultdict(collections.Counter)
    funcs = []
    for e in entries:
        m = module_of(e.name)
        if e.kind == 'F':
            where = 'resident' if e.bank is None else f'bank {e.bank}'
            mods[m]['res code' if e.bank is None else 'bank code'] += e.size
            funcs.append((e.base(), e.size, where))
        elif e.kind == 'T':
            mods[m]['stubs'] += e.size
        elif e.kind == 'D':
            mods[m]['res const' if e.bank is None else 'bank const' if e.bank in rom else 'slot const'] += e.size
    return mods, funcs


def judged_banks(path):
    """{tool: {bank: (judged, placed, [(module, judged, placed)])}} from lk_judged.py's notes;
    only the banks of the module (the ROM banks), not a region's constants."""
    out, tool = {}, None
    with open(path) as fh:
        for line in fh:
            if line.startswith('== '):
                tool = 'LATHE' if 'lathec' in line else 'LLINK'
                out[tool] = {}
            m = re.match(r'bank (\d+): judged (\d+) placed (\d+)  (.*)', line)
            if m:
                rows = [(x, int(j), int(p)) for x, j, p in re.findall(r'(\w+) (\d+)/(\d+)', m.group(4))]
                out[tool][int(m.group(1))] = (int(m.group(2)), int(m.group(3)), rows)
    return out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir')
    ap.add_argument('--functions', type=int, default=25)
    ap.add_argument('--lines', action='store_true')
    a = ap.parse_args(argv)
    d = os.path.abspath(a.dir or tempfile.mkdtemp(prefix='lathe-rom-'))
    if not (os.path.isfile(os.path.join(d, 'listing')) and os.path.isfile(os.path.join(d, 'judged'))):
        os.makedirs(d, exist_ok=True)
        build(d)
    with open(os.path.join(d, 'listing')) as fh:
        listing = fh.read()
    print(listing)

    # 1. The budget.
    module_code = int(re.search(r"the module's code and tables \((\d+) bytes\)", listing).group(1))
    used = left_in_code_banks = 0
    for n, rest in re.findall(r'^bank +(\d+): (.*)$', listing, re.M):
        inuse = sum(int(x) for x in re.findall(r'(\d+) bytes\)', rest))
        used += inuse
        if 'code and constants' in rest and 'free' not in rest:
            left_in_code_banks += BANK - inuse
    print(f'In use: {used} bytes, {module_code} of them the module\'s own code and tables. Left at the '
          f'ends of the code banks, which bbcrom.py fills with nothing else: {left_in_code_banks}.')
    for banks in (8, 7):
        print(f'  {banks} banks hold {banks * BANK}: {used - banks * BANK} bytes too many, packed perfectly')
    print()

    # 2. The banks as judged.
    judged = judged_banks(os.path.join(d, 'judged'))
    rom_banks = {}
    for tool, sub, main_name in TOOLS:
        windows = [e for e in mapenv.read_map(os.path.join(d, sub, 'work', main_name + '.map'))
                   if e.kind == 'W' and e.rom]
        rom_banks[tool] = {e.number for e in windows}
        tj = tp = 0
        print(f'*{tool}, its banks as judged and as placed:')
        for b, (j, p, rows) in sorted(judged[tool].items()):
            if b not in rom_banks[tool]:
                continue
            tj += j
            tp += p
            print(f'  bank {b}: judged {j}, placed {p}, {BANK - j} left as judged: '
                  + ', '.join(f'{m} {x}/{y}' for m, x, y in rows))
        print(f'  in all: judged {tj}, placed {tp}; {tj / BANK:.2f} banks as judged')
    print()

    # 3. Each tool's parts, per module; 5. the largest functions.
    resident = {}
    for tool, sub, main_name in TOOLS:
        mods, funcs = tool_parts(os.path.join(d, sub, 'work', main_name + '.map'))
        parts = collections.Counter()
        for c in mods.values():
            parts.update(c)
        print(f'*{tool}: ' + ', '.join(f'{k} {parts[k]}' for k in PARTS) + f'; in all {sum(parts.values())}')
        print(f'  {"module":10s} ' + ' '.join(f'{c:>10s}' for c in PARTS)
              + f' {"all":>7s} {"lines":>6s} {"b/line":>6s}')
        for m, c in sorted(mods.items(), key=lambda kv: -sum(kv[1].values())):
            total, _ = lines(m)
            code = c['res code'] + c['bank code']
            print(f'  {m:10s} ' + ' '.join(f'{c[k]:10d}' for k in PARTS) + f' {sum(c.values()):7d} {total:6d}'
                  + (f' {code / total:6.1f}' if total else ''))
        resident[tool] = {m: c['res code'] + c['res const'] + c['stubs'] for m, c in mods.items()
                          if c['res code'] + c['res const']}
        print()
        print(f'  Every function of *{tool}:' if a.lines else f'  The {a.functions} largest functions of *{tool}:')
        sizes = collections.Counter()
        for f, size, where in funcs:
            sizes[(f, where)] += size
        ranked = sorted(sizes.items(), key=lambda kv: -kv[1])
        for (f, where), size in (ranked if a.lines else ranked[:a.functions]):
            n = lines(module_of(f))[1].get(f.split('.', 1)[-1], 0)
            print(f'    {f:36s} {size:6d} {where:9s} {n:5d} lines' + (f' {size / n:5.1f}/line' if n else ''))
        print()

    # 4. In both resident parts.
    print('In both resident parts (code, constants and stubs of each module):')
    t1 = t2 = 0
    for m in sorted(set(resident['LATHE']) & set(resident['LLINK'])):
        print(f'  {m:10s} LATHE {resident["LATHE"][m]:6d}  LLINK {resident["LLINK"][m]:6d}')
        t1 += resident['LATHE'][m]
        t2 += resident['LLINK'][m]
    print(f'  {"in all":10s} LATHE {t1:6d}  LLINK {t2:6d}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
