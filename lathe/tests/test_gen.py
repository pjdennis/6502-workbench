"""gen.py: the operand stack, the instructions chosen for operands, and what the registers
are known to hold."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lathec_support as support  # noqa: E402
import err  # noqa: E402
import fbuf  # noqa: E402
import gen  # noqa: E402
import kernel  # noqa: E402
import out  # noqa: E402
import typetab  # noqa: E402

SYM, FUNC, CALL, FIX, CODE = 3, 7, 9, 10, 11


def name(text):
    kernel.name_begin()
    for ch in text:
        kernel.name_add(ch)
    return kernel.name_end()


class GenTest(unittest.TestCase):
    def setUp(self):
        support.fresh()
        err.init()
        kernel.init()
        typetab.init()
        out.init()
        gen.init()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, 'm.lo')
        pointer, _ = support.put_text(self.path.encode())
        out.open(pointer)
        kernel.module_add(name(b'm'))
        kernel.module_add(name(b'util'))
        self.own = out.symbol(out.SYM_FUNCTION, name(b'm'), name(b'f'))
        gen.function_begin()

    def code(self):
        """End the function and give its code."""
        gen.function_end(self.own, 0)
        return bytes(fbuf.code[i] for i in range(fbuf.code_length))

    def records(self):
        out.end_module()
        return support.records(self.path)

    def constant(self, value):
        gen.push(gen.O_CONST, typetab.NUMBER_TYPE, value)
        return gen.depth - 1


class OperandStackTest(GenTest):
    def test_an_operand_is_described_by_kind_type_and_value(self):
        gen.push(gen.O_CONST, typetab.NUMBER_TYPE, 72)
        gen.push(gen.O_CONST, typetab.BOOL_TYPE, 1)
        self.assertEqual(gen.depth, 2)
        self.assertEqual((gen.op_kind[1], gen.op_type[1], gen.op_value[1]), (gen.O_CONST, typetab.BOOL_TYPE, 1))
        gen.pop()
        self.assertEqual((gen.op_kind[0], gen.op_type[0], gen.op_value[0]), (gen.O_CONST, typetab.NUMBER_TYPE, 72))
        gen.pop()
        self.assertEqual(gen.depth, 0)

    def test_the_operand_kinds_are_all_different(self):
        kinds = [gen.O_CONST, gen.O_FUNC, gen.O_VAR, gen.O_SLOT, gen.O_A, gen.O_AX,
                 gen.O_FLAGS, gen.O_INDEXED]
        self.assertEqual(len(set(kinds)), len(kinds))

    def test_too_many_operands_is_error_79(self):
        with self.assertRaises(SystemExit):
            for _ in range(gen.MAX_OPERANDS + 1):
                self.constant(0)
        self.assertIn('error 79:', support.error_text())

    def test_a_function_begins_with_no_operands(self):
        self.constant(1)
        gen.function_begin()
        self.assertEqual(gen.depth, 0)


class RegistersTest(GenTest):
    def test_a_constant_goes_into_each_single_register(self):
        gen.load_register(gen.REG_A, self.constant(0x48))
        gen.load_register(gen.REG_X, self.constant(1))
        gen.load_register(gen.REG_Y, self.constant(2))
        self.assertEqual(self.code(), bytes([0xA9, 0x48, 0xA2, 1, 0xA0, 2, 0x60]))

    def test_a_constant_goes_into_a_pair_low_byte_first(self):
        gen.load_register(gen.REG_AX, self.constant(0x1234))
        self.assertEqual(self.code(), bytes([0xA9, 0x34, 0xA2, 0x12, 0x60]))

    def test_the_other_pairs(self):
        gen.load_register(gen.REG_AY, self.constant(0x1234))
        gen.forget()
        gen.load_register(gen.REG_XY, self.constant(0x5678))
        self.assertEqual(self.code(), bytes([0xA9, 0x34, 0xA0, 0x12, 0xA2, 0x78, 0xA0, 0x56, 0x60]))

    def test_a_bool_goes_into_the_carry_flag(self):
        gen.push(gen.O_CONST, typetab.BOOL_TYPE, 1)
        gen.load_register(gen.REG_C, 0)
        gen.push(gen.O_CONST, typetab.BOOL_TYPE, 0)
        gen.load_register(gen.REG_C, 1)
        self.assertEqual(self.code(), bytes([0x38, 0x18, 0x60]))

    def test_a_register_that_already_holds_the_constant_is_not_loaded_again(self):
        gen.load_register(gen.REG_A, self.constant(5))
        gen.load_register(gen.REG_A, self.constant(5))
        gen.load_register(gen.REG_X, self.constant(5))
        gen.load_register(gen.REG_A, self.constant(6))
        gen.load_register(gen.REG_AX, self.constant(0x0506))
        self.assertEqual(self.code(), bytes([0xA9, 5, 0xA2, 5, 0xA9, 6, 0x60]))

    def test_a_call_makes_the_registers_unknown(self):
        gen.load_register(gen.REG_A, self.constant(5))
        gen.call_address(0xF009)
        gen.load_register(gen.REG_A, self.constant(5))
        self.assertEqual(self.code(), bytes([0xA9, 5, 0x20, 0x09, 0xF0, 0xA9, 5, 0x60]))

    def test_a_new_function_knows_nothing_about_the_registers(self):
        gen.load_register(gen.REG_A, self.constant(5))
        gen.function_begin()
        gen.load_register(gen.REG_A, self.constant(5))
        self.assertEqual(self.code(), bytes([0xA9, 5, 0x60]))

    def test_only_constants_can_be_loaded_so_far(self):
        gen.push(gen.O_A, typetab.BYTE_TYPE, 0)
        with self.assertRaises(SystemExit):
            gen.load_register(gen.REG_X, 0)
        self.assertIn('error 39:', support.error_text())


class CallsTest(GenTest):
    def function(self, scope, text):
        return kernel.sym_add(scope, name(text), kernel.K_FUNC)

    def test_a_call_of_a_fixed_address_is_a_plain_jsr(self):
        gen.call_address(0xF009)
        self.assertEqual(self.code(), bytes([0x20, 0x09, 0xF0, 0x60]))
        self.assertEqual(fbuf.fix_count, 0)
        self.assertNotIn(CALL, [kind for kind, _ in self.records()])

    def test_a_call_of_a_function_is_a_jsr_with_a_fix_up_and_a_call_record(self):
        gen.call_function(self.function(1, b'helper'))
        self.assertEqual(self.code(), bytes([0x20, 0, 0, 0x60]))
        self.assertEqual((fbuf.fix_offset[0], fbuf.fix_kind[0], fbuf.fix_symbol[0], fbuf.fix_slot[0],
                          fbuf.fix_addend[0]), (1, 1, 1, 0xFF, 0))
        records = self.records()
        self.assertIn((SYM, b'\x01\x0butil.helper'), records)
        self.assertIn((CALL, b'\x01\x00\x00\xff\xff'), records)

    def test_a_function_gets_its_object_symbol_when_first_used_and_keeps_it(self):
        helper = self.function(1, b'helper')
        other = self.function(kernel.SCOPE_MODULE, b'other')
        gen.call_function(helper)
        gen.call_function(other)
        gen.call_function(helper)
        self.assertEqual((kernel.sym_obj[helper], kernel.sym_obj[other]), (1, 2))
        self.code()
        symbols = [body for kind, body in self.records() if kind == SYM]
        self.assertEqual(symbols, [b'\x01\x03m.f', b'\x01\x0butil.helper', b'\x01\x07m.other'])

    def test_a_function_ends_with_rts(self):
        self.assertEqual(self.code(), bytes([0x60]))

    def test_no_second_rts_after_a_return_at_the_end(self):
        gen.call_address(0xF009)
        gen.ret()
        self.assertEqual(self.code(), bytes([0x20, 0x09, 0xF0, 0x60]))

    def test_the_function_is_written_to_the_object_file(self):
        gen.call_address(0xF009)
        gen.function_end(self.own, out.FUNC_EXPORTED)
        self.assertEqual(self.records()[-5:-1],
                         [(FUNC, b'\x00\x00\x04'), (FIX, b''), (CODE, b'\x20\x09\xf0\x60'), (12, b'')])


if __name__ == '__main__':
    unittest.main()
