#!/usr/bin/env python3
"""Random programs for the compiler, checked against their true results. Not part of
lathe/verify.sh: run it after changing how code is generated.

    python3 lathe/tests/fuzz.py expr SEED COUNT [SIZE]
    python3 lathe/tests/fuzz.py stmt SEED COUNT [SIZE]

Compiles and runs COUNT programs, made from the seeds SEED, SEED + 1, ... (so a failure can
be made again), each of SIZE statements.

- `expr`: each statement is a random expression of one of the scalar types - arithmetic,
  shifts, conversions, comparisons, `and` `or` `not`, calls in arguments - assigned, returned,
  returned with a status or used as a test. It prints each value.
- `stmt`: a sequence of assignments, compound assignments, halves of words, `if`, `while`,
  `loop ... until` and calls on seven variables, the elements of three arrays (bytes, words
  by column, words by row) and the fields of two arrays of records (by column and by row),
  read and written directly and through pointers, which prints their final values. This is aimed at what the compiler remembers about the registers and the flags.

The true results come from the same program worked out in Python while it is generated. A
program that prints something else, or does not compile, is kept in a directory that is
named; `expression too complex` (error 79) is a capacity of the compiler and not a fault.
"""
import os
import random
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'host', 'driver'))
import build  # noqa: E402

# ---------------------------------------------------------------------------------------------
# Expressions

B, S, W, I, BOOL = 'byte', 'sbyte', 'word', 'int', 'bool'
BITS = {B: 8, S: 8, W: 16, I: 16}
SIGNED = {S, I}
VARS = {B: {'a': 0x35, 'b': 0xC8, 'c': 0x01, 'z': 0x00, 'm': 0xFF},
        S: {'s': -100, 't': 77, 'u': -1},
        W: {'w': 0x1234, 'v': 0xFEDC, 'x': 0x00FF, 'y': 0x8000},
        I: {'i': -1000, 'j': 12345, 'k': -32768},
        BOOL: {'yes': 1, 'no': 0}}


def wrap(t, v):
    bits = BITS[t]
    v &= (1 << bits) - 1
    if t in SIGNED and v >> (bits - 1):
        v -= 1 << bits
    return v


