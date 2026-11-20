"""lathe/tests/cases/e2e/compare_low_zero.lth (a word or an int compared with a constant whose low
byte is 0) and its expected output are made here: the program from the tables below, the output
worked out in Python, independently of the compiler. The two files must be what this gives;
LATHE_UPDATE=1 rewrites them."""
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CASE = os.path.join(HERE, 'cases', 'e2e', 'compare_low_zero')

OPS = ['<', '<=', '>', '>=']
# (name in the program, the constant): those whose low byte is 0, and those that become one
# (x > $00FF is x >= $0100, x <= $80FF is x < $8100)
WORD_K = [('0000', 0x0000), ('0100', 0x0100), ('8000', 0x8000), ('FF00', 0xFF00), ('00FF', 0x00FF),
          ('80FF', 0x80FF)]
INT_K = [('0', 0), ('256', 256), ('n32768', -32768), ('n256', -256), ('255', 255), ('n257', -257)]
# the operands: each side of every boundary, as words and as the ints of the same bits
VALUES = [0, 1, 0xFF, 0x100, 0x101, 0x1FF, 0x7FFF, 0x8000, 0x8001, 0x80FF, 0x8100, 0xFEFF, 0xFF00,
          0xFF01, 0xFFFF]

HEADER = '''; Words and ints compared with a constant whose low byte is 0 compare their high bytes alone
; (lathe/docs/codegen.md, "Comparisons and conditions"): every ordering, the constant on either
; side, in a branch, as a value and as a result in the carry flag, with the constants $0000,
; $0100, $8000, $FF00 and those that become one (> $00FF is >= $0100), for operands either side
; of each boundary. This file and the expected output are made by
; lathe/tests/test_compare_low_zero.py, which works the answers out in Python: a line for each
; operand, and for each constant a word (branches, then values) and a byte (results in the
; carry) of answers, unsigned then signed.
module compare_low_zero

import libout
'''


def signed(v):
    return v - 0x10000 if v & 0x8000 else v


def holds(a, op, b):
    return {'<': a < b, '<=': a <= b, '>': a > b, '>=': a >= b}[op]


def tests(kind, k):
    """[(the test as written, its answer for an operand x)]: each ordering, x on the left and
    then on the right."""
    lit = '$%04X' % k if kind == 'word' else str(k)
    found = []
    for op in OPS:
        found.append(('x %s %s' % (op, lit), lambda x, op=op: holds(x, op, k)))
    for op in OPS:
        found.append(('%s %s x' % (lit, op), lambda x, op=op: holds(k, op, x)))
    return found


def made():
    """(the program's text, its expected output)."""
    src = [HEADER,
           'var words: [%d]word = [%s]' % (len(VALUES), ', '.join('$%04X' % v for v in VALUES)),
           'var ints: [%d]int = [%s]' % (len(VALUES), ', '.join(str(signed(v)) for v in VALUES)),
           'var flag: bool\n']
    rows = [''] * len(VALUES)
    calls = []
    for kind, constants in (('word', WORD_K), ('int', INT_K)):
        table = 'words' if kind == 'word' else 'ints'
        for name, k in constants:
            fn = '%s_%s' % (kind[0], name)
            found = tests(kind, k)
            for n, (text, _) in enumerate(found):
                src.append('func %s_c%d(x: %s): bool\n  return %s\nend\n' % (fn, n, kind, text))
            body = ['func %s(x: %s)' % (fn, kind), '  var r: word = 0', '  var c: byte = 0']
            for n, (text, _) in enumerate(found):
                body.append('  if %s then\n    r |= $%04X\n  end' % (text, 1 << n))
            for n, (text, _) in enumerate(found):
                body.append('  flag = %s\n  if flag then\n    r |= $%04X\n  end' % (text, 1 << (8 + n)))
            for n in range(0, len(found)):
                body.append('  if %s_c%d(x) then\n    c |= $%02X\n  end' % (fn, n, 1 << n))
            body.append('  libout.hexw(r)\n  libout.hex(c)\n  libout.space()\nend\n')
            src.append('\n'.join(body))
            calls.append('    %s(%s[i])' % (fn, table))
            for i, v in enumerate(VALUES):
                x = v if kind == 'word' else signed(v)
                bits = 0
                for n, (_, answer) in enumerate(found):
                    if answer(x):
                        bits |= 1 << n
                rows[i] += '%04X%02X ' % (bits | (bits << 8), bits)
    src.append('\n'.join(['pub func main()', '  var i: byte', '  for i = 0 until %d do' % len(VALUES)]
                         + calls + ['    libout.nl()', '  end', 'end']))
    return '\n'.join(src) + '\n', ''.join(row + '\n' for row in rows)


class CompareLowZero(unittest.TestCase):
    def test_files(self):
        text, output = made()
        for suffix, want in (('.lth', text), ('.expected.out', output)):
            if os.environ.get('LATHE_UPDATE') == '1':
                with open(CASE + suffix, 'w') as f:
                    f.write(want)
            with open(CASE + suffix) as f:
                self.assertEqual(f.read(), want, CASE + suffix)


if __name__ == '__main__':
    unittest.main()
