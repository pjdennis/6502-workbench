"""reg.py: the operand stack, the frame, who owns the registers and what they are known to
hold (docs/codegen.md, "Operands", "Owning a register", "Remembering register contents",
"Weights")."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_support as support  # noqa: E402
from gen_support import BOOL, BYTE, INT, NEGATIVE, NUMBER, SBYTE, WORD  # noqa: E402
import err  # noqa: E402
import fbuf  # noqa: E402
import kernel  # noqa: E402
import reg  # noqa: E402

A, X, Y = reg.A, reg.X, reg.Y


class RegTest(support.GenTest):
    def memory(self, t, symbol=5, slot=fbuf.NO_SLOT, value=0, more=0):
        reg.push_memory(t, symbol, slot, value, more, kernel.NO_SYM)
        return reg.depth - 1

    def constant(self, value, t=NUMBER):
        reg.push(reg.O_CONST, t, value)
        return reg.depth - 1


class OperandStackTest(RegTest):
    def test_an_operand_is_described_by_kind_type_and_value(self):
        self.constant(72)
        self.constant(1, BOOL)
        self.assertEqual(reg.depth, 2)
        self.assertEqual((reg.op_kind[1], reg.op_type[1], reg.op_value[1]), (reg.O_CONST, BOOL, 1))
        reg.pop()
        self.assertEqual((reg.op_kind[0], reg.op_type[0], reg.op_value[0]), (reg.O_CONST, NUMBER, 72))
        reg.pop()
        self.assertEqual(reg.depth, 0)

    def test_the_operand_kinds_are_all_different(self):
        kinds = [reg.O_CONST, reg.O_FUNC, reg.O_VAR, reg.O_A, reg.O_AX, reg.O_COND]
        self.assertEqual(len(set(kinds)), len(kinds))

    def test_too_many_operands_is_error_79(self):
        def fill():
            for _ in range(reg.MAX_OPERANDS + 1):
                self.constant(0)
        self.assertFatal(err.E_OPERANDS_FULL, fill)

    def test_a_function_begins_with_no_operands(self):
        self.constant(1)
        reg.begin(self.own)
        self.assertEqual(reg.depth, 0)

    def test_swap_exchanges_the_two_newest_and_the_owner_goes_with_its_operand(self):
        self.constant(7)
        reg.push_register(BYTE)
        reg.swap()
        self.assertEqual((reg.op_kind[0], reg.op_kind[1], reg.op_value[1]), (reg.O_A, reg.O_CONST, 7))
        self.assertEqual(reg.owner, 0)

    def test_squeeze_removes_the_operand_under_the_newest(self):
        self.constant(1)
        self.constant(2)
        self.constant(3)
        reg.squeeze()
        self.assertEqual((reg.depth, reg.op_value[0], reg.op_value[1]), (2, 1, 3))

    def test_the_bytes_of_a_constant_and_of_a_widened_byte_are_known(self):
        c = self.constant(0x1234, WORD)
        self.assertEqual((reg.const_byte(c, 0), reg.const_byte(c, 1)), (0x34, 0x12))
        v = self.memory(BYTE)
        reg.op_type[v] = WORD                   # a byte where a word is wanted: one real byte
        self.assertFalse(reg.is_const_byte(v, 0))
        self.assertTrue(reg.is_const_byte(v, 1))
        self.assertEqual(reg.const_byte(v, 1), 0)

    def test_two_operands_are_the_same_place_if_their_fix_ups_are_equal(self):
        a = self.memory(WORD, 5, fbuf.NO_SLOT, 0)
        b = self.memory(WORD, 5, fbuf.NO_SLOT, 0)
        c = self.memory(BYTE, 5, fbuf.NO_SLOT, 1)
        d = self.memory(WORD, 5, 0, 0)
        self.assertTrue(reg.same_place(a, b))
        self.assertFalse(reg.same_place(a, c))
        self.assertFalse(reg.same_place(a, d))
        self.assertFalse(reg.same_place(a, self.constant(0)))


class InstructionsTest(RegTest):
    def test_memory_is_reached_by_fix_up_zero_page_fix_up_or_fixed_address(self):
        reg.load(A, self.memory(BYTE, 5), 0)
        reg.load(X, self.memory(WORD, self.own, 2), 1)
        reg.load(Y, self.memory(BYTE, 6, fbuf.NO_SLOT, 0, reg.F_ZP), 0)
        reg.store(A, self.memory(BYTE, kernel.NO_OBJ, fbuf.NO_SLOT, 0xD020), 0)
        reg.store(A, self.memory(BYTE, kernel.NO_OBJ, fbuf.NO_SLOT, 0x10), 0)
        self.assertEqual(self.listing(), ['LDA g5', 'LDX s2+1', 'LDY zp:g6', 'STA $D020', 'STA $10', 'RTS'])

    def test_a_fixed_address_in_zero_page_gets_the_zero_page_opcode(self):
        # The linker shrinks only instructions with fix-ups, so GEN must choose here.
        fixed = self.memory(WORD, kernel.NO_OBJ, fbuf.NO_SLOT, 0xFF)
        reg.alu(reg.OP_ADC, fixed, 0)
        reg.alu(reg.OP_ADC, fixed, 1)
        reg.modify(reg.OP_INC, fixed, 0)
        self.assertEqual(self.listing(), ['ADC $FF', 'ADC $0100', 'INC $FF', 'RTS'])

    def test_a_constant_operand_is_an_immediate(self):
        c = self.constant(0x1234, WORD)
        reg.load(A, c, 0)
        reg.alu(reg.OP_ADC, c, 1)
        reg.compare(c, 0)
        reg.load(X, c, 1)
        reg.load(Y, c, 0)
        self.assertEqual(self.listing(), ['LDA #$34', 'ADC #$12', 'CMP #$34', 'LDX #$12', 'LDY #$34', 'RTS'])

    def test_the_one_byte_instructions(self):
        reg.accumulator(reg.OP_ASL)
        reg.accumulator(reg.OP_LSR)
        reg.accumulator(reg.OP_ROL)
        reg.accumulator(reg.OP_ROR)
        reg.implied(reg.OP_CLC)
        reg.implied(reg.OP_SEC)
        reg.step_x(reg.OP_INX)
        reg.step_x(reg.OP_DEX)
        self.assertEqual(self.listing(), ['ASL', 'LSR', 'ROL', 'ROR', 'CLC', 'SEC', 'INX', 'DEX', 'RTS'])


class RegisterMemoryTest(RegTest):
    def test_a_register_that_holds_the_constant_is_not_loaded_again(self):
        reg.load_const(A, 5)
        reg.load_const(A, 5)
        reg.load_const(A, 6)
        self.assertEqual(self.listing(), ['LDA #$05', 'LDA #$06', 'RTS'])

    def test_a_constant_another_register_holds_is_transferred(self):
        reg.load_const(A, 5)
        reg.load_const(X, 5)
        reg.load_const(Y, 5)
        reg.load_const(X, 7)
        reg.load_const(A, 7)
        reg.load_const(Y, 7)
        self.assertEqual(self.listing(), ['LDA #$05', 'TAX', 'TAY', 'LDX #$07', 'TXA', 'TAY', 'RTS'])

    def test_x_and_y_cannot_be_loaded_from_each_other(self):
        reg.load_const(X, 5)
        reg.load_const(Y, 5)
        self.assertEqual(self.listing(), ['LDX #$05', 'LDY #$05', 'RTS'])

    def test_a_variable_a_register_holds_a_copy_of_is_not_loaded_again(self):
        v = self.memory(WORD)
        reg.load(A, v, 0)
        reg.load(A, v, 0)
        reg.load(X, v, 0)
        reg.load(A, v, 1)
        self.assertEqual(self.listing(), ['LDA g5', 'TAX', 'LDA g5+1', 'RTS'])

    def test_a_store_makes_the_register_a_copy_and_keeps_its_constant(self):
        v = self.memory(WORD)
        reg.load_const(A, 0)
        reg.store(A, v, 0)
        reg.store(A, v, 1)
        reg.load(A, v, 1)
        reg.load_const(A, 0)
        self.assertEqual(self.listing(), ['LDA #$00', 'STA g5', 'STA g5+1', 'RTS'])

    def test_a_store_ends_the_copies_other_registers_held_of_that_byte(self):
        v = self.memory(BYTE)
        reg.load(X, v, 0)
        reg.load_const(A, 1)
        reg.store(A, v, 0)
        reg.load(X, v, 0)
        self.assertEqual(self.listing(), ['LDX g5', 'LDA #$01', 'STA g5', 'TAX', 'RTS'])

    def test_changing_memory_ends_the_copies_of_it(self):
        v = self.memory(BYTE)
        reg.load(A, v, 0)
        reg.modify(reg.OP_INC, v, 0)
        reg.load(A, v, 0)
        self.assertEqual(self.listing(), ['LDA g5', 'INC g5', 'LDA g5', 'RTS'])

    def test_arithmetic_in_a_ends_what_was_known_of_it(self):
        v = self.memory(BYTE)
        reg.load(A, v, 0)
        reg.alu(reg.OP_ADC, v, 0)
        reg.load(A, v, 0)
        self.assertEqual(self.listing(), ['LDA g5', 'ADC g5', 'LDA g5', 'RTS'])

    def test_a_fixed_address_is_never_remembered(self):
        port = self.memory(BYTE, kernel.NO_OBJ, fbuf.NO_SLOT, 0xD020)
        reg.load(A, port, 0)
        reg.load(A, port, 0)
        reg.store(A, port, 0)
        reg.load(A, port, 0)
        self.assertEqual(self.listing(), ['LDA $D020', 'LDA $D020', 'STA $D020', 'LDA $D020', 'RTS'])

    def test_everything_is_forgotten_at_a_label_that_is_gone_to(self):
        v = self.memory(BYTE)
        skip = fbuf.new_label()
        reg.load(A, v, 0)
        fbuf.branch(0xF0, skip)
        reg.implied(reg.OP_CLC)
        reg.label(skip)
        reg.load(A, v, 0)
        self.assertEqual(self.listing(), ['LDA g5', 'BEQ @6', 'CLC', 'LDA g5', 'RTS'])

    def test_everything_is_forgotten_at_a_label_after_code_that_cannot_be_reached(self):
        # What that code seemed to load was never loaded.
        v, w = self.memory(BYTE, 5), self.memory(BYTE, 6)
        skip = fbuf.new_label()
        reg.load(A, v, 0)
        fbuf.jump(skip)
        reg.load(A, w, 0)
        reg.label(skip)
        reg.load(A, w, 0)
        self.assertEqual(self.listing(), ['LDA g5', 'LDA g6', 'RTS'])

    def test_nothing_is_forgotten_at_a_label_no_instruction_goes_to(self):
        v = self.memory(BYTE)
        reg.load(A, v, 0)
        reg.label(fbuf.new_label())
        reg.load(A, v, 0)
        self.assertEqual(self.listing(), ['LDA g5', 'RTS'])

    def test_everything_is_forgotten_at_the_top_of_a_loop(self):
        v = self.memory(BYTE)
        reg.load(A, v, 0)
        reg.loop_label(fbuf.new_label())
        reg.load(A, v, 0)
        self.assertEqual(self.listing(), ['LDA g5', 'LDA g5', 'RTS'])

    def test_put_stores_from_whichever_register_holds_the_byte(self):
        v, w = self.memory(BYTE, 5), self.memory(BYTE, 6)
        reg.load(X, v, 0)
        reg.put(v, 0, w, 0)
        reg.put_const(0, w, 0)
        reg.load_const(Y, 9)
        reg.put_const(9, w, 0)
        reg.put(self.constant(9), 0, v, 0)
        self.assertEqual(self.listing(), ['LDX g5', 'STX g6', 'LDA #$00', 'STA g6', 'LDY #$09', 'STY g6',
                                          'STY g5', 'RTS'])


class FlagsTest(RegTest):
    def test_no_compare_with_zero_after_a_load_of_that_register(self):
        v = self.memory(BYTE)
        reg.load(A, v, 0)
        reg.test(A)
        self.assertEqual(self.listing(), ['LDA g5', 'RTS'])

    def test_a_compare_with_zero_when_the_flags_show_something_else(self):
        v = self.memory(BYTE)
        reg.load(A, v, 0)
        reg.load(X, self.constant(3), 0)
        reg.test(A)
        reg.test(A)
        reg.test(X)
        self.assertEqual(self.listing(), ['LDA g5', 'LDX #$03', 'CMP #$00', 'CPX #$00', 'RTS'])

    def test_a_store_leaves_the_flags_and_a_compare_or_memory_change_spoils_them(self):
        v = self.memory(BYTE)
        reg.load(A, v, 0)
        reg.store(A, v, 0)
        reg.test(A)
        reg.compare(self.constant(4), 0)
        reg.test(A)
        reg.modify(reg.OP_DEC, v, 0)
        reg.test(A)
        self.assertEqual(self.listing(), ['LDA g5', 'STA g5', 'CMP #$04', 'CMP #$00', 'DEC g5', 'CMP #$00', 'RTS'])

    def test_changing_memory_leaves_the_flags_showing_that_byte(self):
        v = self.memory(WORD)
        reg.modify(reg.OP_DEC, v, 1)
        self.assertTrue(reg.shows(v, 1))
        self.assertFalse(reg.shows(v, 0))
        reg.test_byte(v, 1)
        reg.test_byte(v, 0)
        self.assertEqual(self.listing(), ['DEC g5+1', 'LDA g5', 'RTS'])

    def test_a_store_to_the_byte_the_flags_show_ends_that(self):
        v = self.memory(BYTE)
        reg.modify(reg.OP_INC, v, 0)
        reg.store(X, v, 0)
        self.assertFalse(reg.shows(v, 0))

    def test_what_the_flags_show_is_forgotten_where_a_branch_can_arrive(self):
        v = self.memory(BYTE)
        reg.modify(reg.OP_INC, v, 0)
        reg.loop_label(fbuf.new_label())
        self.assertFalse(reg.shows(v, 0))
        reg.load(A, v, 0)
        reg.forget()
        self.assertEqual(reg.flags, reg.NO_REG)

    def test_the_flags_never_show_a_fixed_address(self):
        port = self.memory(BYTE, kernel.NO_OBJ, fbuf.NO_SLOT, 0xD020)
        reg.modify(reg.OP_INC, port, 0)
        self.assertFalse(reg.shows(port, 0))

    def test_arithmetic_and_transfers_leave_the_flags_showing_a(self):
        v = self.memory(BYTE)
        reg.alu(reg.OP_AND, v, 0)
        reg.test(A)
        reg.transfer(A, X)
        reg.test(A)
        self.assertEqual(self.listing(), ['AND g5', 'TAX', 'RTS'])


class OwnerTest(RegTest):
    def test_an_operand_in_a_is_stored_in_a_temporary_before_a_changes(self):
        reg.push_register(BYTE)
        reg.load(A, self.memory(BYTE), 0)
        self.assertEqual((reg.op_kind[0], reg.op_flags[0] & reg.F_TEMP), (reg.O_VAR, reg.F_TEMP))
        self.assertEqual(reg.owner, reg.NONE)
        self.assertEqual(self.listing(), ['STA s0', 'LDA g5', 'RTS'])

    def test_a_word_in_a_and_x_is_stored_when_either_changes(self):
        reg.push_register(WORD)
        reg.load(X, self.memory(BYTE), 0)
        self.assertEqual(self.listing(), ['STA s0', 'STX s0+1', 'LDX g5', 'RTS'])

    def test_x_and_y_can_change_while_an_operand_is_in_a(self):
        reg.push_register(BYTE)
        reg.load(X, self.memory(BYTE), 0)
        reg.load(Y, self.memory(BYTE), 0)
        self.assertEqual(reg.op_kind[0], reg.O_A)
        self.assertEqual(self.listing(), ['LDX g5', 'LDY g5', 'RTS'])

    def test_an_operand_being_used_up_is_released_first(self):
        reg.push_register(BYTE)
        reg.release(0)
        reg.alu(reg.OP_ADC, self.memory(BYTE), 0)
        self.assertEqual(self.listing(), ['ADC g5', 'RTS'])

    def test_the_bytes_of_an_operand_in_the_registers_are_where_they_are(self):
        reg.push_register(WORD)
        self.assertEqual((reg.holder(0, 0), reg.holder(0, 1)), (A, X))
        reg.release(0)
        reg.load(A, 0, 1)
        self.assertEqual(self.listing(), ['TXA', 'RTS'])

    def test_a_call_claims_a_and_x(self):
        reg.push_register(WORD)
        reg.clobber()
        self.assertEqual(self.listing(), ['STA s0', 'STX s0+1', 'RTS'])

    def test_a_temporary_is_free_again_when_its_operand_is_popped(self):
        reg.push_register(BYTE)
        reg.spill(0)
        first = reg.op_slot[0]
        reg.pop()
        reg.push_register(BYTE)
        reg.spill(0)
        self.assertEqual(reg.op_slot[0], first)
        reg.push_register(WORD)
        reg.spill(1)                    # another size: another temporary
        self.assertEqual((reg.temp_count, reg.slot_size[reg.op_slot[1]]), (2, 2))


class FrameTest(RegTest):
    def test_parameters_and_locals_are_numbered_from_0_and_temporaries_from_first_temp(self):
        self.assertEqual(self.slot(BYTE, b'a'), 0)
        self.assertEqual(self.slot(WORD, b'b'), 1)
        self.assertEqual(reg.temp(1), fbuf.FIRST_TEMP)
        self.assertEqual(reg.temp(2), fbuf.FIRST_TEMP + 1)
        self.assertEqual((reg.local_count, reg.temp_count), (2, 2))

    def test_temporaries_are_named_t_and_a_number_after_a_dollar(self):
        n = reg.temp(1)
        text = bytes(kernel.name_char(reg.slot_name[n], i) for i in range(kernel.name_length(reg.slot_name[n])))
        self.assertEqual(text, b'$t1')
        for _ in range(10):
            n = reg.temp(1)
        self.assertEqual(kernel.name_length(reg.slot_name[n]), 4)       # $t11

    def test_too_many_locals_or_temporaries_is_error_85(self):
        def locals_():
            for _ in range(fbuf.FIRST_TEMP + 1):
                self.slot(BYTE)

        def temporaries():
            for _ in range(reg.MAX_TEMPS + 1):
                reg.temp(1)
        self.assertFatal(err.E_SLOTS_FULL, locals_)
        support.support.fresh()
        self.assertFatal(err.E_SLOTS_FULL, temporaries)

    def test_a_slot_declared_zp_is_used_with_zero_page_instructions(self):
        reg.push_slot(BYTE, self.slot(BYTE, b'p', reg.CLASS_ZP))
        reg.load(A, 0, 0)
        self.assertEqual(self.listing(), ['LDA zp:s0', 'RTS'])


class WeightTest(RegTest):
    def test_each_use_of_a_slot_adds_1_outside_loops_and_4_16_64_inside(self):
        reg.push_slot(BYTE, self.slot(BYTE))
        reg.load(A, 0, 0)
        self.assertEqual(reg.slot_weight[0], 1)
        for depth, weight in ((1, 5), (2, 21), (3, 85), (4, 149)):
            reg.loop_depth = depth
            reg.forget()
            reg.load(A, 0, 0)
            self.assertEqual(reg.slot_weight[0], weight)

    def test_the_weight_stops_at_255(self):
        reg.push_slot(BYTE, self.slot(BYTE))
        reg.loop_depth = 3
        for _ in range(5):
            reg.store(A, 0, 0)
        self.assertEqual(reg.slot_weight[0], 255)

    def test_a_variable_counts_its_uses_in_the_symbol_table(self):
        s = self.variable(WORD, b'count')
        reg.push_memory(WORD, 7, fbuf.NO_SLOT, 0, 0, s)
        reg.load(A, 0, 0)
        reg.load(X, 0, 1)
        self.assertEqual(kernel.sym_weight[s], 2)

    def test_a_load_that_is_left_out_is_not_a_use(self):
        reg.push_slot(BYTE, self.slot(BYTE))
        reg.load(A, 0, 0)
        reg.load(A, 0, 0)
        self.assertEqual(reg.slot_weight[0], 1)


class TypingTest(RegTest):
    def test_a_number_takes_the_type_it_is_given_to_if_it_fits(self):
        c = self.constant(255)
        reg.assignable(c, BYTE)
        self.assertEqual((reg.op_type[c], reg.op_value[c]), (BYTE, 255))
        n = self.constant(0xFFFF, NEGATIVE)
        reg.assignable(n, SBYTE)
        self.assertEqual((reg.op_type[n], reg.op_value[n]), (SBYTE, 0xFFFF))

    def test_a_number_that_does_not_fit_is_error_43(self):
        self.assertFatal(err.E_RANGE, lambda: reg.assignable(self.constant(256), BYTE))
        support.support.fresh()
        self.assertFatal(err.E_RANGE, lambda: reg.assignable(self.constant(0xFFFF, NEGATIVE), WORD))

    def test_a_number_is_not_a_bool(self):
        self.assertFatal(err.E_TYPE, lambda: reg.assignable(self.constant(1), BOOL))

    def test_a_byte_can_be_given_where_a_word_is_wanted_and_keeps_its_one_byte(self):
        v = self.memory(BYTE)
        reg.assignable(v, WORD)
        self.assertEqual((reg.op_type[v], reg.op_size[v]), (WORD, 1))

    def test_nothing_else_changes_type_by_itself(self):
        for actual, wanted in ((WORD, BYTE), (SBYTE, INT), (BYTE, INT), (BYTE, SBYTE), (WORD, INT),
                               (BOOL, BYTE), (BYTE, BOOL)):
            support.support.fresh()
            self.assertFatal(err.E_TYPE, lambda: reg.assignable(self.memory(actual), wanted))

    def test_two_operands_of_an_operator_take_one_type(self):
        self.assertEqual(reg.unify(self.memory(BYTE), self.constant(7)), BYTE)
        self.assertEqual(reg.unify(self.constant(7), self.memory(INT)), INT)
        self.assertEqual(reg.unify(self.memory(BYTE), self.memory(WORD)), WORD)
        self.assertEqual(reg.unify(self.memory(WORD), self.memory(BYTE)), WORD)
        self.assertEqual(reg.unify(self.constant(1), self.constant(2, NEGATIVE)), NUMBER)

    def test_signed_and_unsigned_do_not_mix(self):
        self.assertFatal(err.E_TYPE, lambda: reg.unify(self.memory(BYTE), self.memory(SBYTE)))
        support.support.fresh()
        self.assertFatal(err.E_TYPE, lambda: reg.unify(self.memory(INT), self.memory(WORD)))


if __name__ == '__main__':
    unittest.main()