class Expressions:
    def __init__(self, rng):
        self.r = rng
        self.pending = set()

    def const(self, t):
        r = self.r
        if t == B:
            return r.choice([0, 1, 2, 7, 15, 16, 127, 128, 200, 254, 255])
        if t == S:
            return r.choice([0, 1, -1, 2, -2, 100, -100, 127, -128])
        if t == W:
            return r.choice([0, 1, 255, 256, 257, 0x0F0F, 0x7FFF, 0x8000, 0xFF00, 0xFFFF, 1000])
        return r.choice([0, 1, -1, 255, -256, 1000, -1000, 32767, -32768])

    def leaf(self, t):
        r = self.r
        if r.random() < 0.3:
            c = self.const(t)
            # a typed constant, so that it cannot change the type of an operation
            return ('%s(%d)' % (t, c) if r.random() < 0.3 else str(c), c, True)
        name = r.choice(sorted(VARS[t]))
        return (name, VARS[t][name], False)

    def expr(self, t, depth):
        """(text, value, is_untyped_constant)"""
        r = self.r
        if depth <= 0 or r.random() < 0.15:
            return self.leaf(t)
        kind = r.choice(['bin', 'bin', 'bin', 'bin', 'shift', 'unary', 'conv', 'call', 'vshift', 'cond', 'paren'])
        if kind == 'bin':
            op = r.choice(['+', '-', '&', '|', '^'])
            lt, lv, lc, ln = self.operand(t, depth - 1)
            rt, rv, rc, rn = self.operand(t, depth - 1)
            if lc and (rc or rn):   # two untyped constants would be folded exactly, and one
                lt = '%s(%s)' % (t, lt)     # beside a byte would have to be a byte: type it
            if rc and ln:
                rt = '%s(%s)' % (t, rt)
            if ln and rn:           # two bytes would be a byte operation
                lt = '%s(%s)' % (t, lt)
            # a bare constant must fit the type of the other side
            v = {'+': lv + rv, '-': lv - rv, '&': lv & rv, '|': lv | rv, '^': lv ^ rv}[op]
            return ('(%s %s %s)' % (lt, op, rt), wrap(t, v), False)
        if kind == 'shift':
            x, xv, xc = self.expr(t, depth - 1)
            n = r.randrange(0, BITS[t] + 2)
            if xc:
                x = '%s(%s)' % (t, x)
            if r.random() < 0.5:
                return ('(%s << %d)' % (x, n), wrap(t, xv << n), False)
            return ('(%s >> %d)' % (x, n), wrap(t, xv >> n) if t in SIGNED else (xv & ((1 << BITS[t]) - 1)) >> n, False)
        if kind == 'vshift' and BITS[t] == 8:
            x, xv, xc = self.expr(t, depth - 1)
            if xc:
                x = '%s(%s)' % (t, x)
            n, nv, _ = self.expr(B, depth - 2)
            n = '(%s & 7)' % n
            nv &= 7
            if r.random() < 0.5:
                return ('(%s << %s)' % (x, n), wrap(t, xv << nv), False)
            return ('(%s >> %s)' % (x, n), wrap(t, xv >> nv) if t in SIGNED else (xv & 0xFF) >> nv, False)
        if kind == 'unary':
            x, xv, xc = self.expr(t, depth - 1)
            if xc:
                x = '%s(%s)' % (t, x)
            if r.random() < 0.5:
                return ('(-%s)' % x, wrap(t, -xv), False)
            return ('(~%s)' % x, wrap(t, ~xv), False)
        if kind == 'conv':
            src = r.choice([B, S, W, I, BOOL] if BITS[t] == 8 else [B, S, W, I])
            if src == BOOL:
                x, xv = self.cond(depth - 1)
                return ('%s(%s)' % (t, x), xv, False)
            x, xv, _ = self.expr(src, depth - 1)
            if BITS[t] == 8 and BITS[src] == 16 and r.random() < 0.4 and t == B:
                which = r.choice(['lo', 'hi'])
                return ('%s(%s)' % (which, x), (xv & 0xFFFF) >> (8 if which == 'hi' else 0) & 0xFF, False)
            return ('%s(%s)' % (t, x), wrap(t, xv), False)
        if kind == 'call':
            f = r.choice(['id', 'add', 'pick'])
            name = '%s_%s' % (f, t)
            if name in self.pending:
                return self.leaf(t)
            if f == 'id':
                x, xv, xc = self.expr(t, depth - 1)
                return ('%s(%s)' % (name, x), wrap(t, xv), False)
            if f == 'add':
                x, xv, _ = self.expr(t, depth - 1)
                self.pending.add(name)
                y, yv, _ = self.expr(t, depth - 1)
                self.pending.discard(name)
                return ('%s(%s, %s)' % (name, x, y), wrap(t, xv + yv), False)
            c, cv = self.cond(depth - 1)
            self.pending.add(name)
            x, xv, _ = self.expr(t, depth - 1)
            y, yv, _ = self.expr(t, depth - 1)
            self.pending.discard(name)
            return ('%s(%s, %s, %s)' % (name, c, x, y), wrap(t, xv if cv else yv), False)
        if kind == 'cond' and BITS[t] == 8:
            x, xv = self.cond(depth - 1)
            return ('%s(%s)' % (t, x), xv, False)
        x, xv, xc = self.expr(t, depth - 1)
        return ('(%s)' % x, xv, xc)

    def operand(self, t, depth):
        """An operand of an operation in type t: of that type, or a byte where a word is wanted."""
        if t == W and self.r.random() < 0.25:
            x, xv, xc = self.expr(B, depth)
            if xc:
                return ('byte(%s)' % x, xv, False, True)
            return (x, xv, False, True)
        x, xv, xc = self.expr(t, depth)
        return (x, xv, xc, False)

    def cond(self, depth):
        """(text, value 0/1)"""
        r = self.r
        if depth <= 0:
            if r.random() < 0.3:
                name = r.choice(sorted(VARS[BOOL]))
                return (name, VARS[BOOL][name])
            depth = 1
        kind = r.choice(['cmp', 'cmp', 'cmp', 'and', 'or', 'not', 'eqb', 'call'])
        if kind == 'cmp':
            t = r.choice([B, S, W, I])
            x, xv, xc, xn = self.operand(t, depth - 1)
            y, yv, yc, yn = self.operand(t, depth - 1)
            if xc and (yc or yn):
                x = '%s(%s)' % (t, x)
            if yc and xn:
                y = '%s(%s)' % (t, y)
            if xn and yn:
                x = '%s(%s)' % (t, x)
            op = r.choice(['==', '!=', '<', '>=', '>', '<='])
            v = {'==': xv == yv, '!=': xv != yv, '<': xv < yv, '>=': xv >= yv, '>': xv > yv, '<=': xv <= yv}[op]
            return ('(%s %s %s)' % (x, op, y), int(v))
        if kind in ('and', 'or'):
            x, xv = self.cond(depth - 1)
            y, yv = self.cond(depth - 1)
            if kind == 'and':
                return ('(%s and %s)' % (x, y), xv & yv)
            return ('(%s or %s)' % (x, y), xv | yv)
        if kind == 'not':
            x, xv = self.cond(depth - 1)
            return ('(not %s)' % x, 1 - xv)
        if kind == 'eqb':
            x, xv = self.cond(depth - 1)
            y, yv = self.cond(depth - 1)
            if r.random() < 0.5:
                return ('(%s == %s)' % (x, y), int(xv == yv))
            return ('(%s != %s)' % (x, y), int(xv != yv))
        if 'id_bool' in self.pending:
            return self.cond(0)
        x, xv = self.cond(depth - 1)
        return ('id_bool(%s)' % x, xv)


