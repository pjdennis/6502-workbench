"""fbuf.py: the function buffer gives code in the written layout and fix-ups sorted by offset
(docs/object-format.md, "Code and fix-ups"), with branches short where they reach."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lathec_support as support  # noqa: E402
import err  # noqa: E402
import fbuf  # noqa: E402

NOP, RTS, JMP, JSR = 0xEA, 0x60, 0x4C, 0x20
LDA_IMM, LDA_ABS, LDA_IND_Y, STA_ABS = 0xA9, 0xAD, 0xB1, 0x8D
BEQ, BNE, BCC, BCS, BPL, BMI, BVC, BVS, BRA = 0xF0, 0xD0, 0x90, 0xB0, 0x10, 0x30, 0x50, 0x70, 0x80
OWN = 7                 # the symbol number of the function under test


def nops(n):
    for _ in range(n):
        fbuf.op(NOP)


def code():
    fbuf.finish(OWN)
    return bytes(fbuf.code[i] for i in range(fbuf.code_length))


def fixups():
    """The fix-ups as (offset, kind, symbol, slot, addend)."""
    return [(fbuf.fix_offset[i], fbuf.fix_kind[i], fbuf.fix_symbol[i], fbuf.fix_slot[i],
             fbuf.fix_addend[i]) for i in range(fbuf.fix_count)]


class FbufTest(unittest.TestCase):
    def setUp(self):
        support.fresh()
        err.init()
        fbuf.begin()

    def assertFatal(self, number, call):
        with self.assertRaises(SystemExit):
            call()
        self.assertIn('error %d:' % number, support.error_text())


class InstructionsTest(FbufTest):
    def test_instructions_without_symbols_are_their_bytes(self):
        fbuf.op_byte(LDA_IMM, 0x48)
        fbuf.op_word(JSR, 0xF009)
        fbuf.op(RTS)
        self.assertEqual(code(), bytes([0xA9, 0x48, 0x20, 0x09, 0xF0, 0x60]))
        self.assertEqual(fixups(), [])

    def test_an_empty_function_has_no_code(self):
        self.assertEqual(code(), b'')
        self.assertEqual(fixups(), [])

    def test_an_address_fix_up_takes_two_zero_bytes_in_the_absolute_form(self):
        fbuf.op(NOP)
        fbuf.op_fix(LDA_ABS, fbuf.FIX_ADDRESS, 5, 2, 1)
        self.assertEqual(code(), bytes([NOP, LDA_ABS, 0, 0]))
        self.assertEqual(fixups(), [(2, 1, 5, 2, 1)])

    def test_low_high_and_zero_page_fix_ups_take_one_byte(self):
        fbuf.op_fix(LDA_IMM, fbuf.FIX_LOW, 3, 0xFF, 0)
        fbuf.op_fix(LDA_IMM, fbuf.FIX_HIGH, 3, 0xFF, 0x1234)
        fbuf.op_fix(LDA_IND_Y, fbuf.FIX_ZERO_PAGE, 9, 0, 0)
        self.assertEqual(code(), bytes([LDA_IMM, 0, LDA_IMM, 0, LDA_IND_Y, 0]))
        self.assertEqual(fixups(), [(1, 2, 3, 0xFF, 0), (3, 3, 3, 0xFF, 0x1234), (5, 4, 9, 0, 0)])

    def test_fix_ups_are_in_order_of_offset(self):
        fbuf.op_fix(JSR, fbuf.FIX_ADDRESS, 300, 0xFF, 0)
        fbuf.op_byte(LDA_IMM, 1)
        fbuf.op_fix(STA_ABS, fbuf.FIX_ADDRESS, 2, 1, 0)
        fbuf.op_fix(JSR, fbuf.FIX_ADDRESS, 1, 0xFF, 0)
        code()
        self.assertEqual(fixups(), [(1, 1, 300, 0xFF, 0), (6, 1, 2, 1, 0), (9, 1, 1, 0xFF, 0)])

    def test_begin_starts_again_from_nothing(self):
        label = fbuf.new_label()
        fbuf.place(label)
        fbuf.op_fix(JSR, fbuf.FIX_ADDRESS, 1, 0xFF, 0)
        code()
        fbuf.begin()
        self.assertEqual(fbuf.new_label(), label)
        fbuf.op(RTS)
        self.assertEqual(code(), bytes([RTS]))
        self.assertEqual(fixups(), [])


class RunsOnTest(FbufTest):
    """Whether the processor can run past the newest instruction into what comes next."""

    def test_an_empty_function_runs_on(self):
        self.assertTrue(fbuf.runs_on())

    def test_an_ordinary_instruction_runs_on(self):
        fbuf.op_word(JSR, 0xF009)
        self.assertTrue(fbuf.runs_on())
        fbuf.branch(BEQ, fbuf.new_label())
        self.assertTrue(fbuf.runs_on())

    def test_a_return_or_a_jump_does_not(self):
        fbuf.op(RTS)
        self.assertFalse(fbuf.runs_on())
        fbuf.op(NOP)
        fbuf.jump(fbuf.new_label())
        self.assertFalse(fbuf.runs_on())
        fbuf.op(0x40)                                           # RTI
        self.assertFalse(fbuf.runs_on())
        fbuf.op_fix(JMP, fbuf.FIX_ADDRESS, 3, fbuf.NO_SLOT, 0)    # a call turned into a jump
        self.assertFalse(fbuf.runs_on())
        fbuf.op_word(0x6C, 0x1234)                              # JMP (indirect)
        self.assertFalse(fbuf.runs_on())
        fbuf.branch(BRA, fbuf.new_label())
        self.assertFalse(fbuf.runs_on())

    def test_a_label_can_be_arrived_at_so_it_runs_on(self):
        fbuf.op(RTS)
        fbuf.place(fbuf.new_label())
        self.assertTrue(fbuf.runs_on())

    def test_an_operand_that_looks_like_a_return_is_not_one(self):
        fbuf.op_byte(LDA_IMM, RTS)
        self.assertTrue(fbuf.runs_on())
        fbuf.begin()
        fbuf.op(RTS)
        fbuf.begin()
        self.assertTrue(fbuf.runs_on())


class BranchTest(FbufTest):
    def test_a_backward_branch(self):
        top = fbuf.new_label()
        fbuf.place(top)
        nops(3)
        fbuf.branch(BNE, top)
        self.assertEqual(code(), bytes([NOP, NOP, NOP, BNE, 0xFB]))

    def test_a_forward_branch(self):
        done = fbuf.new_label()
        fbuf.branch(BEQ, done)
        nops(2)
        fbuf.place(done)
        fbuf.op(RTS)
        self.assertEqual(code(), bytes([BEQ, 2, NOP, NOP, RTS]))
        self.assertEqual(fixups(), [])

    def test_a_branch_to_the_next_instruction(self):
        here = fbuf.new_label()
        fbuf.branch(BCC, here)
        fbuf.place(here)
        self.assertEqual(code(), bytes([BCC, 0]))

    def test_a_label_at_the_end_of_the_function(self):
        end = fbuf.new_label()
        fbuf.branch(BCS, end)
        fbuf.op(RTS)
        fbuf.place(end)
        self.assertEqual(code(), bytes([BCS, 1, RTS]))

    def test_a_forward_branch_reaches_127_bytes(self):
        far = fbuf.new_label()
        fbuf.branch(BEQ, far)
        nops(127)
        fbuf.place(far)
        fbuf.op(RTS)
        self.assertEqual(code(), bytes([BEQ, 127] + [NOP] * 127 + [RTS]))

    def test_a_forward_branch_over_128_bytes_becomes_the_opposite_branch_round_a_jump(self):
        far = fbuf.new_label()
        fbuf.branch(BEQ, far)
        nops(128)
        fbuf.place(far)
        fbuf.op(RTS)
        self.assertEqual(code(), bytes([BNE, 3, JMP, 0, 0] + [NOP] * 128 + [RTS]))
        self.assertEqual(fixups(), [(3, 1, OWN, 0xFF, 133)])

    def test_a_backward_branch_reaches_128_bytes(self):
        top = fbuf.new_label()
        fbuf.place(top)
        nops(126)
        fbuf.branch(BNE, top)
        self.assertEqual(code(), bytes([NOP] * 126 + [BNE, 0x80]))

    def test_a_backward_branch_over_129_bytes_becomes_the_opposite_branch_round_a_jump(self):
        fbuf.op(NOP)
        top = fbuf.new_label()
        fbuf.place(top)
        nops(127)
        fbuf.branch(BNE, top)
        self.assertEqual(code(), bytes([NOP] * 128 + [BEQ, 3, JMP, 0, 0]))
        self.assertEqual(fixups(), [(131, 1, OWN, 0xFF, 1)])

    def test_every_condition_has_its_opposite(self):
        for branch, opposite in ((BEQ, BNE), (BNE, BEQ), (BCC, BCS), (BCS, BCC),
                                 (BPL, BMI), (BMI, BPL), (BVC, BVS), (BVS, BVC)):
            fbuf.begin()
            far = fbuf.new_label()
            fbuf.branch(branch, far)
            nops(200)
            fbuf.place(far)
            self.assertEqual(code()[:3], bytes([opposite, 3, JMP]))

    def test_a_branch_always_that_does_not_reach_is_just_a_jump(self):
        far = fbuf.new_label()
        fbuf.branch(BRA, far)
        nops(200)
        fbuf.place(far)
        self.assertEqual(code(), bytes([JMP, 0, 0] + [NOP] * 200))
        self.assertEqual(fixups(), [(1, 1, OWN, 0xFF, 203)])

    def test_distances_are_measured_in_the_written_layout(self):
        # 42 instructions that may shrink to two bytes each still count as three: 126 bytes,
        # then two more make 128, one too many.
        far = fbuf.new_label()
        fbuf.branch(BEQ, far)
        for _ in range(42):
            fbuf.op_fix(LDA_ABS, fbuf.FIX_ADDRESS, 1, 0, 0)
        nops(2)
        fbuf.place(far)
        self.assertEqual(code()[:3], bytes([BNE, 3, JMP]))

    def test_making_one_branch_long_can_put_another_out_of_reach(self):
        # The outer branch spans the inner one. Alone it would just reach; the three bytes
        # the inner one grows by push its target out of range.
        outer, inner = fbuf.new_label(), fbuf.new_label()
        fbuf.branch(BEQ, outer)         # 2 bytes
        fbuf.branch(BCC, inner)         # 2 bytes, 5 when long
        nops(125)
        fbuf.place(outer)               # short layout: 127 past the first branch
        nops(10)
        fbuf.place(inner)               # 135 past the second: long
        fbuf.op(RTS)
        self.assertEqual(code(), bytes([BNE, 3, JMP, 0, 0, BCS, 3, JMP, 0, 0] + [NOP] * 135 + [RTS]))
        self.assertEqual(fixups(), [(3, 1, OWN, 0xFF, 135), (8, 1, OWN, 0xFF, 145)])

    def test_a_short_branch_over_a_long_one_counts_its_five_bytes(self):
        skip, far = fbuf.new_label(), fbuf.new_label()
        fbuf.branch(BEQ, skip)
        fbuf.branch(BNE, far)
        fbuf.place(skip)
        nops(200)
        fbuf.place(far)
        self.assertEqual(code()[:7], bytes([BEQ, 5, BEQ, 3, JMP, 0, 0]))

    def test_a_backward_branch_over_a_long_one(self):
        top, far = fbuf.new_label(), fbuf.new_label()
        fbuf.place(top)
        fbuf.branch(BEQ, far)
        fbuf.branch(BNE, top)
        nops(200)
        fbuf.place(far)
        self.assertEqual(code()[:7], bytes([BNE, 3, JMP, 0, 0, BNE, 0xF9]))

    def test_a_jump_to_a_label_is_a_fix_up_to_the_function_itself(self):
        top = fbuf.new_label()
        fbuf.op(NOP)
        fbuf.place(top)
        fbuf.op(NOP)
        fbuf.jump(top)
        self.assertEqual(code(), bytes([NOP, NOP, JMP, 0, 0]))
        self.assertEqual(fixups(), [(3, 1, OWN, 0xFF, 1)])

    def test_a_label_after_a_long_branch_is_at_its_written_offset(self):
        far, loop = fbuf.new_label(), fbuf.new_label()
        fbuf.branch(BEQ, far)
        fbuf.place(loop)
        nops(200)
        fbuf.jump(loop)
        fbuf.place(far)
        self.assertEqual(len(code()), 208)
        self.assertEqual(fixups(), [(3, 1, OWN, 0xFF, 208), (206, 1, OWN, 0xFF, 5)])

    def test_two_labels_can_be_at_one_place(self):
        a, b = fbuf.new_label(), fbuf.new_label()
        fbuf.branch(BEQ, a)
        fbuf.branch(BNE, b)
        fbuf.place(a)
        fbuf.place(b)
        self.assertEqual(code(), bytes([BEQ, 2, BNE, 0]))


class CapacityTest(FbufTest):
    def test_a_function_with_too_much_code_is_error_75(self):
        def fill():
            for _ in range(fbuf.MAX_CODE // 3 + 1):
                fbuf.op_word(JSR, 0xF009)
            fbuf.finish(OWN)
        self.assertFatal(err.E_FUNC_BIG, fill)

    def test_a_function_can_fill_the_code_buffer(self):
        nops(fbuf.MAX_CODE)
        self.assertEqual(len(code()), fbuf.MAX_CODE)

    def test_a_function_with_too_many_instructions_is_error_75(self):
        def fill():
            for _ in range(fbuf.BUFFER_SIZE):
                fbuf.op_fix(LDA_ABS, fbuf.FIX_ADDRESS, 1, 0, 0)
        self.assertFatal(err.E_FUNC_BIG, fill)

    def test_too_many_labels_is_error_76(self):
        def fill():
            for _ in range(fbuf.MAX_LABELS + 1):
                fbuf.new_label()
        self.assertFatal(err.E_LABELS_FULL, fill)

    def test_too_many_fix_ups_is_error_77(self):
        def fill():
            for _ in range(fbuf.MAX_FIXUPS + 1):
                fbuf.op_fix(LDA_IMM, fbuf.FIX_LOW, 1, 0xFF, 0)
            fbuf.finish(OWN)
        self.assertFatal(err.E_FIXUPS_FULL, fill)

    def test_a_branch_to_a_label_that_was_never_placed_is_a_compiler_error(self):
        def lost():
            fbuf.branch(BEQ, fbuf.new_label())
            fbuf.finish(OWN)
        self.assertFatal(err.E_INTERNAL, lost)


if __name__ == '__main__':
    unittest.main()
