"""Multi-module Lathe programs of a given size and of the shape of real Lathe code, for measuring
what the tools compile and link (lathe/docs/bbc.md, "A program of real size on the 32K Model
B").

    python3 lathe/tests/gen_program.py OUTDIR MODULES FUNCTIONS [CALLS] [SEED] [BODY]

writes the program's modules to OUTDIR (genmain.lth, the main, and gen01.lth ... genNN.lth) with
genmain.expected.out, what it prints, and says how many lines and functions it has.

The shape is that of the tools' own code, measured from their objects and sources (lk_ram32.shape
and a count of the twins' sources, 2026-11-18): 109 to 127 bytes of code a function (the median
67), 3.2 to 3.6 slots, 1.0 to 1.3 parameters, 1.4 locals, 3.7 to 4.2 calls a function (the
run-time's among them), 23 to 44 functions a module, about 7 imports a module and 4 names an
import list, 6 to 17 variables a module. The end-to-end cases (one module each) have 119 bytes
and 2.2 calls a function. Here every function has one or two parameters (a word, and a byte for
some), one or two locals, a few statements of arithmetic on words (`*`, `/` and `mod` call the
run-time library, as in real code), a loop over the module's constant table, a test, an update
of the module's variables, and CALLS calls (on average) of other functions of the program; a
module imports the modules before it that it calls, with a list of the names it uses.

What it does: each module's `run` calls each of its functions once in turn (through functions
`part0`, `part1` ..., each calling PART of them, so that no function is larger than real ones)
and returns the sum of their results; the main prints each module's sum and the sum of all, in hexadecimal. The
calls go only to functions of a lower level (a function's level is its index in its module
modulo LEVELS), declared before the caller in its own module, so no call is recursive, no
function needs a forward declaration and each run makes a bounded number of calls. Every
statement is also evaluated here as the 6502 computes it (words modulo 65536, bytes modulo 256,
unsigned division), which gives genmain.expected.out.

Each module fits the 32K compiler's capacities when FUNCTIONS is at most about 30 (its names, its
symbols and its function buffer: test_gen_program.py checks the modules with the host compiler at
those capacities), and module names fit the DFS's seven characters.
"""
import os
import random
import re
import sys

LEVELS = 4
TABLE = 8                       # bytes in each module's constant table
SMALL = 0.35                    # the share of one-line functions, which call nothing
PART = 8                        # run() calls the functions in parts of this many, as real code is in pieces
# The words of the names: a function is VERB_NOUN, its parameters and locals NOUN, NOUN_count,
# new_NOUN and NOUN_part, so that a module has about as many names, and as long, as real ones.
VERBS = ('count', 'find', 'read', 'mark', 'place', 'check', 'shift', 'merge', 'scale', 'store',
         'load', 'pack', 'split', 'trim', 'turn', 'clear', 'weigh', 'match')
NOUNS = ('row', 'name', 'slot', 'line', 'page', 'entry', 'field', 'block', 'track', 'label',
         'value', 'index', 'limit', 'offset', 'item', 'mark', 'place', 'size', 'width', 'depth',
         'level', 'flag', 'pair', 'node', 'edge', 'chain', 'span', 'column', 'origin', 'weight')
MASK = 0xFFFF


class Function:
    def __init__(self, module, index, rnd):
        self.module = module
        self.index = index
        self.level = index % LEVELS
        self.name = None                            # VERB_NOUN, chosen by its module
        self.words = rnd.sample(NOUNS, 4)           # its parameters' and locals' names
        self.has_count = rnd.random() < 0.4         # a second parameter, a byte
        self.has_extra = rnd.random() < 0.4         # a second local, a word
        self.keeps_more = rnd.random() < 0.3        # updates the module's other variables too
        self.small = rnd.random() < SMALL           # a one-line function, as accessors are
        self.statements = []                        # [(kind, data)], made by Program
        self.calls = []                             # the Functions it calls
        self.exported = False                       # called from another module: `pub`

    def qualified(self, caller_module):
        return self.name if caller_module is self.module else '%s.%s' % (self.module.name, self.name)