EXPRESSION_HEAD = '''module fuzz
import host
'''
EXPRESSION_FUNCS = '''
func digit(n: byte)
  if n < 10 then
    host.put_byte('0' + n)
  else
    host.put_byte('A' - 10 + n)
  end
end
func hex(n: byte)
  digit(n >> 4)
  digit(n & 15)
end
func out(n: word)
  hex(hi(n))
  hex(lo(n))
  host.put_byte(10)
end
func id_bool(p: bool): bool
  return p
end
'''


def expression_program(seed, count):
    """A program of `count` statements with random expressions, and what it must print."""
    rng = random.Random(seed)
    g = Expressions(rng)
    src = [EXPRESSION_HEAD]
    for t in (B, S, W, I, BOOL):
        for name, value in sorted(VARS[t].items()):
            src.append('var %s: %s = %s\n' % (name, t, ('true' if value else 'false') if t == BOOL else value))
    src.append('var rb: byte\nvar rs: sbyte\nvar rw: word\nvar ri: int\nvar rf: bool\n')
    src.append(EXPRESSION_FUNCS)
    for t in (B, S, W, I):
        src.append('func id_%s(p: %s): %s\n  return p\nend\n' % (t, t, t))
        src.append('func add_%s(p: %s, q: %s): %s\n  return p + q\nend\n' % (t, t, t, t))
        src.append('func pick_%s(c: bool, p: %s, q: %s): %s\n  if c then\n    return p\n  end\n  return q\nend\n' % (t, t, t, t))
    body, funcs, expected = [], [], []
    res = {B: 'rb', S: 'rs', W: 'rw', I: 'ri'}
    for n in range(count):
        t = rng.choice([B, S, W, I])
        form = rng.choice(['assign', 'assign', 'return', 'compound', 'if', 'bool', 'status'])
        if form == 'assign':
            x, xv, _ = g.expr(t, rng.randrange(1, 5))
            body.append('  %s = %s\n  out(word(%s))\n' % (res[t], x, res[t]))
            expected.append(wrap(t, xv) & 0xFFFF)
        elif form == 'return':
            x, xv, _ = g.expr(t, rng.randrange(1, 5))
            funcs.append('func f%d(): %s\n  return %s\nend\n' % (n, t, x))
            body.append('  out(word(f%d()))\n' % n)
            expected.append(wrap(t, xv) & 0xFFFF)
        elif form == 'compound':
            x, xv, _ = g.expr(t, rng.randrange(1, 4))
            y, yv, yc, _ = g.operand(t, rng.randrange(0, 3))
            op = rng.choice(['+', '-', '&', '|', '^'])
            v = {'+': xv + yv, '-': xv - yv, '&': xv & yv, '|': xv | yv, '^': xv ^ yv}[op]
            body.append('  %s = %s\n  %s %s= %s\n  out(word(%s))\n' % (res[t], x, res[t], op, y, res[t]))
            expected.append(wrap(t, v) & 0xFFFF)
        elif form == 'if':
            c, cv = g.cond(rng.randrange(1, 4))
            x, xv, _ = g.expr(t, rng.randrange(0, 3))
            y, yv, _ = g.expr(t, rng.randrange(0, 3))
            body.append('  if %s then\n    %s = %s\n  else\n    %s = %s\n  end\n  out(word(%s))\n'
                        % (c, res[t], x, res[t], y, res[t]))
            expected.append(wrap(t, xv if cv else yv) & 0xFFFF)
        elif form == 'bool':
            c, cv = g.cond(rng.randrange(1, 5))
            body.append('  rf = %s\n  out(word(byte(rf)))\n' % c)
            expected.append(cv)
        else:
            c, cv = g.cond(rng.randrange(1, 4))
            x, xv, _ = g.expr(t, rng.randrange(0, 3))
            funcs.append('func f%d(): %s, bool\n  return %s, %s\nend\n' % (n, t, x, c))
            body.append('  %s, rf = f%d()\n  out(word(%s) + word(byte(rf)))\n' % (res[t], n, res[t]))
            expected.append((wrap(t, xv) + cv) & 0xFFFF)
    src += funcs
    src.append('pub func main()\n' + ''.join(body) + 'end\n')
    return ''.join(src), ''.join('%04X\n' % (e & 0xFFFF) for e in expected)


