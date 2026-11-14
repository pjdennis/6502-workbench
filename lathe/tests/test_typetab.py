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

    def test_an_array_knows_its_length_its_elements_and_its_size(self):
        a = typetab.array_of(typetab.WORD_TYPE, 10, False)
        self.assertTrue(typetab.is_array(a))
        self.assertFalse(typetab.is_array(typetab.WORD_TYPE))
        self.assertFalse(typetab.is_pointer(a))
        self.assertEqual((typetab.length(a), typetab.base(a), typetab.size(a)), (10, typetab.WORD_TYPE, 20))

    def test_an_array_of_bytes_is_not_stored_by_column_and_one_of_words_is(self):
        self.assertFalse(typetab.is_column(typetab.array_of(typetab.BYTE_TYPE, 10, False)))
        self.assertTrue(typetab.is_column(typetab.array_of(typetab.WORD_TYPE, 10, False)))
        self.assertTrue(typetab.is_column(typetab.array_of(typetab.pointer_to(typetab.BYTE_TYPE), 4, False)))

    def test_an_array_declared_rows_is_another_type_not_stored_by_column(self):
        a = typetab.array_of(typetab.WORD_TYPE, 10, False)
        r = typetab.array_of(typetab.WORD_TYPE, 10, True)
        self.assertNotEqual(a, r)
        self.assertTrue(typetab.is_rows(r))
        self.assertFalse(typetab.is_column(r))
        self.assertTrue(typetab.is_array(r))
        self.assertEqual(typetab.size(r), 20)

    def test_the_same_array_type_is_made_once(self):
        a = typetab.array_of(typetab.BYTE_TYPE, 8, False)
        self.assertEqual(typetab.array_of(typetab.BYTE_TYPE, 8, False), a)
        self.assertNotEqual(typetab.array_of(typetab.BYTE_TYPE, 9, False), a)
        self.assertNotEqual(typetab.pointer_to(typetab.BYTE_TYPE), a)

    def test_arrays_of_arrays_multiply_their_sizes(self):
        inner = typetab.array_of(typetab.WORD_TYPE, 4, False)
        self.assertEqual(typetab.size(typetab.array_of(inner, 3, False)), 24)

    def test_an_array_larger_than_64k_is_error_43(self):
        with self.assertRaises(SystemExit):
            typetab.array_of(typetab.WORD_TYPE, 40000, False)
        self.assertIn('error 43:', support.error_text())

    def test_prefixes_are_built_from_the_inside_out(self):
        mark = typetab.prefix_count
        typetab.prefix(typetab.FORM_POINTER, 0)            # ^[3]word
        typetab.prefix(typetab.FORM_ARRAY, 3)
        t = typetab.build(typetab.WORD_TYPE, mark)
        self.assertEqual(t, typetab.pointer_to(typetab.array_of(typetab.WORD_TYPE, 3, False)))
        self.assertEqual(typetab.prefix_count, mark)

    def test_prefixes_of_a_type_inside_another_are_kept_apart(self):
        outer = typetab.prefix_count
        typetab.prefix(typetab.FORM_ARRAY, 2)
        inner = typetab.prefix_count
        typetab.prefix(typetab.FORM_POINTER, 0)
        self.assertEqual(typetab.build(typetab.BYTE_TYPE, inner), typetab.pointer_to(typetab.BYTE_TYPE))
        self.assertEqual(typetab.build(typetab.BYTE_TYPE, outer), typetab.array_of(typetab.BYTE_TYPE, 2, False))

    def test_nil_is_two_bytes_and_not_a_pointer_type_itself(self):
        self.assertEqual(typetab.size(typetab.NIL_TYPE), 2)
        self.assertFalse(typetab.is_pointer(typetab.NIL_TYPE))

    def test_a_record_is_a_new_type_each_time_it_is_declared(self):
        r = typetab.declared(typetab.FORM_RECORD, 7)
        q = typetab.declared(typetab.FORM_RECORD, 7)
        self.assertNotEqual(r, q)
        self.assertTrue(typetab.is_record(r))
        self.assertFalse(typetab.is_record(typetab.WORD_TYPE))
        self.assertFalse(typetab.is_enum(r))
        self.assertEqual(typetab.base(r), 7)            # the symbol that declares it
        self.assertEqual(typetab.size(r), 0)

    def test_fields_make_a_record_larger_in_order_without_padding(self):
        r = typetab.declared(typetab.FORM_RECORD, 1)
        self.assertEqual(typetab.grow(r, 2), 0)
        self.assertEqual(typetab.grow(r, 1), 2)
        self.assertEqual(typetab.grow(r, 20), 3)
        self.assertEqual(typetab.size(r), 23)
        self.assertEqual(typetab.size(typetab.array_of(r, 10, False)), 230)
        self.assertTrue(typetab.is_column(typetab.array_of(r, 10, False)))

    def test_a_record_larger_than_64k_is_error_43(self):
        r = typetab.declared(typetab.FORM_RECORD, 1)
        typetab.grow(r, 0xFFFF)
        with self.assertRaises(SystemExit):
            typetab.grow(r, 1)
        self.assertIn('error 43:', support.error_text())

    def test_an_enumeration_is_a_byte_sized_type_that_is_not_a_number(self):
        e = typetab.declared(typetab.FORM_ENUM, 3)
        self.assertTrue(typetab.is_enum(e))
        self.assertEqual(typetab.size(e), 1)
        self.assertFalse(typetab.is_number(e))
        self.assertEqual(typetab.limit(e), 0xFF)
        self.assertNotEqual(typetab.declared(typetab.FORM_ENUM, 3), e)

    def test_the_innermost_elements_of_arrays_of_arrays(self):
        r = typetab.declared(typetab.FORM_RECORD, 1)
        a = typetab.array_of(typetab.array_of(r, 2, False), 3, True)
        self.assertEqual(typetab.innermost(a), r)
        self.assertEqual(typetab.innermost(typetab.pointer_to(r)), typetab.pointer_to(r))

    def test_pointers_and_arrays_of_a_record_are_made_once_like_any_other(self):
        r = typetab.declared(typetab.FORM_RECORD, 1)
        self.assertEqual(typetab.pointer_to(r), typetab.pointer_to(r))
        self.assertNotEqual(typetab.pointer_to(r), typetab.pointer_to(typetab.declared(typetab.FORM_RECORD, 1)))

    def test_a_function_type_is_two_bytes_known_by_its_symbol_and_new_each_time(self):
        f = typetab.declared(typetab.FORM_FUNC, 5)
        self.assertTrue(typetab.is_func(f))
        self.assertEqual((typetab.size(f), typetab.base(f)), (2, 5))
        self.assertFalse(typetab.is_pointer(f) or typetab.is_record(f) or typetab.is_number(f))
        self.assertNotEqual(typetab.declared(typetab.FORM_FUNC, 5), f)
        self.assertFalse(typetab.is_func(typetab.pointer_to(f)))
        self.assertEqual(typetab.size(typetab.array_of(f, 3, False)), 6)

    def test_a_function_type_can_be_made_recursive(self):
        f = typetab.declared(typetab.FORM_FUNC, 5)
        g = typetab.declared(typetab.FORM_FUNC, 6)
        typetab.make_recursive(g)
        self.assertEqual((typetab.is_recursive(f), typetab.is_recursive(g)), (False, True))
        self.assertFalse(typetab.is_recursive(typetab.WORD_TYPE))


if __name__ == '__main__':
    unittest.main()
