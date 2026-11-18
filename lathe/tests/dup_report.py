#!/usr/bin/env python3
"""Repeated logic in the tools' Lathe source: sequences of statements written more than once, and
functions that are near copies of each other (lathe/docs/spikes.md, "The tools' source, a second
look (measured)").

    python3 lathe/tests/dup_report.py [--tool lathec|link|both] [--lines K] [--min N]
                                      [--pairs R] [--top N] [--map MAP]...

1. **Repeated sequences.** Each function's body is cut into statements (one a line, comments and
   blank lines left out, a line ended by `,` or `(` or an operator joined to the next). Every run
   of K consecutive statements (default 2) is written out in a normal form: the function's own
   locals and parameters become L1, L2 ... in order of first use in the run, numbers stay. A form
   found at least N times (default 3) in the tool is listed with its count and where it is, the
   longest and commonest first; a run inside a longer run that is listed with the same count is
   left out.
2. **Near copies.** Each function's statements, every name kept but its locals renumbered, are
   compared with every other function's of a similar length (difflib's ratio over statements);
   pairs at ratio R or above (default 0.6) are listed, with the statements they share.

With --map (a map the linker wrote for the tool, more than one for both tools) each function
listed has its bytes as placed, and the sequences an estimate of their bytes (the function's
bytes a statement, times the statements, times the count less one): what a helper would save at
most, before its call costs.
"""
import argparse
import collections
import difflib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), 'src')

COMPILER = ('lathec', 'lex', 'src', 'err', 'kernel', 'typetab', 'fbuf', 'fold', 'cond', 'reg', 'gen',
            'out', 'parts', 'expr', 'decl', 'inlines', 'asmblock')
LINKER = ('link', 'lk_alloc', 'lk_boot', 'lk_emit', 'lk_envf', 'lk_err', 'lk_file', 'lk_fix', 'lk_graph',
          'lk_map', 'lk_name', 'lk_op', 'lk_out', 'lk_place', 'lk_rec', 'lk_scan', 'lk_sym', 'lk_tab',
          'lk_win')

FUNC_RE = re.compile(r'^(?:pub\s+|inline\s+|recursive\s+|interrupt\s+)*(?:asm\s+)?func\s+(\w+)\s*\(([^)]*)\)')
VAR_RE = re.compile(r'^\s*var\s+(\w+)\s*:')
WORD_RE = re.compile(r'[A-Za-z_]\w*|\$[0-9A-Fa-f]+|%[01]+|\d+|"(?:[^"\\]|\\.)*"|\'.\'|<<|>>|[<>=!]=|\S')
CONT_RE = re.compile(r'(,|\(|\[|\bor|\band|[-+*/&|^=<>])$')


def strip_comment(line):
    """The line without its comment (a `;` outside a string or a character)."""
    out, quote = [], None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote and line[i - 1] != '\\':
                quote = None
        elif ch in '"\'':
            quote = ch
        elif ch == ';':
            break
        out.append(ch)
    return ''.join(out).rstrip()


class Function:
    def __init__(self, module, name, params, first):
        self.module, self.name, self.first = module, name, first
        self.locals = set(params)
        self.statements = []        # (line number, text)

    @property
    def full(self):
        return f'{self.module}.{self.name}'


def functions(module):
    """The functions of lathe/src/MODULE.lth with their statements."""
    found, current, pending, start = [], None, '', 0
    with open(os.path.join(SRC, module + '.lth')) as f:
        for number, raw in enumerate(f, 1):
            line = strip_comment(raw)
            if current is None:
                m = FUNC_RE.match(line)
                if m and not line.lstrip().startswith('forward') and ' at ' not in line:
                    params = [p.split(':')[0].strip() for p in m.group(2).split(',') if ':' in p]
                    current = Function(module, m.group(1), params, number)
                    if line.rstrip().endswith(' end') or 'asm func' in line:
                        current = None if 'asm func' not in line else current
                continue
            if raw.startswith('end'):
                found.append(current)
                current = None
                continue
            text = line.strip()
            if not text:
                continue
            m = VAR_RE.match(text)
            if m:
                current.locals.add(m.group(1))
            if pending:
                pending += ' ' + text
            else:
                pending, start = text, number
            if CONT_RE.search(text) and not text.startswith('end'):
                continue
            current.statements.append((start, ' '.join(pending.split())))
            pending = ''
    return found


