"""The run-time arithmetic library, lathe/rt/rt_math.lth: a Python model of every function, by
plain Python arithmetic and not by the 6502 algorithms, and the expected output of the
end-to-end cases cases/e2e/math_*.lth computed from it.

The cases themselves run in test_cases.py like every end-to-end case. This file checks that
each committed NAME.expected.out is what the model gives, so the expected files are an
independent computation and not merely what the library printed. To write them again:

    python3 lathe/tests/test_rt_math.py --write
"""
import os
import sys
import unittest

E2E = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cases', 'e2e')


# ---- The model (lathe/rt/rt_math.lth, "Rules") ----------------------------------------------

def sx(v, bits):
    """v, `bits` wide, as a signed number."""
    return v - (1 << bits) if v & (1 << (bits - 1)) else v


def udiv(a, b, bits):
    """Quotient and remainder; by zero: all ones and the dividend."""
    if b == 0:
        return (1 << bits) - 1, a
    return a // b, a % b


def sdiv(a, b, bits):
    """Signed quotient and remainder of the bit patterns a and b, as bit patterns: truncating
    toward zero, the remainder with the sign of the dividend; by zero the magnitudes divide by
    the unsigned rule. Also the unsigned remainder of the magnitudes, which sdiv leaves."""
    mask = (1 << bits) - 1
    sa, sb = sx(a, bits), sx(b, bits)
    q, r = udiv(abs(sa) & mask, abs(sb) & mask, bits)
    mag_r = r
    if (sa < 0) != (sb < 0):
        q = -q
    if sa < 0:
        r = -r
    return q & mask, r & mask, mag_r


def mul8(a, b):
    return a * b & 0xFF


def mul8x8(a, b):
    return a * b


def mul16(a, b):
    return a * b & 0xFFFF


def shl16(w, n):
    return (w << n) & 0xFFFF if n < 16 else 0


def shr16(w, n):
    return w >> n if n < 16 else 0


def sar16(w, n):
    return (sx(w, 16) >> min(n, 16)) & 0xFFFF


# ---- What the cases print ------------------------------------------------------------------

class Out:
    def __init__(self):
        self.text = []
        self.sum = 0

    def add(self, v):
        self.sum = ((self.sum << 1) | (self.sum >> 15)) & 0xFFFF
        self.sum = (self.sum + v) & 0xFFFF

    def show(self):
        self.hexw(self.sum)
        self.text.append(' ')
        self.sum = 0

    def hex(self, b):
        self.text.append('%02X' % b)

    def hexw(self, w):
        self.text.append('%04X' % w)

    def put(self, s):
        self.text.append(s)

    def value(self):
        return ''.join(self.text).encode('ascii')


BYTES = range(256)


def case_mul8():
    o = Out()
    v = [0, 1, 2, 0x7F, 0x80, 0xAB, 0xFF]
    for f in (mul8, mul8x8):
        for i in BYTES:
            for j in BYTES:
                o.add(f(i, j))
        o.show()
    o.put('\n')
    for i in v:
        for j in v:
            o.hex(mul8(i, j))
            o.put(' ')
    o.put('\n')
    for i in v:
        for j in v:
            o.hexw(mul8x8(i, j))
            o.put(' ')
    o.put('\n')
    return o.value()


def case_div8():
    o = Out()
    v = [0, 1, 2, 7, 0x7F, 0x80, 0xAB, 0xFF]
    for k in (0, 1, 1):             # quotient, mod8, the remainder div8 leaves
        for i in BYTES:
            for j in BYTES:
                o.add(udiv(i, j, 8)[k])
        o.show()
    o.put('\n')
    for i in v:
        for j in v:
            q, r = udiv(i, j, 8)
            o.hex(q)
            o.put('r')
            o.hexw(r)
            o.put(' ')
    o.put('\n')
    for i in v:
        for j in v:
            o.hex(udiv(i, j, 8)[1])
            o.put(' ')
    o.put('\n')
    return o.value()


def case_sdiv8():
    o = Out()
    v = [x & 0xFF for x in (0, 1, -1, 7, -7, 127, -127, -128)]
    for k in (0, 1, 2):             # sdiv8, smod8, the remainder sdiv8 leaves
        for i in BYTES:
            for j in BYTES:
                o.add(sdiv(i, j, 8)[k])
        o.show()
    o.put('\n')
    for i in v:
        for j in v:
            q, r, _ = sdiv(i, j, 8)
            o.hex(q)
            o.put('r')
            o.hex(r)
            o.put(' ')
    o.put('\n')
    return o.value()


