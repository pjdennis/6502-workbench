"""cond.py: comparisons leave a Condition, and `and`, `or`, `not`, a test, a value and the
carry flag are made from Conditions (docs/codegen.md, "Comparisons and conditions")."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_support as support  # noqa: E402
from gen_support import BOOL, BYTE, INT, NUMBER, SBYTE, WORD  # noqa: E402
import cond  # noqa: E402
import err  # noqa: E402
import fbuf  # noqa: E402
import fold  # noqa: E402
import gen  # noqa: E402
import reg  # noqa: E402


class CondTest(support.GenTest):
    def compare(self, op, t, number=None):
        """Compare two new locals of type t, or one with a number. Returns the branch."""
        self.local(t)
        if number is None:
            self.local(t)
        else:
            gen.constant(NUMBER, number)
        cond.compare(op)
        return reg.op_value[reg.depth - 1]

    def if_false(self):
        """Use the Condition as a test with an empty body, so its branches can be read."""
        target = cond.jump_false()
        reg.implied(reg.OP_CLC)
        reg.label(target)


class CompareTest(CondTest):
    def test_bytes_are_compared_with_cmp_and_the_answer_is_z_or_the_carry(self):
        for op, branch in ((fold.EQ, cond.OP_BEQ), (fold.NE, cond.OP_BNE), (fold.LT, cond.OP_BCC),
                           (fold.GE, cond.OP_BCS)):
            gen.function_begin(self.own)
            self.assertEqual(self.compare(op, BYTE), branch)
            self.assertEqual((reg.depth, reg.op_kind[0], reg.op_type[0]), (1, reg.O_COND, BOOL))
            reg.pop()
            self.assertEqual(self.listing(), ['LDA s0', 'CMP s1', 'RTS'])

    def test_greater_and_less_or_equal_exchange_the_operands(self):
        self.assertEqual(self.compare(fold.GT, BYTE), cond.OP_BCC)
        reg.pop()
        self.assertEqual(self.listing(), ['LDA s1', 'CMP s0', 'RTS'])

    def test_with_a_constant_they_add_one_to_it_instead(self):
        self.assertEqual(self.compare(fold.GT, BYTE, 5), cond.OP_BCS)
        self.assertEqual(self.compare(fold.LE, BYTE, 5), cond.OP_BCC)
        reg.pop()
        reg.pop()
        self.assertEqual(self.listing(), ['LDA s0', 'CMP #$06', 'LDA s1', 'CMP #$06', 'RTS'])

    def test_what_cannot_be_otherwise_is_a_constant(self):
        for op, number, answer in ((fold.GT, 255, 0), (fold.LE, 255, 1), (fold.LT, 0, 0), (fold.GE, 0, 1)):
            self.compare(op, BYTE, number)
            self.assertEqual((reg.op_kind[reg.depth - 1], reg.op_value[reg.depth - 1]), (reg.O_CONST, answer))
        self.assertEqual(fbuf.used, 0)

    def test_zero_needs_no_cmp_after_a_load(self):
        self.assertEqual(self.compare(fold.EQ, BYTE, 0), cond.OP_BEQ)
        reg.pop()
        self.assertEqual(self.listing(), ['LDA s0', 'RTS'])

    def test_a_word_is_zero_if_the_or_of_its_bytes_is(self):
        self.compare(fold.NE, WORD, 0)
        reg.pop()
        self.assertEqual(self.listing(), ['LDA s0', 'ORA s0+1', 'RTS'])

    def test_words_are_equal_if_the_high_bytes_are_once_the_low_bytes_are(self):
        self.compare(fold.EQ, WORD)
        self.assertNotEqual(reg.op_false[0], reg.NONE)      # the low bytes differ: false at once
        self.if_false()
        self.assertEqual(self.listing(), ['LDA s0', 'CMP s1', 'BNE @17', 'LDA s0+1', 'CMP s1+1', 'BNE @17',
                                          'CLC', 'RTS'])

    def test_words_are_ordered_by_a_subtraction_that_keeps_only_the_carry(self):
        self.assertEqual(self.compare(fold.LT, WORD), cond.OP_BCC)
        reg.pop()
        self.assertEqual(self.listing(), ['LDA s0', 'CMP s1', 'LDA s0+1', 'SBC s1+1', 'RTS'])

    def test_signed_order_is_the_sign_of_the_difference_put_right_after_an_overflow(self):
        self.assertEqual(self.compare(fold.LT, SBYTE), cond.OP_BMI)
        self.assertEqual(self.compare(fold.GE, INT), cond.OP_BMI ^ cond.FLIP)
        reg.pop()
        reg.pop()
        self.assertEqual(self.listing(), ['LDA s0', 'SEC', 'SBC s1', 'BVC @11', 'EOR #$80',
                                          'LDA s2', 'CMP s3', 'LDA s2+1', 'SBC s3+1', 'BVC @27', 'EOR #$80',
                                          'RTS'])

    def test_a_signed_value_against_zero_is_its_sign_bit(self):
        self.assertEqual(self.compare(fold.LT, INT, 0), cond.OP_BMI)
        reg.pop()
        self.assertEqual(self.listing(), ['LDA s0+1', 'RTS'])

    def test_constants_are_compared_when_compiling(self):
        gen.constant(NUMBER, 3)
        gen.constant(NUMBER, 5)
        gen.negate()
        cond.compare(fold.GT)
        self.assertEqual((reg.depth, reg.op_kind[0], reg.op_type[0], reg.op_value[0]), (1, reg.O_CONST, BOOL, 1))

    def test_bools_have_no_order_and_do_not_compare_with_numbers(self):
        self.assertFatal(err.E_TYPE, lambda: self.compare(fold.LT, BOOL))
        support.support.fresh()
        gen.function_begin(self.own)
        self.assertFatal(err.E_TYPE, lambda: self.compare(fold.EQ, BOOL, 1))


class LogicTest(CondTest):
    def test_and_leaves_for_the_false_label_when_its_left_side_is_false(self):
        self.compare(fold.LT, BYTE)
        cond.left(True)
        self.compare(fold.EQ, BYTE)
        cond.right()
        self.assertEqual((reg.depth, reg.op_value[0], reg.op_true[0]), (1, cond.OP_BEQ, reg.NONE))
        self.if_false()
        self.assertEqual(self.listing(), ['LDA s0', 'CMP s1', 'BCS @17', 'LDA s2', 'CMP s3', 'BNE @17', 'CLC',
                                          'RTS'])

    def test_or_leaves_for_the_true_label_when_its_left_side_is_true(self):
        self.compare(fold.LT, BYTE)
        cond.left(False)
        self.compare(fold.EQ, BYTE)
        cond.right()
        self.assertEqual(reg.op_false[0], reg.NONE)
        self.if_false()
        self.assertEqual(self.listing(), ['LDA s0', 'CMP s1', 'BCC @16', 'LDA s2', 'CMP s3', 'BNE @17', 'CLC',
                                          'RTS'])

    def test_not_exchanges_the_labels_and_the_branch_and_generates_nothing(self):
        self.compare(fold.EQ, WORD)
        used = fbuf.used
        differ = reg.op_false[0]
        cond.invert()
        self.assertEqual((reg.op_value[0], reg.op_true[0], reg.op_false[0], fbuf.used),
                         (cond.OP_BNE, differ, reg.NONE, used))

    def test_a_bool_variable_is_true_when_it_is_not_zero(self):
        self.local(BOOL)
        self.if_false()
        self.assertEqual(self.listing(), ['LDA s0', 'BEQ @6', 'CLC', 'RTS'])

    def test_a_test_known_when_compiling_makes_no_branch(self):
        gen.constant(BOOL, 1)
        self.if_false()
        self.assertEqual(self.listing(), ['CLC', 'RTS'])

    def test_a_value_in_a_is_stored_before_a_right_side_that_is_never_run(self):
        reg.push_register(BYTE)
        gen.constant(BOOL, 1)
        cond.left(False)                    # `true or ...`: a jump round the right side
        self.local(BOOL)
        cond.right()
        cond.value()
        self.assertEqual(reg.op_kind[0], reg.O_VAR)
        self.assertEqual(self.listing()[0], 'STA s1')

    def test_and_needs_bools(self):
        self.local(BYTE)
        self.assertFatal(err.E_TYPE, lambda: cond.left(True))


class ValueTest(CondTest):
    def test_carry_set_becomes_a_value_by_rol(self):
        self.compare(fold.GE, BYTE)
        cond.value()
        self.assertEqual((reg.op_kind[0], reg.op_type[0], reg.owner), (reg.O_A, BOOL, 0))
        self.assertEqual(self.listing(), ['LDA s0', 'CMP s1', 'LDA #$00', 'ROL', 'RTS'])

    def test_carry_clear_is_turned_over(self):
        self.compare(fold.LT, BYTE)
        cond.value()
        self.assertEqual(self.listing(), ['LDA s0', 'CMP s1', 'LDA #$00', 'ROL', 'EOR #$01', 'RTS'])

    def test_anything_else_is_a_branch_over_a_load_of_1_to_a_load_of_0(self):
        self.compare(fold.EQ, BYTE)
        cond.value()
        self.assertEqual(self.listing(), ['LDA s0', 'CMP s1', 'BNE @12', 'LDA #$01', 'BNE @14', 'LDA #$00', 'RTS'])

    def test_what_is_in_a_is_stored_before_the_branch_not_on_one_side_of_it(self):
        reg.push_register(BYTE)
        cond.push(cond.OP_BEQ)
        cond.value()
        self.assertEqual(self.listing(), ['STA s0', 'BNE @9', 'LDA #$01', 'BNE @11', 'LDA #$00', 'RTS'])

    def test_a_known_condition_is_a_constant_again(self):
        gen.constant(BOOL, 0)
        cond.invert()
        cond.value()
        self.assertEqual((reg.op_kind[0], reg.op_value[0]), (reg.O_CONST, 1))


class CarryTest(CondTest):
    def carry(self):
        cond.carry(reg.depth - 1)
        reg.pop()

    def test_carry_set_is_there_already(self):
        self.compare(fold.GE, BYTE)
        self.carry()
        self.assertEqual(self.listing(), ['LDA s0', 'CMP s1', 'RTS'])

    def test_less_is_turned_round_when_the_carry_is_wanted(self):
        cond.wanted_in_carry(True)
        self.assertEqual(self.compare(fold.LT, BYTE), cond.OP_BCS)
        self.assertEqual(self.compare(fold.LT, BYTE, 10), cond.OP_BCS)
        cond.wanted_in_carry(False)
        reg.pop()
        reg.pop()
        self.assertEqual(self.listing(), ['LDA s1', 'CLC', 'SBC s0', 'LDA #$09', 'CMP s2', 'RTS'])

    def test_zero_or_not_is_an_order_when_the_carry_is_wanted(self):
        cond.wanted_in_carry(True)
        self.assertEqual(self.compare(fold.EQ, BYTE, 0), cond.OP_BCS)
        self.assertEqual(self.compare(fold.NE, BYTE, 0), cond.OP_BCS)
        cond.wanted_in_carry(False)
        reg.pop()
        reg.pop()
        self.assertEqual(self.listing(), ['LDA #$00', 'CMP s0', 'LDA s1', 'CMP #$01', 'RTS'])

    def test_equal_after_a_cmp_has_the_carry_set_too(self):
        self.compare(fold.EQ, BYTE)
        self.carry()
        self.assertEqual(self.listing(), ['LDA s0', 'CMP s1', 'BEQ @9', 'CLC', 'RTS'])

    def test_a_false_label_only_needs_the_carry_cleared_there(self):
        self.compare(fold.GE, BYTE)
        cond.left(True)
        self.compare(fold.GE, BYTE)
        cond.right()
        self.carry()
        self.assertEqual(self.listing(), ['LDA s0', 'CMP s1', 'BCC @16', 'LDA s2', 'CMP s3', 'BCS @17', 'CLC',
                                          'RTS'])

    def test_anything_else_branches_to_sec_or_clc(self):
        self.compare(fold.NE, BYTE)
        self.carry()
        self.assertEqual(self.listing(), ['LDA s0', 'CMP s1', 'BNE @11', 'CLC', 'BCC @12', 'SEC', 'RTS'])

    def test_a_constant_and_a_variable(self):
        gen.constant(BOOL, 1)
        self.carry()
        self.local(BOOL)
        self.carry()
        self.assertEqual(self.listing(), ['SEC', 'LDA s0', 'LSR', 'RTS'])


if __name__ == '__main__':
    unittest.main()
