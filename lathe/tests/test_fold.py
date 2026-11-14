"""fold.py: constant arithmetic. Numbers without a type are exact from -32768 to 65535 and a
result outside that is error 43; constants of a type wrap as the type does."""
import itertools
import operator
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lathec_support as support  # noqa: E402
import err  # noqa: E402
import fold  # noqa: E402
import typetab  # noqa: E402

VALUES = [-32768, -32767, -300, -129, -128, -2, -1, 0, 1, 2, 3, 7, 127, 128, 255, 256, 1000,
          32767, 32768, 40000, 65535]


def truncated_quotient(a, b):
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def truncated_remainder(a, b):
    r = abs(a) % abs(b)
    return -r if a < 0 else r


EXACT = [(fold.ADD, operator.add), (fold.SUB, operator.sub), (fold.MUL, operator.mul),
         (fold.BAND, operator.and_), (fold.BOR, operator.or_), (fold.BXOR, operator.xor),
         (fold.DIV, truncated_quotient), (fold.REM, truncated_remainder)]
COMPARISONS = [(fold.EQ, operator.eq), (fold.NE, operator.ne), (fold.LT, operator.lt),
               (fold.GE, operator.ge), (fold.GT, operator.gt), (fold.LE, operator.le)]
TYPES = [(typetab.BYTE_TYPE, 0, 255), (typetab.SBYTE_TYPE, -128, 127),
         (typetab.WORD_TYPE, 0, 65535), (typetab.INT_TYPE, -32768, 32767)]


def exact(op, a, b):
    """fold.exact on Python numbers: the result as a Python number, or None for an error."""
    support.fresh()
    try:
        value, negative = fold.exact(op, a & 0xFFFF, a < 0, b & 0xFFFF, b < 0)
    except SystemExit:
        return None
    return value - 0x10000 if negative else value


class ExactTest(unittest.TestCase):
    def setUp(self):
        support.fresh()
        err.init()

    def test_every_operator_gives_the_exact_result_or_an_error_if_it_is_out_of_range(self):
        for (op, python), a, b in itertools.product(EXACT, VALUES, VALUES):
            if b == 0 and op in (fold.DIV, fold.REM):
                continue
            want = python(a, b)
            if not -32768 <= want <= 65535:
                want = None
            self.assertEqual(exact(op, a, b), want, (op, a, b))

    def test_shifts_are_exact_too_and_a_right_shift_rounds_down(self):
        for a, count in itertools.product(VALUES, [0, 1, 2, 7, 8, 15, 16, 20]):
            want = a << count
            if not -32768 <= want <= 65535:
                want = None
            self.assertEqual(exact(fold.SHL, a, count), want, (a, count))
            self.assertEqual(exact(fold.SHR, a, count), a >> count, (a, count))

    def test_a_result_out_of_range_is_error_43(self):
        self.assertIsNone(exact(fold.ADD, 65535, 1))
        self.assertIn('error 43:', support.error_text())
        self.assertIsNone(exact(fold.SUB, -32768, 1))
        self.assertIn('error 43:', support.error_text())

    def test_dividing_by_zero_is_error_59(self):
        for op in (fold.DIV, fold.REM):
            self.assertIsNone(exact(op, 7, 0))
            self.assertIn('error 59:', support.error_text())
        support.fresh()
        with self.assertRaises(SystemExit):
            fold.typed(fold.DIV, typetab.BYTE_TYPE, 7, 0)
        self.assertIn('error 59:', support.error_text())


class TypedTest(unittest.TestCase):
    def test_every_operator_wraps_as_its_type_does(self):
        for t, low, high in TYPES:
            values = [v for v in VALUES if low <= v <= high]
            for (op, python), a, b in itertools.product(EXACT, values, values):
                if b == 0 and op in (fold.DIV, fold.REM):
                    continue
                want = typetab.narrow(python(a, b) & 0xFFFF, t)
                got = fold.typed(op, t, typetab.narrow(a & 0xFFFF, t), typetab.narrow(b & 0xFFFF, t))
                self.assertEqual(got, want, (t, op, a, b))

    def test_shifts_wrap_and_a_signed_right_shift_keeps_the_sign(self):
        for t, low, high in TYPES:
            for a in [v for v in VALUES if low <= v <= high]:
                for count in (0, 1, 3, 8, 15, 17):
                    held = typetab.narrow(a & 0xFFFF, t)
                    self.assertEqual(fold.typed(fold.SHL, t, held, count),
                                     typetab.narrow((a << count) & 0xFFFF, t), (t, a, count))
                    self.assertEqual(fold.typed(fold.SHR, t, held, count),
                                     typetab.narrow((a >> count) & 0xFFFF, t), (t, a, count))

    def test_examples(self):
        self.assertEqual(fold.typed(fold.ADD, typetab.BYTE_TYPE, 200, 100), 44)
        self.assertEqual(fold.typed(fold.SUB, typetab.BYTE_TYPE, 0, 1), 255)
        self.assertEqual(fold.typed(fold.SUB, typetab.SBYTE_TYPE, 0, 1), 0xFFFF)     # -1, sign-extended
        self.assertEqual(fold.typed(fold.MUL, typetab.WORD_TYPE, 300, 300), 90000 & 0xFFFF)
        self.assertEqual(fold.typed(fold.DIV, typetab.INT_TYPE, 0xFFF9, 2), 0xFFFD)  # -7 / 2 is -3
        self.assertEqual(fold.typed(fold.SHR, typetab.SBYTE_TYPE, 0xFF80, 1), 0xFFC0)


class CompareTest(unittest.TestCase):
    def test_comparisons_know_which_numbers_are_below_zero(self):
        for (op, python), a, b in itertools.product(COMPARISONS, VALUES, VALUES):
            self.assertEqual(fold.compare(op, a & 0xFFFF, a < 0, b & 0xFFFF, b < 0), python(a, b), (op, a, b))

    def test_the_operators_of_compound_assignment_are_in_token_order(self):
        self.assertEqual([fold.ADD, fold.SUB, fold.BAND, fold.BOR, fold.BXOR, fold.SHL, fold.SHR],
                         list(range(1, 8)))


if __name__ == '__main__':
    unittest.main()
