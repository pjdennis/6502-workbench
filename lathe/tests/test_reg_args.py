"""lathe/tests/cases/e2e/reg_args.lth (arguments in registers) worked out in Python: its expected
output must be what this model of the program prints. Python takes arguments from left to right,
as Lathe must; where a later argument calls `bump`, the model reads the earlier ones first."""
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))

bytes_ = [3, 1, 4, 1, 5, 9, 2, 6]       # the program's tables
words = [0x1111, 0x2222, 0x3333, 0x4444]
cells = [0x0102, 0x0304, 0x0506, 0x0708]


def B(v): return v & 0xFF
def W(v): return v & 0xFFFF


# the program's functions
def mix(a, b, c): return B(a + (b << 2) + (c << 5))
def mix2(a, b): return B(a + (b << 4))
def join(w, b): return W(w + (b << 8))
def join2(b, w): return W((w << 1) + b)
def four(a, b, c, d): return B(a + (b << 1) + (c << 2) + (d << 3))
def words4(w, v, b, c): return W((w ^ v) + b - c)
def pick(t, a, b): return a if t else b
def widen(w): return w


def bumper(st):
    def bump():
        st['k'] = B(st['k'] + 1)
        st['kw'] = W(st['kw'] + 1)
        return st['k']
    return bump


def changes(a, b, c):
    a = B(a + 1)
    b = B(a + b)
    c = c ^ b
    return B(a + b + c)


def changes_word(w, b):
    b = B(b + 1)
    w = W(w + b)
    w = W(w + b)
    return w


def asm_sum(a, b, c): return B(a + b - c)
def asm_word(w, b): return (w >> 8) ^ (w & 0xFF) ^ b


def fold(n, w, step):
    if n == 0:
        return w
    return W(fold(n - 1, W(w + step), B(step + 1)) + n)


def depth(a, b, c):
    if a == 0:
        return B(b + c)
    return depth(a - 1, B(depth(a - 1, b, c) + 1), c ^ a)


def fold_through(n, w, step):
    if n == 0:
        return w
    return W(fold_through(n - 1, W(w + step), B(step + 2)) + 1)


def model():
    st = dict(k=5, kw=1000)
    bump = bumper(st)
    out = []

    def show(w):
        out.append('%04X ' % W(w))

    def showb(b):
        out.append('%02X ' % B(b))

    def nl():
        out.append('\n')

    # registers_in_use
    i, j = 2, 5
    showb(mix(i, bytes_[i], bytes_[j]))
    showb(mix(bytes_[i], bytes_[i + 1], i))
    showb(mix(bytes_[i], j, bytes_[j]))
    showb(mix2(j, bytes_[i]))
    showb(mix(i + j, B(bytes_[j] - i), bytes_[i] ^ j))
    show(join(words[i], bytes_[j]))
    show(join(cells[i], j))
    show(join(cells[i], bytes_[i]))
    show(join2(bytes_[j], words[i]))
    show(widen(words[i + 1]))
    show(widen(cells[j - 4]))
    show(widen(bytes_[j]))
    showb(bytes_[1 + i])
    show(cells[1 + i])
    nl()

    # calls_in_arguments (Python takes arguments from left to right, as Lathe must)
    showb(mix(mix2(1, 2), mix2(3, 4), mix2(5, 6)))
    showb(mix2(1, mix2(2, mix2(3, 1))))
    k = st['k']; showb(mix(k, bump(), st['k']))
    kw = st['kw']; show(join(kw, bump()))
    k = st['k']; b = bump(); show(join2(k, W(b + st['kw'])))
    a = st['k']; b = bump(); c = st['k']; d = bump(); showb(four(a, b, c, d))
    a = st['kw']; b = st['kw']; c = bump(); d = st['k']; show(words4(a, b, c, d))
    t = st['k'] > 7; a = bump(); b = st['k']; showb(pick(t, a, b))
    showb(pick(bytes_[1] == 1, bytes_[2], bytes_[3]))
    k = st['k']; showb(four(mix2(k, 1), B(k + 1), bytes_[k & 7], four(1, 2, 3, 4)))
    nl()

    # through_pointers
    showb(mix(1, 2, 3))
    a = st['k']; b = bump(); c = bytes_[st['k'] & 7]; showb(mix(a, b, c))
    showb(mix(mix2(1, 1), mix(2, 2, 2), 3))
    show(join(0x1234, 2))
    show(join(words[1], bytes_[2]))
    show(join(join(0x0100, 1), mix2(2, 3)))
    nl()

    # recursion
    show(fold(4, 100, 3))
    showb(depth(3, 1, 2))
    show(fold_through(5, 7, 1))
    nl()

    # parameters_changed
    showb(changes(1, 2, 3))
    a = st['k']; b = B(st['k'] + 1); c = bump(); showb(changes(a, b, c))
    show(changes_word(0x1000, 0x10))
    showb(asm_sum(10, 20, 3))
    k = st['k']; showb(asm_sum(k, bytes_[3], B(k + 1)))
    showb(asm_word(0x1234, 0x56))
    nl()
    return ''.join(out)


class RegArgsModelTest(unittest.TestCase):
    def test_the_expected_output_is_the_model_s(self):
        with open(os.path.join(HERE, 'cases', 'e2e', 'reg_args.expected.out')) as f:
            self.assertEqual(f.read(), model())


if __name__ == '__main__':
    unittest.main()