WORD_E = [0, 1, 2, 3, 4, 7, 8, 10, 0x10, 0x80, 0xFF, 0x100, 0x101, 0x400, 0x1000, 0x1234,
          0x4000, 0x7FFE, 0x7FFF, 0x8000, 0x8001, 0xC000, 0xFF00, 0xFFF9, 0xFFFE, 0xFFFF]
WORD_S = [0, 1, 7, 0x7FFF, 0x8000, 0xFFF9, 0xFFFF]
WORD_OPS = (
    mul16,
    lambda a, b: udiv(a, b, 16)[0],
    lambda a, b: udiv(a, b, 16)[1],
    lambda a, b: udiv(a, b, 16)[1],
    lambda a, b: sdiv(a, b, 16)[0],
    lambda a, b: sdiv(a, b, 16)[1],
    lambda a, b: sdiv(a, b, 16)[2],
)


def random_pairs(n):
    """The pairs of math_word.lth's generator: xorshift 7, 9, 8 from 1."""
    seed = 1

    def step(s):
        s ^= (s << 7) & 0xFFFF
        s ^= s >> 9
        s ^= (s << 8) & 0xFFFF
        return s
    for _ in range(n):
        seed = step(seed)
        a = seed
        seed = step(seed)
        b = seed
        seed = step(seed)
        b &= 0xFFFF >> (seed & 15)
        yield a, b


def case_word():
    o = Out()
    for f in WORD_OPS:
        for a, b in random_pairs(3000):
            o.add(f(a, b))
        o.show()
        for i in WORD_E:
            for j in WORD_E:
                o.add(f(i, j))
        o.show()
        o.put('\n')
    for f in WORD_OPS:
        for i in WORD_S:
            for j in WORD_S:
                o.hexw(f(i, j))
                o.put(' ')
        o.put('\n')
    return o.value()


def case_shift():
    o = Out()
    w = [0, 1, 0x8000, 0xFFFF, 0x1234, 0x8001, 0x7FFF, 0x5A5A, 0x00FF, 0xFF00]
    counts = [0, 1, 7, 8, 9, 15, 16, 17, 255]
    ops = (shl16, shr16, sar16)
    for f in ops:
        for x in w:
            for n in BYTES:
                o.add(f(x, n))
        o.show()
    o.put('\n')
    for f in ops:
        for x in w:
            for n in counts:
                o.hexw(f(x, n))
                o.put(' ')
        o.put('\n')
    return o.value()


CASES = {
    'math_mul8': case_mul8,
    'math_div8': case_div8,
    'math_sdiv8': case_sdiv8,
    'math_word': case_word,
    'math_shift': case_shift,
}


def expected_path(name):
    return os.path.join(E2E, name + '.expected.out')


class TestModel(unittest.TestCase):
    """The model's own rules, on cases worked by hand."""

    def test_signed_division_truncates(self):
        def s(a, b):
            q, r, _ = sdiv(a & 0xFF, b & 0xFF, 8)
            return sx(q, 8), sx(r, 8)
        self.assertEqual(s(-7, 2), (-3, -1))
        self.assertEqual(s(7, -2), (-3, 1))
        self.assertEqual(s(-7, -2), (3, -1))
        self.assertEqual(s(-128, -1), (-128, 0))
        self.assertEqual(s(5, 0), (-1, 5))
        self.assertEqual(s(-5, 0), (1, -5))

    def test_unsigned_division_by_zero(self):
        self.assertEqual(udiv(0x1234, 0, 16), (0xFFFF, 0x1234))

    def test_shifts_past_the_word(self):
        self.assertEqual((shl16(0xFFFF, 16), shr16(0xFFFF, 255)), (0, 0))
        self.assertEqual((sar16(0x8000, 16), sar16(0x7FFF, 255)), (0xFFFF, 0))


class TestExpected(unittest.TestCase):
    def test_expected_files_are_the_models_output(self):
        for name, make in CASES.items():
            with self.subTest(name):
                with open(expected_path(name), 'rb') as fh:
                    self.assertEqual(fh.read(), make(),
                                     f'{name}.expected.out differs from the model '
                                     '(python3 lathe/tests/test_rt_math.py --write)')


if __name__ == '__main__':
    if sys.argv[1:] == ['--write']:
        for _name, _make in CASES.items():
            with open(expected_path(_name), 'wb') as _fh:
                _fh.write(_make())
    else:
        unittest.main()
