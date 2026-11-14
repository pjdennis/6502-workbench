"""The expected output of the end-to-end cases of the operators that call the run-time library
or stand in for it (cases/e2e/arith_*.lth), computed in Python from the rules of
docs/code-model.md, "Run-time arithmetic", and not by the 6502 algorithms. Like
test_rt_math.py, this checks that each committed NAME.expected.out is what the model gives.
To write them again:

    python3 lathe/tests/test_operators.py --write
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_rt_math import Out, expected_path, sar16, sdiv, shl16, shr16, udiv  # noqa: E402

J = [0, 1, 2, 3, 5, 7, 10, 16, 100, 127, 128, 200, 255]
T = [x & 0xFF for x in (0, 1, -1, 2, -2, 3, -7, 127, -128, 100)]
W = [0, 1, 2, 3, 7, 10, 255, 256, 1000, 0x7FFF, 0x8000, 0xFFFF]
I = [x & 0xFFFF for x in (0, 1, -1, 2, -2, 7, -7, 32767, -32768, -1000)]
TAB = [3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5, 8, 9, 7, 9, 3]


def div(a, b, bits):
    return udiv(a, b, bits)[0]


def mod(a, b, bits):
    return udiv(a, b, bits)[1]


def sd(a, b, bits):
    return sdiv(a & ((1 << bits) - 1), b & ((1 << bits) - 1), bits)[0]


def sm(a, b, bits):
    return sdiv(a & ((1 << bits) - 1), b & ((1 << bits) - 1), bits)[1]


def case_arith_ops():
    o = Out()
    for i in range(256):
        for j in J:
            o.add(i * j & 0xFF)
            o.add(div(i, j, 8))
            o.add(mod(i, j, 8))
    o.show()
    for i in range(256):
        for v in (i * 7 & 0xFF, 7 * i & 0xFF, i * 200 & 0xFF, div(i, 7, 8), div(200, i, 8),
                  mod(i, 7, 8), mod(255, i, 8), i, 255):
            o.add(v)
    o.show()
    for s in range(256):
        for t in T:
            o.add(s * t & 0xFF)
            o.add(sd(s, t, 8))
            o.add(sm(s, t, 8))
        for v in (sd(s, 4, 8), sm(s, 4, 8), sd(s, -4, 8), sd(-100, s, 8), s * -3 & 0xFF):
            o.add(v)
    o.show()
    o.put('\n')
    for u in W:
        for v in W:
            o.add(u * v & 0xFFFF)
            o.add(div(u, v, 16))
            o.add(mod(u, v, 16))
        for v in (u * 300 & 0xFFFF, 300 * u & 0xFFFF, div(u, 1000, 16), mod(u, 1000, 16),
                  div(60000, u, 16)):
            o.add(v)
    o.show()
    for x in I:
        for y in I:
            o.add(x * y & 0xFFFF)
            o.add(sd(x, y, 16))
            o.add(sm(x, y, 16))
        for v in (sd(x, 2, 16), sm(x, 2, 16), sd(x, -3, 16), sm(x, 256, 16), sd(-30000, x, 16)):
            o.add(v)
    o.show()
    for i in range(256):
        for j in J:
            for u in W:
                o.add(u * i & 0xFFFF)
                o.add(i * u & 0xFFFF)
                o.add(div(u, i, 16))
                o.add(mod(u, j, 16))
            o.add(i * j)
            o.add(i * 300 & 0xFFFF)
    o.show()
    o.put('\n')
    n = 0
    for i in range(256):
        for j in J:
            o.add((i * j + j * i) & 0xFF)
            o.add(2 * (i * j) & 0xFF)
            o.add(TAB[mod(i * 5 & 0xFF, 16, 8)])
            if div(i, j, 8) == 2:
                n += 1
            if mod(i, 3, 8) == mod(j, 3, 8):
                n += 1
    o.show()
    o.hex(n & 0xFF)
    o.put('\n')
    for w in (0, 7, 10, 255, 1000, 12345, 65535):
        o.put('%d ' % w)
    o.put('\n')
    return o.value()


def case_arith_shift():
    o = Out()
    for w in (0, 1, 0x8000, 0xFFFF, 0x1234, 0x8001, 0x7FFF, 0x5A5A):
        for n in range(21):
            for v in (shl16(w, n), shr16(w, n), sar16(w, n), shl16(w, n), shl16(w, n), shr16(w, n)):
                o.add(v)
        o.show()
    o.put('\n')
    for n in range(21):
        o.hexw(shr16(0x8421, n))
        o.put(' ')
        o.hexw(sar16(0x8421, n))
        o.put(' ')
    o.put('\n')
    return o.value()


def case_arith_short():
    o = Out()
    for i in range(256):
        for c in (3, 5, 6, 7, 9, 10, 12, 10, 7, 3, 11):
            o.add(i * c & 0xFF)
    o.show()
    o.hex(0)
    o.put('\n')
    return o.value()


def case_for_until():
    """Each loop as a Python range, the end of which is the variable after the loop."""
    o = Out()

    def show(count, total, after):
        o.put('%04X/%04X/%04X ' % (count & 0xFFFF, total & 0xFFFF, after & 0xFFFF))

    def plain(first, limit, add=False, skip=None, stop=None):
        count = total = 0
        i = first
        while i < limit:
            if skip is not None and skip(i):
                i += 1
                continue
            if stop is not None and stop(i):
                break
            count += 1
            if add:
                total += i
            i += 1
        show(count, total, i)

    plain(0, 0)
    plain(5, 5)
    plain(200, 100)
    plain(7, 8, True)
    plain(0, 255, True)
    count, i, n = 0, 0, 10              # the body sets the limit to 6 when i is 3
    while i < n:
        count += 1
        if i == 3:
            n = 6
        i += 1
    show(count, 0, i)
    plain(0, 100, True, lambda i: i & 1 == 0, lambda i: i == 51)
    o.put('\n')
    plain(-128, 127, True)
    plain(3, -3)
    plain(-1, 0)
    plain(-10, 10, True, lambda s: s < 0)
    o.put('\n')
    plain(0, 0xFFFF, True)
    plain(300, 300)
    plain(0xFFFE, 0xFFFF)
    plain(250, 1000, False, None, lambda w: w == 260)
    o.put('\n')
    plain(-32768, 32767, True)
    plain(100, -100)
    plain(-300, 300, True, lambda k: k > -298)
    o.put('\n')
    return o.value()


def case_strings_long():
    text = ''.join(chr(0x41 + (i * 7) % 26) for i in range(600))
    return ('%s\n600 7\nonetwoabcdefghijkl\n%s\n' % (text, text)).encode('ascii')


def case_const_width():
    o = Out()
    for b in (~0x20 & 0xFF, 0xF7 & ~0x20 & 0xFF, ~0x21 & 0xFF, (0xF7 & ~0x20) - 2 & 0xFF, ~0x0F & 0xFF):
        o.hex(b)
        o.put(' ')
    o.put('%04X %04X\n' % (0xFFFF, ~0x20 & 0xFFFF))
    for d in range(16):
        o.put('%04X %s ' % (0xFFFF - d, 'T' if 6553 <= (0xFFFF - d) // 10 else 'F'))
    o.put('\n%04X T %04X\n' % (1200, 201))
    return o.value()


CASES = {
    'const_width': case_const_width,
    'strings_long': case_strings_long,
    'for_until': case_for_until,
    'arith_ops': case_arith_ops,
    'arith_short': case_arith_short,
    'arith_shift': case_arith_shift,
}


class TestExpected(unittest.TestCase):
    def test_expected_files_are_the_models_output(self):
        for name, make in CASES.items():
            with self.subTest(name):
                with open(expected_path(name), 'rb') as fh:
                    self.assertEqual(fh.read(), make(),
                                     f'{name}.expected.out differs from the model '
                                     '(python3 lathe/tests/test_operators.py --write)')


if __name__ == '__main__':
    if sys.argv[1:] == ['--write']:
        for _name, _make in CASES.items():
            with open(expected_path(_name), 'wb') as _fh:
                _fh.write(_make())
    else:
        unittest.main()
