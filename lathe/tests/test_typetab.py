"""typetab.py: the type table."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lathec_support as support  # noqa: E402
import err  # noqa: E402
import typetab  # noqa: E402


class TypeTableTest(unittest.TestCase):
    def setUp(self):
        support.fresh()
        err.init()
        typetab.init()

    def test_sizes_of_the_basic_types(self):
        sizes = [typetab.size(t) for t in
                 (typetab.BYTE_TYPE, typetab.SBYTE_TYPE, typetab.WORD_TYPE, typetab.INT_TYPE, typetab.BOOL_TYPE)]
        self.assertEqual(sizes, [1, 1, 2, 2, 1])

    def test_a_pointer_is_two_bytes_and_knows_what_it_points_to(self):
        p = typetab.pointer_to(typetab.BYTE_TYPE)
        self.assertTrue(typetab.is_pointer(p))
        self.assertFalse(typetab.is_pointer(typetab.WORD_TYPE))
        self.assertEqual(typetab.size(p), 2)
        self.assertEqual(typetab.base(p), typetab.BYTE_TYPE)

    def test_the_same_pointer_type_is_made_once(self):
        p = typetab.pointer_to(typetab.BYTE_TYPE)
        self.assertEqual(typetab.pointer_to(typetab.BYTE_TYPE), p)
        self.assertNotEqual(typetab.pointer_to(typetab.WORD_TYPE), p)
        self.assertNotEqual(typetab.pointer_to(p), p)

    def test_a_number_fits_a_type_if_it_is_in_its_range(self):
        def fits(value, t):
            return typetab.number_fits(value, False, t)
        self.assertTrue(fits(255, typetab.BYTE_TYPE))
        self.assertFalse(fits(256, typetab.BYTE_TYPE))
        self.assertTrue(fits(127, typetab.SBYTE_TYPE))
        self.assertFalse(fits(128, typetab.SBYTE_TYPE))
        self.assertTrue(fits(65535, typetab.WORD_TYPE))
        self.assertTrue(fits(32767, typetab.INT_TYPE))
        self.assertFalse(fits(32768, typetab.INT_TYPE))

    def test_a_number_below_zero_fits_only_the_signed_types(self):
        def fits(value, t):
            return typetab.number_fits(value & 0xFFFF, True, t)
        self.assertTrue(fits(-128, typetab.SBYTE_TYPE))
        self.assertFalse(fits(-129, typetab.SBYTE_TYPE))
        self.assertTrue(fits(-32768, typetab.INT_TYPE))
        self.assertFalse(fits(-1, typetab.BYTE_TYPE))
        self.assertFalse(fits(-1, typetab.WORD_TYPE))
        self.assertFalse(fits(-1, typetab.BOOL_TYPE))

    def test_a_number_is_not_a_bool_or_a_pointer(self):
        self.assertFalse(typetab.number_fits(1, False, typetab.BOOL_TYPE))
        self.assertFalse(typetab.number_fits(0, False, typetab.pointer_to(typetab.BYTE_TYPE)))
        self.assertFalse(typetab.is_number(typetab.BOOL_TYPE))
        self.assertTrue(typetab.is_number(typetab.INT_TYPE))

    def test_numbers_without_a_type_and_signed_types(self):
        self.assertTrue(typetab.is_untyped(typetab.NUMBER_TYPE))
        self.assertTrue(typetab.is_untyped(typetab.NEGATIVE_TYPE))
        self.assertFalse(typetab.is_untyped(typetab.WORD_TYPE))
        self.assertEqual([t for t in range(1, 8) if typetab.is_signed(t)],
                         [typetab.SBYTE_TYPE, typetab.INT_TYPE, typetab.NEGATIVE_TYPE])

    def test_the_largest_value_of_each_number_type(self):
        self.assertEqual([typetab.limit(t) for t in (typetab.BYTE_TYPE, typetab.SBYTE_TYPE,
                                                      typetab.WORD_TYPE, typetab.INT_TYPE)],
                         [0xFF, 0x7F, 0xFFFF, 0x7FFF])

    def test_narrowing_keeps_the_low_byte_and_the_sign_of_a_signed_byte(self):
        self.assertEqual(typetab.narrow(0x1234, typetab.BYTE_TYPE), 0x34)
        self.assertEqual(typetab.narrow(0x12FE, typetab.SBYTE_TYPE), 0xFFFE)
        self.assertEqual(typetab.narrow(0x127E, typetab.SBYTE_TYPE), 0x007E)
        self.assertEqual(typetab.narrow(0x1234, typetab.WORD_TYPE), 0x1234)
        self.assertEqual(typetab.narrow(0xFFFF, typetab.INT_TYPE), 0xFFFF)
        self.assertEqual(typetab.narrow(1, typetab.BOOL_TYPE), 1)

    def test_too_many_types_is_error_74(self):
        with self.assertRaises(SystemExit):
            t = typetab.BYTE_TYPE
            for _ in range(typetab.MAX_TYPES):
                t = typetab.pointer_to(t)
        self.assertIn('error 74:', support.error_text())


if __name__ == '__main__':
    unittest.main()