# ---------------------------------------------------------------------------------------------
# Statements

BV = ['b0', 'b1', 'b2', 'b3']
WV = ['w0', 'w1', 'w2']
CV = ['c0', 'c1']               # loop counters, changed only by the loops


class Statements:
    def __init__(self, rng):
        self.r = rng

    def index(self):
        """An index of one of the arrays, which have 8 elements: (lathe, python)."""
        r = self.r
        k = r.random()
        if k < 0.3:
            n = str(r.randrange(0, 8))
            return n, n
        if k < 0.5:
            c = r.choice(CV)
            return c, c
        if k < 0.65:
            c = r.choice(CV)
            n = r.randrange(1, 4)
            return '%s + %d' % (c, n), '%s + %d' % (c, n)
        v = '(%s & 7)' % r.choice(BV)
        return v, v

    def element(self, word):
        """An element, or a field of one: (lathe, python)."""
        i, pi = self.index()
        if word:
            name = self.r.choice(['aw', 'ar', 'pw', 'ra%s.w', 'rr%s.w', 'pr%s.w'])
        else:
            name = self.r.choice(['ab', 'pb', 'ra%s.b', 'rr%s.c', 'pr%s.b'])
        lathe = name + '[%s]' if '%' not in name else name.replace('%s', '[%s]')
        python = {'pw': 'ar', 'pb': 'ab', 'pr%s.w': 'rr%s.w', 'pr%s.b': 'rr%s.b'}.get(name, name)
        python = python.replace('%s.', '_').replace('%s', '') + '[%s]'
        return lathe % i, python % pi

    def bleaf(self):
        r = self.r
        k = r.random()
        if k < 0.45:
            v = r.choice(BV)
            return v, v
        if k < 0.55:
            if r.random() < 0.6:
                return self.element(False)
            x, px = self.element(True)
            if r.random() < 0.5:
                return 'lo(%s)' % x, '(%s & 255)' % px
            return 'hi(%s)' % x, '(%s >> 8)' % px
        if k < 0.7:
            w = r.choice(WV)
            if r.random() < 0.5:
                return 'lo(%s)' % w, '(%s & 255)' % w
            return 'hi(%s)' % w, '(%s >> 8)' % w
        c = r.choice([0, 1, 2, 3, 0x0F, 0x7F, 0x80, 0xFE, 0xFF])
        return str(c), str(c)

    def bexpr(self, depth=1):
        r = self.r
        if depth == 0 or r.random() < 0.35:
            return self.bleaf()
        x, px = self.bexpr(depth - 1)
        kind = r.random()
        if kind < 0.12:
            n = r.randrange(0, 4)
            op = r.choice(['<<', '>>'])
            if not any(v in x for v in BV + WV):
                x, px = r.choice(BV), None
                px = x
            return '(%s %s %d)' % (x, op, n), '((%s %s %d) & 255)' % (px, op, n)
        if kind < 0.2:
            if not any(v in x for v in BV + WV):
                x = px = r.choice(BV)
            return 'idb(%s)' % x, '(%s)' % px
        y, py = self.bexpr(depth - 1)
        if not any(v in x for v in BV + WV) and not any(v in y for v in BV + WV):
            x = px = r.choice(BV)
        op = r.choice(['+', '-', '&', '|', '^'])
        return '(%s %s %s)' % (x, op, y), '((%s %s %s) & 255)' % (px, op, py)

    def wleaf(self):
        r = self.r
        k = r.random()
        if k < 0.5:
            v = r.choice(WV)
            return v, v, True
        if k < 0.6:
            x, px = self.element(True)
            return x, px, True
        if k < 0.8:
            v = r.choice(BV)
            return v, v, False          # a byte, widened
        c = r.choice([0, 1, 2, 0xFF, 0x100, 0x101, 0x7FFF, 0x8000, 0xFF00, 0xFFFF])
        return str(c), str(c), None     # a number

    def wexpr(self, depth=1):
        """(lathe, python, is a word for certain)"""
        r = self.r
        if depth == 0 or r.random() < 0.35:
            x, px, kind = self.wleaf()
            if kind is None:
                return x, px, True
            if kind is False:
                return 'word(%s)' % x, px, True
            return x, px, True
        x, px, _ = self.wexpr(depth - 1)
        if r.random() < 0.12:
            n = r.randrange(0, 5)
            op = r.choice(['<<', '>>'])
            if not any(v in x for v in BV + WV):
                x = px = r.choice(WV)
            return '(%s %s %d)' % (x, op, n), '((%s %s %d) & 65535)' % (px, op, n), True
        y, py, kind = self.wleaf()
        if not any(v in x for v in BV + WV) and kind is not True:
            x = px = r.choice(WV)
        op = r.choice(['+', '-', '&', '|', '^'])
        return '(%s %s %s)' % (x, op, y), '((%s %s %s) & 65535)' % (px, op, py), True

    def cond(self):
        r = self.r
        op = r.choice(['==', '!=', '<', '>=', '>', '<='])
        if r.random() < 0.6:
            x = r.choice(BV)
            y, py = self.bleaf()
            if r.random() < 0.3:
                y = py = '0'
            return '%s %s %s' % (x, op, y), '%s %s %s' % (x, op, py)
        x = r.choice(WV)
        y, py, kind = self.wleaf()
        return '%s %s %s' % (x, op, y), '%s %s %s' % (x, op, py)

    def stmt(self, depth, ind, lathe, py, loops):
        r = self.r
        pad = '  ' * ind
        ppad = '    ' * (ind - 1)
        kind = r.random()
        if kind < 0.22:
            d = pd = r.choice(BV)
            if r.random() < 0.3:
                d, pd = self.element(False)
            x, px = self.bexpr(r.randrange(0, 3))
            lathe.append('%s%s = %s\n' % (pad, d, x))
            py.append('%s%s = %s\n' % (ppad, pd, px))
        elif kind < 0.30:
            d, pd = self.element(r.random() < 0.5)
            op = r.choice(['+', '-', '&', '|', '^', '+', '-'])
            mask = 65535 if pd.startswith(('aw', 'ar', 'ra_w', 'rr_w')) else 255
            if mask == 255:
                x, px = self.bleaf()
            else:
                x, px, _ = self.wleaf()
            if r.random() < 0.4:
                x = px = '1'
            lathe.append('%s%s %s= %s\n' % (pad, d, op, x))
            py.append('%s%s = (%s %s %s) & %d\n' % (ppad, pd, pd, op, px, mask))
        elif kind < 0.33:
            d = r.choice(BV)
            x, px = self.bexpr(r.randrange(0, 3))
            lathe.append('%s%s = %s\n' % (pad, d, x))
            py.append('%s%s = %s\n' % (ppad, d, px))
        elif kind < 0.40:
            d = pd = r.choice(WV)
            if r.random() < 0.3:
                d, pd = self.element(True)
            x, px, _ = self.wexpr(r.randrange(0, 3))
            lathe.append('%s%s = %s\n' % (pad, d, x))
            py.append('%s%s = %s\n' % (ppad, pd, px))
        elif kind < 0.55:
            d = r.choice(BV)
            op = r.choice(['+', '-', '&', '|', '^', '+', '-'])
            x, px = self.bleaf()
            if r.random() < 0.4:
                x = px = '1'
            lathe.append('%s%s %s= %s\n' % (pad, d, op, x))
            py.append('%s%s = (%s %s %s) & 255\n' % (ppad, d, d, op, px))
        elif kind < 0.68:
            d = r.choice(WV)
            op = r.choice(['+', '-', '&', '|', '^', '+', '-'])
            x, px, k = self.wleaf()
            if r.random() < 0.4:
                x = px = '1'
            lathe.append('%s%s %s= %s\n' % (pad, d, op, x))
            py.append('%s%s = (%s %s %s) & 65535\n' % (ppad, d, d, op, px))
        elif kind < 0.74:
            d = r.choice(WV)
            x, px = self.bexpr(1)
            if r.random() < 0.5:
                lathe.append('%slo(%s) = %s\n' % (pad, d, x))
                py.append('%s%s = (%s & 0xFF00) | %s\n' % (ppad, d, d, px))
            else:
                lathe.append('%shi(%s) = %s\n' % (pad, d, x))
                py.append('%s%s = (%s & 0x00FF) | (%s << 8)\n' % (ppad, d, d, px))
        elif kind < 0.79:
            d = r.choice(BV + WV)
            n = r.randrange(0, 4)
            op = r.choice(['<<', '>>'])
            mask = 255 if d in BV else 65535
            lathe.append('%s%s %s= %d\n' % (pad, d, op, n))
            py.append('%s%s = (%s %s %d) & %d\n' % (ppad, d, d, op, n, mask))
        elif kind < 0.84:
            lathe.append('%stouch()\n' % pad)
            py.append('%sb3 = (b3 + 1) & 255; w2 = (w2 ^ b0) & 65535\n' % ppad)
        elif kind < 0.94 and depth > 0:
            c, pc = self.cond()
            lathe.append('%sif %s then\n' % (pad, c))
            py.append('%sif %s:\n' % (ppad, pc))
            for _ in range(r.randrange(1, 4)):
                self.stmt(depth - 1, ind + 1, lathe, py, loops)
            if r.random() < 0.5:
                lathe.append('%selse\n' % pad)
                py.append('%selse:\n' % ppad)
                for _ in range(r.randrange(1, 3)):
                    self.stmt(depth - 1, ind + 1, lathe, py, loops)
            lathe.append('%send\n' % pad)
        elif depth > 0 and loops < 2:
            c = CV[loops]
            n = r.randrange(0, 4)
            if r.random() < 0.5:
                lathe.append('%s%s = %d\n%swhile %s != 0 do\n' % (pad, c, n, pad, c))
                py.append('%s%s = %d\n%swhile %s != 0:\n' % (ppad, c, n, ppad, c))
                for _ in range(r.randrange(1, 4)):
                    self.stmt(depth - 1, ind + 1, lathe, py, loops + 1)
                lathe.append('%s  %s -= 1\n%send\n' % (pad, c, pad))
                py.append('%s    %s -= 1\n' % (ppad, c))
            else:
                lathe.append('%s%s = %d\n%sloop\n' % (pad, c, n + 1, pad))
                py.append('%s%s = %d\n%swhile True:\n' % (ppad, c, n + 1, ppad))
                for _ in range(r.randrange(1, 4)):
                    self.stmt(depth - 1, ind + 1, lathe, py, loops + 1)
                lathe.append('%s  %s -= 1\n%suntil %s == 0\n' % (pad, c, pad, c))
                py.append('%s    %s -= 1\n%s    if %s == 0:\n%s        break\n' % (ppad, c, ppad, c, ppad))
        else:
            self.stmt(0, ind, lathe, py, loops)