class Module:
    def __init__(self, number, functions, rnd):
        self.number = number
        self.name = 'gen%02d' % number
        self.functions = [Function(self, i, rnd) for i in range(functions)]
        names = rnd.sample(['%s_%s' % (v, n) for v in VERBS for n in NOUNS], functions)
        for f, name in zip(self.functions, names):
            f.name = name
        self.table = [rnd.randrange(1, 256) for _ in range(TABLE)]
        self.imports = {}                           # module -> [names]

    def callable_at(self, level, before=None):
        """Its functions of a level below `level` (and declared before function `before`)."""
        return [f for f in self.functions if f.level < level and (before is None or f.index < before)]


class Program:
    """A program of `modules` modules of `functions` functions each, with `calls` calls of other
    functions a function on average, chosen by `seed`; with `body`, each function that is not a
    one-liner has that many statements of arithmetic, loops and tests besides its calls (larger
    functions), else 0 to 2."""

    def __init__(self, modules, functions, calls=2.0, seed=1, body=None):
        self.rnd = rnd = random.Random(seed)
        self.body = body
        self.modules = [Module(n, functions, rnd) for n in range(1, modules + 1)]
        for m in self.modules:
            earlier = [e for e in self.modules if e.number < m.number][-6:]   # at most 6 imports
            for f in m.functions:
                each = calls / (1 - SMALL) / (1 - 1 / LEVELS)   # the calls of the functions that call
                n = int(each) + (1 if rnd.random() < each - int(each) else 0)
                if f.level == 0 or f.small:
                    n = 0
                for _ in range(n):
                    if earlier and rnd.random() < 0.6:
                        target = rnd.choice(earlier)
                        pool = target.callable_at(f.level)
                        listed = m.imports.get(target, [])
                        if len(listed) >= 6:                     # a short import list
                            pool = [g for g in pool if g.name in listed] or pool[:0]
                    else:
                        pool = m.callable_at(f.level, f.index)
                    if not pool:
                        pool = m.callable_at(f.level, f.index)
                    g = rnd.choice(pool)
                    f.calls.append(g)
                    g.exported = g.exported or g.module is not m
                    if g.module is not m and g.name not in m.imports.setdefault(g.module, []):
                        m.imports[g.module].append(g.name)
                f.statements = self.statements_of(f)

    def statements_of(self, f):
        """The body: a mix of the statements real functions have, the calls among them."""
        rnd = self.rnd
        if f.small:
            return [('small', rnd.randrange(1, 1000))]
        body = [('add', rnd.randrange(1, 1000))]
        kinds = ['mul', 'div', 'xor', 'loop', 'test', 'mod', 'shift']
        many = rnd.choice((0, 1, 1, 2)) if self.body is None else self.body
        for kind in [rnd.choice(kinds) for _ in range(many)]:
            body.append((kind, rnd.randrange(3, 200)))
        for g in f.calls:
            body.insert(rnd.randrange(1, len(body) + 1), ('call', g))
        body.append(('keep', None))
        return body

    # ---- The Lathe text -----------------------------------------------------------------------

    def source(self, m):
        out = ['; A generated module (lathe/tests/gen_program.py): arithmetic, a loop, a test and',
               '; calls, of the shape of real Lathe code.', 'module ' + m.name, '']
        for target in sorted(m.imports, key=lambda t: t.number):
            out.append('import %s (%s)' % (target.name, ', '.join(sorted(m.imports[target]))))
        out += ['', 'const TABLE: [%d]byte = [%s]' % (TABLE, ', '.join(str(v) for v in m.table)),
                '', 'var total: word', 'var last: word', 'var seen: byte', '']
        for f in m.functions:
            out += self.function_text(m, f) + ['']
        parts = [m.functions[i:i + PART] for i in range(0, len(m.functions), PART)]
        for k, part in enumerate(parts):
            out += ['; Functions %d to %d once, in turn: the sum of their results.' % (part[0].index, part[-1].index),
                    'func part%d(): word' % k, '  var sum: word', '  sum = 0']
            for f in part:
                args = '%d' % (f.index * 37 + 11) + (', %d' % (f.index % 5 + 2) if f.has_count else '')
                out.append('  sum += %s(%s)' % (f.name, args))
            out += ['  return sum', 'end', '']
        out += ['; Each function once, in turn; the sum of their results and of the variables.',
                'pub func run(): word', '  var sum: word', '  total = 0', '  last = 1', '  seen = 0', '  sum = 0']
        out += ['  sum += part%d()' % k for k in range(len(parts))]
        out += ['  return sum + total + last + word(seen)', 'end']
        return '\n'.join(out) + '\n'

    def function_text(self, m, f):
        params = 'value: word' + (', count: byte' if f.has_count else '')
        out = ['%sfunc %s(%s): word' % ('pub ' if f.exported else '', f.name, params)]
        if f.small:
            return out + ['  return (value ^ %d) + TABLE[lo(value) & %d]' % (f.statements[0][1], TABLE - 1), 'end']
        out.append('  var result: word')
        if f.has_extra:
            out.append('  var other: word')
        if any(k == 'loop' for k, _ in f.statements):
            out.append('  var i: byte')
        count = 'word(count)' if f.has_count else '3'
        for kind, data in f.statements:
            if kind == 'add':
                out.append('  result = value + %d' % data)
                if f.has_extra:
                    out.append('  other = result ^ %d' % (data * 7 & MASK))
            elif kind == 'mul':
                out.append('  result += value * %d' % data)
            elif kind == 'div':
                out.append('  result += result / %d' % data)
            elif kind == 'mod':
                out.append('  result -= result mod %d' % data)
            elif kind == 'xor':
                out.append('  result = (result ^ %d) + %s' % (data, count))
            elif kind == 'shift':
                out.append('  result = result + (value >> 2) + (result << 1)')
            elif kind == 'loop':
                out += ['  for i = 0 until %d do' % (data % TABLE + 1),
                        '    result += TABLE[i]', '  end']
            elif kind == 'test':
                out += ['  if result > %d then' % (data * 100), '    result -= %d' % data, '  else',
                        '    result += %s' % ('other' if f.has_extra else count), '  end']
            elif kind == 'call':
                g = data
                args = 'result' + (', lo(result)' if g.has_count else '')
                out.append('  result += %s(%s)' % (g.qualified(m), args))
            elif kind == 'keep':
                out.append('  total += result')
                if f.keeps_more:
                    out += ['  last = last ^ value', '  seen += 1']
                out.append('  return result')
        out.append('end')
        # Its own names for its parameters and locals.
        a, b, c, d = f.words
        for word, name in (('value', a), ('count', b + '_count'), ('result', 'new_' + c), ('other', d + '_part')):
            out = [re.sub(r'\b%s\b' % word, name, line) for line in out]
        return out

    def main_text(self):
        out = ['; The main of a generated program (lathe/tests/gen_program.py): each module\'s sum and',
               '; the sum of all, in hexadecimal.', 'module genmain', '', 'import host']
        out += ['import %s (run)' % m.name for m in self.modules]
        out += ['', 'const DIGITS: [16]byte = "0123456789ABCDEF"', '',
                'func hex(n: word)', '  host.put_byte(DIGITS[byte(n >> 12)])',
                '  host.put_byte(DIGITS[byte(n >> 8) & 15])', '  host.put_byte(DIGITS[byte(n >> 4) & 15])',
                '  host.put_byte(DIGITS[byte(n) & 15])', '  host.put_byte(10)', 'end', '',
                'pub func main()', '  var sum: word', '  var all: word', '  all = 0']
        for m in self.modules:
            out += ['  sum = %s.run()' % m.name, '  hex(sum)', '  all = all + sum']
        out += ['  hex(all)', 'end']
        return '\n'.join(out) + '\n'

    # ---- What the 6502 computes ---------------------------------------------------------------

    def evaluate(self):
        """The program's output, as the 6502 computes it."""
        state = {}

        def call(f, value, count):
            m = f.module
            st = state[m]
            result = other = 0
            c = count if f.has_count else 3
            for kind, data in f.statements:
                if kind == 'small':
                    return ((value ^ data) + m.table[value & (TABLE - 1)]) & MASK
                if kind == 'add':
                    result = (value + data) & MASK
                    if f.has_extra:
                        other = result ^ (data * 7 & MASK)
                elif kind == 'mul':
                    result = (result + value * data) & MASK
                elif kind == 'div':
                    result = (result + result // data) & MASK
                elif kind == 'mod':
                    result = (result - result % data) & MASK
                elif kind == 'xor':
                    result = ((result ^ data) + c) & MASK
                elif kind == 'shift':
                    result = (result + (value >> 2) + ((result << 1) & MASK)) & MASK
                elif kind == 'loop':
                    for i in range(data % TABLE + 1):
                        result = (result + m.table[i]) & MASK
                elif kind == 'test':
                    if result > data * 100:
                        result = (result - data) & MASK
                    else:
                        result = (result + (other if f.has_extra else c)) & MASK
                elif kind == 'call':
                    result = (result + call(data, result, result & 0xFF)) & MASK
                elif kind == 'keep':
                    st['total'] = (st['total'] + result) & MASK
                    if f.keeps_more:
                        st['last'] ^= value
                        st['seen'] = (st['seen'] + 1) & 0xFF
                    return result

        lines, everything = [], 0
        for m in self.modules:
            state[m] = {'total': 0, 'last': 1, 'seen': 0}
        for m in self.modules:
            st = state[m]
            st.update(total=0, last=1, seen=0)
            s = 0
            for f in m.functions:
                s = (s + call(f, f.index * 37 + 11, f.index % 5 + 2)) & MASK
            s = (s + st['total'] + st['last'] + st['seen']) & MASK
            lines.append('%04X' % s)
            everything = (everything + s) & MASK
        lines.append('%04X' % everything)
        return ('\n'.join(lines) + '\n').encode()

    def write(self, out_dir):
        """Writes the modules, the main and genmain.expected.out to out_dir: the main's path."""
        os.makedirs(out_dir, exist_ok=True)
        for m in self.modules:
            with open(os.path.join(out_dir, m.name + '.lth'), 'w') as f:
                f.write(self.source(m))
        main = os.path.join(out_dir, 'genmain.lth')
        with open(main, 'w') as f:
            f.write(self.main_text())
        with open(os.path.join(out_dir, 'genmain.expected.out'), 'wb') as f:
            f.write(self.evaluate())
        return main

    def lines(self):
        return sum(self.source(m).count('\n') for m in self.modules) + self.main_text().count('\n')

    def functions(self):
        """Every function: each module's, its parts and run, and the main's two."""
        return sum(len(m.functions) + 1 + (len(m.functions) + PART - 1) // PART for m in self.modules) + 2


def main(argv):
    if len(argv) < 3:
        raise SystemExit(__doc__)
    out, modules, functions = argv[0], int(argv[1]), int(argv[2])
    calls = float(argv[3]) if len(argv) > 3 else 2.0
    seed = int(argv[4]) if len(argv) > 4 else 1
    body = int(argv[5]) if len(argv) > 5 else None
    p = Program(modules, functions, calls, seed, body)
    p.write(out)
    print('%d modules and the main, %d lines, %d functions' % (modules, p.lines(), p.functions()))


if __name__ == '__main__':
    main(sys.argv[1:])
