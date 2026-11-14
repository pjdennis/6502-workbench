"""gen.py: the pending operation and where its result goes, stores, conversions, calls, the
function's records and the initial values (docs/codegen.md). The snapshot cases show the same
rules on whole functions; here each is shown alone."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_support as support  # noqa: E402
from gen_support import BOOL, BYTE, INT, NEGATIVE, NUMBER, SBYTE, WORD, name  # noqa: E402
import cond  # noqa: E402
import err  # noqa: E402
import fbuf  # noqa: E402
import fold  # noqa: E402
import gen  # noqa: E402
import kernel  # noqa: E402
import out  # noqa: E402
import reg  # noqa: E402
import typetab  # noqa: E402

SYM, VAR, FUNC, SLOT, CALL, FIX, CODE, ENDF = 3, 4, 7, 8, 9, 10, 11, 12


class PendingTest(support.GenTest):
    """An operator waits until what follows shows where its result must go."""

    def test_an_operator_generates_nothing_by_itself(self):
        self.local(BYTE)
        self.local(BYTE)
        gen.binary(fold.ADD)
        self.assertEqual((gen.pend_op, gen.pend_type, reg.depth), (fold.ADD, BYTE, 2))
        self.assertEqual(fbuf.used, 0)

    def test_pushing_the_next_operand_computes_it_into_a(self):
        self.local(BYTE)
        self.local(BYTE)
        gen.binary(fold.ADD)
        gen.constant(NUMBER, 1)
        self.assertEqual((gen.pend_op, reg.depth, reg.op_kind[0], reg.owner), (0, 2, reg.O_A, 0))
        self.assertEqual(self.listing(), ['CLC', 'LDA s0', 'ADC s1', 'RTS'])

    def test_a_word_goes_to_a_and_x_with_the_low_byte_waiting_in_y(self):
        self.local(WORD)
        self.local(WORD)
        gen.binary(fold.ADD)
        gen.settle()
        self.assertEqual(reg.op_kind[0], reg.O_AX)
        self.assertEqual(self.listing(), ['CLC', 'LDA s0', 'ADC s1', 'TAY', 'LDA s0+1', 'ADC s1+1', 'TAX', 'TYA',
                                          'RTS'])

    def test_a_store_computes_it_straight_into_the_destination(self):
        self.local(WORD, b'x')
        self.local(WORD, b'y')
        self.local(WORD, b'z')
        gen.binary(fold.ADD)
        gen.store()
        self.assertEqual(reg.depth, 0)
        self.assertEqual(self.listing(), ['CLC', 'LDA s1', 'ADC s2', 'STA s0', 'LDA s1+1', 'ADC s2+1', 'STA s0+1',
                                          'RTS'])

    def test_adding_one_to_the_destination_is_inc(self):
        i = self.local(BYTE)
        gen.local(BYTE, i)
        gen.constant(NUMBER, 1)
        gen.binary(fold.ADD)
        gen.store()
        w = self.local(WORD)
        gen.constant(NUMBER, 1)
        gen.assign(fold.ADD)
        self.assertEqual(self.listing(), ['INC s0', 'INC s1', 'BNE @11', 'INC s1+1', 'RTS'])

    def test_constants_are_folded_and_no_operation_is_pending(self):
        gen.constant(NUMBER, 6)
        gen.constant(NUMBER, 7)
        gen.binary(fold.MUL)
        self.assertEqual((gen.pend_op, reg.depth, reg.op_kind[0], reg.op_type[0], reg.op_value[0]),
                         (0, 1, reg.O_CONST, NUMBER, 42))
        gen.negate()
        self.assertEqual((reg.op_type[0], reg.op_value[0]), (NEGATIVE, 0xFFD6))

    def test_an_operation_that_changes_nothing_leaves_its_left_operand(self):
        self.local(BYTE)
        gen.constant(NUMBER, 0)
        gen.binary(fold.ADD)
        self.assertEqual((gen.pend_op, reg.depth, reg.op_kind[0]), (0, 1, reg.O_VAR))

    def test_a_right_side_in_a_is_exchanged_with_the_left_if_the_operator_commutes(self):
        self.local(BYTE)
        reg.push_register(BYTE)
        gen.binary(fold.BAND)
        gen.settle()
        self.assertEqual(self.listing(), ['AND s0', 'RTS'])

    def test_a_byte_minus_what_is_in_a_adds_the_complement(self):
        self.local(BYTE)
        reg.push_register(BYTE)
        gen.binary(fold.SUB)
        self.assertEqual((gen.pend_op, reg.depth, reg.op_kind[0]), (0, 1, reg.O_A))
        self.assertEqual(self.listing(), ['EOR #$FF', 'SEC', 'ADC s0', 'RTS'])

    def test_multiplying_by_a_power_of_two_is_a_shift(self):
        self.local(BYTE)
        gen.constant(NUMBER, 8)
        gen.binary(fold.MUL)
        self.assertEqual((gen.pend_op, reg.op_value[1]), (fold.SHL, 3))

    def test_multiplying_two_variables_calls_mul8_with_the_operands_in_a_and_x(self):
        self.local(BYTE)
        self.local(BYTE)
        gen.binary(fold.MUL)
        self.assertEqual((gen.pend_op, reg.depth, reg.op_kind[0], reg.op_type[0]), (0, 1, reg.O_A, BYTE))
        self.assertEqual(self.listing(), ['LDX s1', 'LDA s0', 'JMP g1'])

    def test_a_right_operand_in_a_goes_to_its_slot_first(self):
        self.local(WORD)
        self.local(WORD)
        self.local(WORD)
        gen.binary(fold.ADD)
        gen.settle()
        gen.binary(fold.DIV)
        self.assertEqual((reg.depth, reg.op_kind[0], reg.op_type[0]), (1, reg.O_AX, WORD))
        self.assertEqual(self.listing()[8:], ['STA f1.1', 'STX f1.1+1', 'LDX s0+1', 'LDA s0', 'JMP g1'])

    def test_a_remainder_by_a_power_of_two_is_a_mask(self):
        self.local(WORD)
        gen.constant(NUMBER, 256)
        gen.binary(fold.REM)
        self.assertEqual((gen.pend_op, reg.op_value[1]), (fold.BAND, 255))


class RegistersTargetTest(support.GenTest):
    def test_a_word_in_a_and_x_plus_a_byte_carries_into_x(self):
        reg.push_register(WORD)
        self.local(BYTE)
        gen.binary(fold.ADD)
        gen.settle()
        self.assertEqual(self.listing(), ['CLC', 'ADC s0', 'BCC @7', 'INX', 'RTS'])

    def test_a_byte_in_a_has_no_high_byte_in_x_to_carry_into(self):
        reg.push_register(BYTE)
        gen.constant(WORD, 255)
        gen.binary(fold.SUB)
        gen.settle()
        self.assertEqual(self.listing(), ['SEC', 'SBC #$FF', 'TAY', 'LDA #$00', 'SBC #$00', 'TAX', 'TYA', 'RTS'])


class StoreTest(support.GenTest):
    def test_a_byte_stored_in_a_word_gets_a_zero_high_byte(self):
        self.local(WORD)
        self.local(BYTE)
        gen.store()
        self.assertEqual(self.listing(), ['LDA s1', 'STA s0', 'LDA #$00', 'STA s0+1', 'RTS'])

    def test_a_word_in_a_and_x_is_stored_from_both(self):
        self.local(WORD)
        reg.push_register(WORD)
        gen.store()
        self.assertEqual(self.listing(), ['STA s0', 'STX s0+1', 'RTS'])

    def test_a_condition_is_stored_as_0_or_1(self):
        self.local(BOOL)
        cond.push(cond.OP_BCS)
        gen.store()
        self.assertEqual(self.listing(), ['LDA #$00', 'ROL', 'STA s0', 'RTS'])

    def test_storing_a_variable_in_itself_is_nothing(self):
        n = self.local(BYTE)
        gen.local(BYTE, n)
        gen.store()
        self.assertEqual(self.listing(), ['RTS'])

    def test_a_word_does_not_go_into_a_byte(self):
        self.local(BYTE)
        self.local(WORD)
        self.assertFatal(err.E_TYPE, gen.store)

    def test_nor_does_a_pending_word_operation(self):
        self.local(BYTE)
        self.local(WORD)
        gen.constant(NUMBER, 1)
        gen.binary(fold.ADD)
        self.assertFatal(err.E_TYPE, gen.store)


class ConversionTest(support.GenTest):
    def test_narrowing_a_variable_only_changes_its_type(self):
        self.local(WORD)
        gen.convert(BYTE)
        self.assertEqual((reg.op_kind[0], reg.op_type[0], reg.op_size[0]), (reg.O_VAR, BYTE, 1))
        self.assertEqual(fbuf.used, 0)

    def test_narrowing_a_pending_operation_computes_only_its_low_byte(self):
        self.local(WORD)
        self.local(WORD)
        gen.binary(fold.ADD)
        gen.convert(BYTE)
        gen.settle()
        self.assertEqual(self.listing(), ['CLC', 'LDA s0', 'ADC s1', 'RTS'])

    def test_widening_an_unsigned_byte_keeps_its_one_byte(self):
        self.local(BYTE)
        gen.convert(INT)
        self.assertEqual((reg.op_type[0], reg.op_size[0]), (INT, 1))
        self.assertEqual(fbuf.used, 0)

    def test_widening_a_signed_byte_carries_its_sign_into_x(self):
        self.local(SBYTE)
        gen.convert(INT)
        self.assertEqual((reg.op_kind[0], reg.op_type[0]), (reg.O_AX, INT))
        self.assertEqual(self.listing(), ['LDX #$00', 'LDA s0', 'BPL @8', 'DEX', 'RTS'])

    def test_a_byte_widened_to_a_signed_type_is_not_sign_extended_later(self):
        self.local(BYTE)
        gen.convert(INT)
        gen.convert(WORD)
        self.assertEqual((reg.op_kind[0], reg.op_type[0], reg.op_size[0]), (reg.O_VAR, WORD, 1))
        self.assertEqual(fbuf.used, 0)

    def test_a_constant_is_converted_when_compiling(self):
        gen.constant(NUMBER, 0x1234)
        gen.convert(BYTE)
        self.assertEqual((reg.op_type[0], reg.op_value[0]), (BYTE, 0x34))
        gen.constant(NUMBER, 0xFE)
        gen.convert(SBYTE)
        gen.convert(INT)
        self.assertEqual((reg.op_type[1], reg.op_value[1]), (INT, 0xFFFE))

    def test_lo_and_hi_of_a_variable_are_bytes_of_it(self):
        self.local(WORD)
        gen.part(1)
        self.assertEqual((reg.op_kind[0], reg.op_type[0], reg.op_value[0]), (reg.O_VAR, BYTE, 1))
        gen.constant(NUMBER, 0x1234)
        gen.part(0)
        self.assertEqual((reg.op_type[1], reg.op_value[1]), (BYTE, 0x34))

    def test_hi_of_a_word_in_a_and_x_is_txa(self):
        reg.push_register(WORD)
        gen.part(1)
        self.assertEqual(reg.op_kind[0], reg.O_A)
        self.assertEqual(self.listing(), ['TXA', 'RTS'])


class CallsTest(support.GenTest):
    def test_a_call_of_a_function_is_a_jsr_with_a_fix_up_and_a_call_record(self):
        gen.call(self.function(b'helper', scope=1), 0, False)
        reg.implied(reg.OP_CLC)
        self.assertEqual(self.listing(), ['JSR g1', 'CLC', 'RTS'])
        records = self.records()
        self.assertIn((SYM, b'\x01\x0butil.helper'), records)
        self.assertIn((CALL, b'\x01\x00\x00\xff\xff'), records)

    def test_a_function_gets_its_object_symbol_when_first_used_and_keeps_it(self):
        helper = self.function(b'helper', scope=1)
        other = self.function(b'other')
        for f in (helper, other, helper):
            gen.call(f, 0, False)
        self.assertEqual((kernel.sym_obj[helper], kernel.sym_obj[other]), (1, 2))
        self.listing()
        symbols = [body for kind, body in self.records() if kind == SYM]
        self.assertEqual(symbols, [b'\x01\x03m.f', b'\x01\x0butil.helper', b'\x01\x07m.other'])

    def test_the_first_argument_waits_for_a_and_the_next_is_stored_in_the_callees_slot(self):
        g = self.function(b'g', [(BYTE, 0), (WORD, 0)])
        self.assertEqual([gen.in_register(g, 0), gen.in_register(g, 1)], [True, False])
        gen.constant(NUMBER, 5)
        gen.accept(BYTE)
        gen.hold()
        gen.parameter(g, 1)
        self.local(BYTE)
        gen.store()
        gen.arguments_end(out.NO_OUTER)
        gen.call(g, 0, False)
        self.assertEqual(self.listing(), ['LDA s0', 'STA f1.1', 'LDA #$00', 'STA f1.1+1', 'LDA #$05', 'JMP g1'])

    def test_which_parameters_are_passed_in_registers(self):
        names = iter([b'g1', b'g2', b'g3', b'g4', b'g5'])

        def where(*types):
            f = self.function(next(names), [(t, 0) for t in types])
            return [gen.register_of(f, i) for i in range(len(types))]
        A, X, Y, AX, NONE = gen.REG_A, gen.REG_X, gen.REG_Y, gen.REG_AX, gen.REG_NONE
        self.assertEqual(where(BYTE, BOOL, BYTE, BYTE), [A, X, Y, NONE])
        self.assertEqual(where(WORD, BYTE, BYTE), [AX, Y, NONE])
        self.assertEqual(where(BYTE, WORD, BYTE), [A, NONE, NONE])
        self.assertEqual(where(WORD, WORD), [AX, NONE])
        self.assertEqual(where(BYTE, BYTE, WORD), [A, X, NONE])

    def test_the_callee_stores_the_registers_in_its_slots_and_they_still_hold_them(self):
        self.slot(WORD)
        self.slot(BYTE)
        gen.receive(self.function(b'g', [(WORD, 0), (BYTE, 0)]))
        self.local(WORD)
        gen.local(WORD, 0)
        gen.store()                     # s2 = s0: A and X hold it already
        self.assertEqual(self.listing(), ['STA s0', 'STX s0+1', 'STY s1', 'STA s2', 'STX s2+1', 'RTS'])

    def test_a_call_made_while_arguments_wait_names_their_function_as_outer(self):
        g = self.function(b'g', [(WORD, 0), (WORD, 0), (WORD, 0)])
        h = self.function(b'h', [], [(BYTE, gen.REG_A)])
        gen.call(h, reg.depth, True)        # in the first argument, for A and X: nothing waits
        gen.accept(WORD)
        gen.hold()
        gen.parameter(g, 1)
        gen.call(h, reg.depth, True)        # in the second, for g's frame: nothing waits there yet
        gen.store()
        gen.parameter(g, 2)
        gen.call(h, reg.depth, True)        # in the third: the second is in g's frame
        gen.store()
        gen.arguments_end(out.NO_OUTER)
        gen.call(g, 0, False)
        self.listing()
        calls = [body for kind, body in self.records() if kind == CALL]
        self.assertEqual(calls, [b'\x01\x00\x00\xff\xff', b'\x01\x00\x00\x02\x00', b'\x02\x00\x00\xff\xff'])

    def test_a_call_that_a_return_follows_is_a_jump(self):
        gen.call(self.function(b'helper'), 0, False)
        gen.ret()
        self.assertEqual(self.listing(), ['JMP g1'])

    def test_results_are_operands(self):
        value = self.function(b'value', [], [(BYTE, gen.REG_A)])
        wide = self.function(b'wide', [], [(WORD, gen.REG_AX)])
        status = self.function(b'status', [], [(BOOL, gen.REG_C)])
        gen.call(value, 0, True)
        self.assertEqual((reg.op_kind[0], reg.op_type[0], reg.owner), (reg.O_A, BYTE, 0))
        gen.call(wide, 1, True)             # the byte in A is stored first
        self.assertEqual((reg.op_kind[0], reg.op_kind[1], reg.owner), (reg.O_VAR, reg.O_AX, 1))
        gen.call(status, 2, True)
        self.assertEqual((reg.op_kind[2], reg.op_value[2]), (reg.O_COND, cond.OP_BCS))
        self.assertEqual(self.listing()[:4], ['JSR g1', 'STA s0', 'JSR g2', 'STA s1'])

    def test_a_call_forgets_what_the_registers_held(self):
        reg.load_const(reg.A, 5)
        gen.call(self.function(b'helper'), 0, False)
        reg.load_const(reg.A, 5)
        self.assertEqual(self.listing(), ['LDA #$05', 'JSR g1', 'LDA #$05', 'RTS'])


class ExternTest(support.GenTest):
    def extern(self, *params, results=()):
        return self.function(b'x', params, results, flags=kernel.SF_EXTERN, address=0x1234)

    def test_registers_are_loaded_in_the_order_y_x_a_after_the_carry(self):
        f = self.extern((WORD, gen.REG_AX), (BYTE, gen.REG_Y), (BOOL, gen.REG_C))
        gen.constant(WORD, 0xABCD)
        gen.constant(BYTE, 7)
        gen.constant(BOOL, 1)
        gen.call(f, 0, False)
        self.assertEqual(self.listing(), ['SEC', 'LDY #$07', 'LDX #$AB', 'LDA #$CD', 'JMP $1234'])
        self.assertNotIn(CALL, [kind for kind, _ in self.records()])

    def test_the_other_pairs(self):
        gen.constant(WORD, 0x1234)
        gen.call(self.function(b'ay', [(WORD, gen.REG_AY)], flags=kernel.SF_EXTERN, address=0x1000), 0, False)
        gen.constant(WORD, 0x5678)
        gen.call(self.function(b'xy', [(WORD, gen.REG_XY)], flags=kernel.SF_EXTERN, address=0x2000), 0, False)
        self.assertEqual(self.listing(), ['LDY #$12', 'LDA #$34', 'JSR $1000', 'LDY #$56', 'LDX #$78', 'JMP $2000'])

    def test_an_element_for_a_pair_is_loaded_low_byte_first_and_its_index_is_not_lost(self):
        f = self.extern((WORD, gen.REG_AX))
        words = self.variable(typetab.array_of(WORD, 4, False), b'w')
        gen.variable(words)
        self.local(BYTE)
        gen.index()
        gen.call(f, 0, False)
        gen.variable(self.variable(typetab.array_of(BYTE, 4, False), b'b'))
        self.local(BYTE)
        gen.index()
        gen.accept(WORD)
        gen.call(f, 0, False)
        self.assertEqual(self.listing(), ['LDX s0', 'LDA g1,X', 'LDY s0', 'LDX g1+4,Y', 'JSR $1234',
                                          'LDX s1', 'LDA g2,X', 'LDX #$00', 'JMP $1234'])

    def test_an_argument_computed_into_a_goes_from_there(self):
        f = self.extern((BYTE, gen.REG_X), (BYTE, gen.REG_A))
        reg.push_register(BYTE)
        gen.hold()
        self.local(BYTE)
        gen.call(f, 0, False)
        self.assertEqual(self.listing(), ['TAX', 'LDA s0', 'JMP $1234'])

    def test_an_argument_in_a_is_stored_only_if_a_later_one_needs_a(self):
        f = self.extern((BYTE, gen.REG_A), (BYTE, gen.REG_X))
        reg.push_register(BYTE)
        gen.hold()
        self.local(BYTE)
        self.local(BYTE)
        gen.binary(fold.ADD)
        gen.call(f, 0, False)
        self.assertEqual(self.listing(), ['STA s2', 'CLC', 'LDA s0', 'ADC s1', 'TAX', 'LDA s2', 'JMP $1234'])

    def test_a_byte_for_a_pair_has_a_zero_high_byte(self):
        self.local(BYTE)
        gen.accept(WORD)
        gen.call(self.extern((WORD, gen.REG_AX)), 0, False)
        self.assertEqual(self.listing(), ['LDX #$00', 'LDA s0', 'JMP $1234'])

    def test_a_bool_variable_reaches_the_carry_through_a(self):
        self.local(BOOL)
        gen.call(self.extern((BOOL, gen.REG_C)), 0, False)
        self.assertEqual(self.listing(), ['LDA s0', 'LSR', 'JMP $1234'])

    def test_results_in_other_registers_are_moved_to_a_and_x(self):
        gen.call(self.extern(results=[(BYTE, gen.REG_X)]), 0, True)
        gen.call(self.function(b'y', [], [(WORD, gen.REG_AY)], flags=kernel.SF_EXTERN, address=0x1234), 1, True)
        self.assertEqual(self.listing(), ['JSR $1234', 'TXA', 'STA s0', 'JSR $1234', 'PHA', 'TYA', 'TAX', 'PLA',
                                          'RTS'])


class ReturnTest(support.GenTest):
    def test_a_value_is_loaded_into_a_or_into_a_and_x(self):
        self.local(BYTE)
        gen.accept(WORD)
        gen.load_result()
        gen.ret()
        self.assertEqual(self.listing(), ['LDX #$00', 'LDA s0', 'RTS'])

    def test_a_status_goes_to_the_carry_before_the_value_is_loaded(self):
        self.local(BYTE)
        gen.accept(BYTE)
        gen.constant(BOOL, 0)
        gen.carry()
        gen.load_result()
        gen.ret()
        self.assertEqual(self.listing(), ['CLC', 'LDA s0', 'RTS'])

    def test_a_function_ends_with_rts_once(self):
        self.assertEqual(self.listing(), ['RTS'])
        gen.function_begin(self.own)
        gen.ret()
        self.assertEqual(self.listing(), ['RTS'])


class FunctionTest(support.GenTest):
    def test_the_slots_are_written_parameters_and_locals_first_then_temporaries(self):
        reg.new_slot(1, reg.CLASS_EITHER, reg.SLOT_PARAMETER, name(b'p'))
        reg.push_register(WORD)
        reg.spill(0)                        # a temporary, made before the local is declared
        n = reg.new_slot(2, reg.CLASS_ZP, reg.SLOT_LOCAL, name(b'n'))
        gen.local(WORD, n)
        reg.load(reg.A, 1, 0)
        gen.function_end(out.FUNC_EXPORTED)
        self.assertEqual(support.decode(self.own), ['STA s2', 'STX s2+1', 'LDA zp:s1', 'RTS'])
        records = self.records()
        self.assertEqual(records[-8:-1], [
            (FUNC, b'\x00\x00\x04'),
            (SLOT, b'\x01\x00\x01\x00\x00\x01p'),
            (SLOT, b'\x02\x00\x00\x01\x01\x01n'),
            (SLOT, b'\x02\x00\x01\x02\x02\x03$t1'),
            (FIX, records[-4][1]),
            (CODE, b'\x8d\x00\x00\x8e\x00\x00\xa5\x00\x60'),
            (ENDF, b'')])

    def test_a_new_function_starts_with_nothing(self):
        self.local(BYTE)
        reg.load(reg.A, 0, 0)
        gen.function_begin(self.own)
        self.assertEqual((reg.depth, reg.local_count, reg.temp_count, gen.pend_op), (0, 0, 0, 0))
        self.assertEqual(self.listing(), ['RTS'])


class InitialValuesTest(support.GenTest):
    def variable_with_symbol(self, t, text, flags=0, address=0):
        s = self.variable(t, text, flags, address)
        if flags & kernel.SF_AT == 0:
            kernel.sym_obj[s] = out.symbol(out.SYM_VARIABLE, name(b'm'), 0, name(text))
        return s

    def test_the_function_stores_each_value_and_loads_equal_ones_once(self):
        gen.function_end(0)
        gen.initial(self.variable_with_symbol(BYTE, b'a'), kernel.NO_OBJ, 0, 0)
        gen.initial(self.variable_with_symbol(WORD, b'w'), kernel.NO_OBJ, 0, 0)
        gen.initial(self.variable_with_symbol(BYTE, b'z', kernel.SF_ZP), kernel.NO_OBJ, 0, 7)
        gen.initial(self.variable_with_symbol(BYTE, b'port', kernel.SF_AT, 0xD020), kernel.NO_OBJ, 0, 7)
        symbol = out.symbol(out.SYM_FUNCTION, name(b'm'), 0, name(b'$init'))
        gen.init_function(symbol)
        self.assertEqual(support.decode(symbol), ['LDA #$00', 'STA g1', 'STA g2', 'STA g2+1', 'LDA #$07',
                                                  'STA zp:g3', 'STA $D020', 'RTS'])
        self.assertEqual((gen.init_count, gen.init_part), (0, symbol))

    def test_a_later_function_calls_the_one_written_before(self):
        gen.function_end(0)
        gen.initial(self.variable_with_symbol(BYTE, b'a'), kernel.NO_OBJ, 0, 1)
        first = out.symbol(out.SYM_FUNCTION, name(b'm'), 0, name(b'$init1'))
        gen.init_function(first)
        gen.initial(self.variable_with_symbol(BYTE, b'b'), kernel.NO_OBJ, 0, 2)
        last = out.symbol(out.SYM_FUNCTION, name(b'm'), 0, name(b'$init'))
        gen.init_function(last)
        self.assertEqual(support.decode(last), ['JSR g%d' % first, 'LDA #$02', 'STA g3', 'RTS'])
        self.assertIn((CALL, bytes([first, 0, 0, 0xFF, 0xFF])), self.records())

    def test_too_many_initial_values_is_error_86(self):
        v = self.variable_with_symbol(BYTE, b'a')

        def fill():
            for _ in range(gen.MAX_INITS + 1):
                gen.initial(v, kernel.NO_OBJ, 0, 0)
        self.assertFatal(err.E_INITS_FULL, fill)


class ElementsTest(support.GenTest):
    """Indexing, addresses and pointer arithmetic (docs/codegen.md, "Operands")."""

    def array(self, t, n, text=b'a', rows=False):
        """Push a module-level array variable of n elements of type t."""
        s = self.variable(typetab.array_of(t, n, rows), text)
        gen.variable(s)
        return s

    def test_a_constant_index_is_added_to_the_address(self):
        self.local(WORD)
        self.array(WORD, 10)
        gen.constant(NUMBER, 3)
        gen.index()
        gen.store()
        self.assertEqual(self.listing(), ['LDA g1+3', 'STA s0', 'LDX g1+13', 'STX s0+1', 'RTS'])

    def test_a_variable_index_and_a_constant_added_to_it(self):
        self.local(BYTE, b'n')
        self.array(BYTE, 10)
        self.local(BYTE, b'i')
        gen.constant(NUMBER, 2)
        gen.binary(fold.SUB)
        gen.index()
        gen.store()
        self.assertEqual(self.listing(), ['LDX s1', 'LDA g1+65534,X', 'STA s0', 'RTS'])

    def test_a_word_index_on_a_small_array_is_error_120(self):
        self.array(BYTE, 10)
        self.local(WORD)
        self.assertFatal(err.E_BYTE_INDEX, gen.index)

    def test_a_big_array_is_reached_through_a_pointer_in_zero_page(self):
        self.local(BYTE, b'n')
        self.array(BYTE, 1000)
        self.local(WORD, b'i')
        gen.index()
        gen.store()
        self.assertEqual(self.listing(), ['CLC', 'LDA s1', 'ADC #<g1', 'STA s2', 'LDA s1+1', 'ADC #>g1',
                                          'STA s2+1', 'LDY #$00', 'LDA (zp:s2),Y', 'STA s0', 'RTS'])
        self.assertEqual(reg.slot_class[fbuf.FIRST_TEMP], reg.CLASS_ZP)

    def test_a_pointer_index_is_scaled_by_the_element_size(self):
        self.local(WORD, b'w')
        self.local(typetab.pointer_to(WORD), b'p')
        self.local(BYTE, b'i')
        gen.index()
        gen.store()
        self.assertEqual(self.listing(), ['LDA s2', 'ASL', 'STA s3', 'TAY', 'LDA (zp:s1),Y', 'STA s0', 'INY',
                                          'LDA (zp:s1),Y', 'STA s0+1', 'RTS'])

    def test_the_address_of_an_array_is_a_pointer_to_its_first_element(self):
        self.array(BYTE, 10)
        gen.address()
        self.assertEqual((reg.op_kind[0], reg.op_type[0]), (reg.O_ADDR, typetab.pointer_to(BYTE)))

    def test_a_column_stored_array_has_no_address(self):
        self.array(WORD, 10)
        self.assertFatal(err.E_NO_ADDRESS, gen.address)

    def test_a_pointer_plus_a_number_is_a_pointer_and_two_pointers_differ_by_a_word(self):
        p = typetab.pointer_to(BYTE)
        self.local(p, b'p')
        gen.constant(NUMBER, 1)
        gen.binary(fold.ADD)
        self.assertEqual(gen.pend_type, p)
        gen.settle()
        self.local(p, b'q')
        gen.binary(fold.SUB)
        self.assertEqual(gen.pend_type, WORD)

    def test_a_pointer_cannot_be_multiplied(self):
        self.local(typetab.pointer_to(BYTE))
        gen.constant(NUMBER, 2)
        self.assertFatal(err.E_TYPE, lambda: gen.binary(fold.MUL))

    def test_an_array_is_copied_a_page_at_a_time_then_counting_down(self):
        s = self.variable(typetab.array_of(BYTE, 300, False), b'big')
        gen.variable(s)
        gen.copy_array(9, 300)
        reg.pop()
        self.assertEqual(self.listing(), ['LDX #$00', 'LDA g9,X', 'STA g1,X', 'INX', 'BNE @2', 'LDX #$2C',
                                          'LDA g9+255,X', 'STA g1+255,X', 'DEX', 'BNE @13', 'RTS'])


if __name__ == '__main__':
    unittest.main()