STATEMENT_HEAD = '''module fuzz
import host
var b0: byte = 3
var b1: byte = 200
var b2: byte = 0
var b3: byte = 255
var w0: word = 300
var w1: word = 65535
var w2: word = 0
var c0: byte
var c1: byte
var ab: [8]byte = [1, 2, 3, 4, 250, 251, 252, 253]
var aw: [8]word = [0, 1, 255, 256, 32767, 32768, 65534, 65535]
var ar: [8]word rows = [7, 300, 0, 65535, 1, 2, 3, 4]
var pb: ^byte = @ab
var pw: ^word = @ar
type R = record
  b: byte
  c: byte
  w: word
end
var ra: [8]R
var rr: [8]R rows
var pr: ^R
func digit(n: byte)
  if n < 10 then
    host.put_byte('0' + n)
  else
    host.put_byte('A' - 10 + n)
  end
end
func hex(n: byte)
  digit(n >> 4)
  digit(n & 15)
end
func out(n: word)
  hex(hi(n))
  hex(lo(n))
  host.put_byte(10)
end
func idb(p: byte): byte
  return p
end
func touch()
  b3 += 1
  w2 ^= b0
end
pub func main()
'''


def statement_program(seed, count):
    """A program of `count` random statements, and the values its variables must end with."""
    rng = random.Random(seed)
    g = Statements(rng)
    lathe, py = [], []
    for _ in range(count):
        g.stmt(2, 1, lathe, py, 0)
    fields = ('ra[%d].b', 'ra[%d].w', 'rr[%d].b', 'rr[%d].c', 'rr[%d].w')
    shown = BV + WV + ['%s[%d]' % (a, i) for a in ('ab', 'aw', 'ar') for i in range(8)] \
        + [f % i for f in fields for i in range(8)]
    tail = ''.join('  out(%s)\n' % v for v in shown) + 'end\n'
    env = dict(b0=3, b1=200, b2=0, b3=255, w0=300, w1=65535, w2=0, c0=0, c1=0,
               ab=[1, 2, 3, 4, 250, 251, 252, 253], aw=[0, 1, 255, 256, 32767, 32768, 65534, 65535],
               ar=[7, 300, 0, 65535, 1, 2, 3, 4])
    head = '  pr = @rr[0]\n'
    for n, f in enumerate(fields):          # records have no initial values: set them here
        python = f.replace('[%d].', '_')
        env[python] = [(37 * n + 91 * i) % 256 if f.endswith(('b', 'c')) else (4999 * (n + i) + 255 * i) % 65536
                       for i in range(8)]
        head += ''.join('  %s = %d\n' % (f % i, env[python][i]) for i in range(8))
    exec(''.join(py), {}, env)
    want = ''.join('%04X\n' % eval(_python(v), {}, env) for v in shown)
    return STATEMENT_HEAD + head + ''.join(lathe) + tail, want