def normal(texts, local_names):
    """The statements with the function's own names numbered in order of first use."""
    names, out = {}, []
    for t in texts:
        words = []
        for w in WORD_RE.findall(t):
            if w in local_names:
                w = names.setdefault(w, f'L{len(names) + 1}')
            words.append(w)
        out.append(' '.join(words))
    return tuple(out)


def load(modules):
    return [f for m in modules for f in functions(m)]


def read_sizes(maps):
    sizes = collections.Counter()
    for path in maps:
        with open(path) as f:
            for line in f:
                p = line.split()
                if len(p) >= 4 and p[0] == 'F':
                    sizes[p[3]] += int(p[2], 16)
    return sizes


def per_statement(fn, sizes):
    if not sizes or fn.full not in sizes or not fn.statements:
        return None
    return sizes[fn.full] / len(fn.statements)


def sequences(funcs, k, least, sizes):
    """[(count, form, [(function, line)], estimated bytes or None)] of the runs of k statements
    found at least `least` times."""
    where = collections.defaultdict(list)
    for fn in funcs:
        texts = [t for _, t in fn.statements]
        for i in range(len(texts) - k + 1):
            run = texts[i:i + k]
            if all(t in ('end', 'else') or t.startswith('var ') for t in run):
                continue
            where[normal(run, fn.locals)].append((fn, fn.statements[i][0]))
    out = []
    for form, sites in where.items():
        if len(sites) < least:
            continue
        est = None
        if sizes:
            each = [per_statement(fn, sizes) for fn, _ in sites]
            each = [e for e in each if e is not None]
            if each:
                est = round(sum(each) / len(each) * k * (len(sites) - 1))
        out.append((len(sites), form, sites, est))
    out.sort(key=lambda r: (-(r[3] or 0), -r[0]))
    return out


def near_copies(funcs, ratio):
    """[(ratio, f, g, shared statements)] for the pairs of functions alike at `ratio` or more."""
    forms = [(fn, normal([t for _, t in fn.statements], fn.locals)) for fn in funcs if len(fn.statements) >= 4]
    out = []
    for i, (f, a) in enumerate(forms):
        for g, b in forms[i + 1:]:
            if min(len(a), len(b)) < ratio * max(len(a), len(b)):
                continue
            sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
            if sm.quick_ratio() < ratio:
                continue
            r = sm.ratio()
            if r >= ratio:
                out.append((r, f, g, sum(m.size for m in sm.get_matching_blocks())))
    out.sort(key=lambda r: -r[0])
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--tool', choices=('lathec', 'link', 'both'), default='both')
    ap.add_argument('--lines', type=int, default=2)
    ap.add_argument('--min', type=int, default=3)
    ap.add_argument('--pairs', type=float, default=0.6)
    ap.add_argument('--top', type=int, default=40)
    ap.add_argument('--map', action='append', default=[])
    args = ap.parse_args(argv)
    sizes = read_sizes(args.map)
    tools = {'lathec': [COMPILER], 'link': [LINKER], 'both': [COMPILER, LINKER]}[args.tool]
    for modules in tools:
        funcs = load(modules)
        title = 'the compiler' if modules is COMPILER else 'the linker'
        print(f'== {title}: {len(funcs)} functions, {sum(len(f.statements) for f in funcs)} statements')
        print(f'-- runs of {args.lines} statements found {args.min} times or more')
        shown = 0
        for count, form, sites, est in sequences(funcs, args.lines, args.min, sizes):
            mods = collections.Counter(fn.module for fn, _ in sites)
            print(f'{count:4d}x  ~{est if est is not None else "?"} bytes  ' + ' | '.join(form))
            print('        ' + ', '.join(f'{m} {n}' for m, n in mods.most_common()))
            shown += 1
            if shown >= args.top:
                break
        print(f'-- near copies, ratio {args.pairs} or more')
        for r, f, g, shared in near_copies(funcs, args.pairs)[:args.top]:
            sf = sizes.get(f.full, '?') if sizes else '?'
            sg = sizes.get(g.full, '?') if sizes else '?'
            print(f'{r:.2f}  {f.full} ({len(f.statements)} st, {sf} b) ~ {g.full} ({len(g.statements)} st, {sg} b)'
                  f'  {shared} shared')
        print()


if __name__ == '__main__':
    main()