def _python(v):
    """The Python name of what `v` shows: ra[3].w is ra_w[3]."""
    if '.' not in v:
        return v
    name, rest = v.split('[')
    index, field = rest.split('].')
    return '%s_%s[%s]' % (name, field, index)


def run(text, want, seed):
    """Build and run a program. Returns '' if it prints `want`, else what went wrong."""
    d = tempfile.mkdtemp(prefix='lathe-fuzz-%d-' % seed)
    path = os.path.join(d, 'fuzz.lth')
    with open(path, 'w') as f:
        f.write(text)
    try:
        build.build(path, os.path.join(d, 'fuzz.bin'), keep=os.path.join(d, 'build'))
        status, out, _ = build.run_image(os.path.join(d, 'fuzz.bin'))
        got = out.decode('latin-1')
    except build.BuildError as e:
        return 'does not build (%s): %s' % (e, path)
    if status == 0 and got == want:
        shutil.rmtree(d, ignore_errors=True)
        return ''
    got, want = got.split('\n'), want.split('\n')
    first = next((n for n in range(min(len(got), len(want))) if got[n] != want[n]), min(len(got), len(want)))
    return 'status %d, line %d of the output is %s and must be %s: %s' % (
        status, first + 1, got[first:first + 1], want[first:first + 1], path)


def main(argv):
    if len(argv) < 3 or argv[0] not in ('expr', 'stmt'):
        sys.stderr.write('usage: fuzz.py expr|stmt SEED COUNT [SIZE]\n')
        return 2
    make = expression_program if argv[0] == 'expr' else statement_program
    first, count = int(argv[1]), int(argv[2])
    size = int(argv[3]) if len(argv) > 3 else 30
    bad = 0
    for seed in range(first, first + count):
        text, want = make(seed, size)
        problem = run(text, want, seed)
        if problem:
            bad += 1
            print('seed %d: %s' % (seed, problem))
    print('%d programs, %d wrong' % (count, bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
