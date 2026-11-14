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
    fbuf.finish(OWN, 0)
    return support.finished()[0]


def fixups():
    """The fix-ups as (offset, kind, symbol, slot, addend)."""
    return support.finished()[1]


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
        self.assertEqual(fixups(), [(2, 5, 5, 2, 1)])

    def test_kind_5_is_for_an_instruction_with_a_zero_page_form(self):
        for opcode in (0xAD, 0xBD, 0x8D, 0x9D, 0xEE, 0xFE, 0xAE, 0xBE, 0xAC, 0xBC, 0x2C, 0xCC, 0xEC,
                       0x6D, 0x0E, 0x9C, 0x9E, 0x0C, 0x1C, 0x3C):
            fbuf.op_fix(opcode, fbuf.FIX_ADDRESS, 1, 0xFF, 0)
        for opcode in (JSR, 0xB9, 0x99, 0x19, JMP):
            fbuf.op_fix(opcode, fbuf.FIX_ADDRESS, 1, 0xFF, 0)
        code()
        self.assertEqual([f[1] for f in fixups()], [5] * 20 + [1] * 5)
        self.assertFalse(any(fbuf.has_zero_page_form(op) for op in (0x6C, 0x7C, 0x5C, 0xDC, 0xFC)))

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
        self.assertEqual(fixups(), [(1, 1, 300, 0xFF, 0), (6, 5, 2, 1, 0), (9, 1, 1, 0xFF, 0)])

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


def weights():
    """The weights counted for other functions' slots, as (symbol, slot, weight)."""
    return [(fbuf.weight_symbol[i], fbuf.weight_slot[i], fbuf.weight_value[i]) for i in range(fbuf.weight_count)]


class WeightTest(FbufTest):
    def test_uses_of_other_functions_slots_are_counted(self):
        fbuf.op_fix(STA_ABS, fbuf.FIX_ADDRESS, 3, 0, 0)        # another function's slot
        fbuf.op_fix(STA_ABS, fbuf.FIX_ADDRESS, 3, 0, 1)
        fbuf.op_fix(STA_ABS, fbuf.FIX_ADDRESS, 4, 1, 0)        # a class parameter, or a slot
        fbuf.op_fix(LDA_ABS, fbuf.FIX_ADDRESS, OWN, 0, 0)      # its own: REG counts those
        fbuf.op_fix(LDA_ABS, fbuf.FIX_ADDRESS, 5, 0xFF, 0)     # a variable: OUT counts those
        fbuf.op_fix(LDA_IND_Y, fbuf.FIX_ZERO_PAGE, 3, 2, 0)    # always in zero page
        fbuf.op_fix(JSR, fbuf.FIX_ADDRESS, 3, 0xFF, 0)
        fbuf.op(RTS)
        code()
        self.assertEqual(weights(), [(3, 0, 2), (4, 1, 1)])

    def test_a_use_inside_loops_weighs_more(self):
        outer = fbuf.new_label()
        inner = fbuf.new_label()
        fbuf.place(outer)
        fbuf.op_fix(STA_ABS, fbuf.FIX_ADDRESS, 3, 0, 0)        # 4
        fbuf.place(inner)
        fbuf.op_fix(STA_ABS, fbuf.FIX_ADDRESS, 3, 0, 0)        # 16
        fbuf.branch(BNE, inner)
        fbuf.branch(BCC, outer)
        fbuf.op_fix(STA_ABS, fbuf.FIX_ADDRESS, 3, 0, 0)        # 1
        fbuf.op(RTS)
        code()
        self.assertEqual(weights(), [(3, 0, 21)])

    def test_a_jump_back_is_a_loop_too_and_weights_stop_at_255(self):
        top = fbuf.new_label()
        fbuf.place(top)
        for _ in range(70):
            fbuf.op_fix(STA_ABS, fbuf.FIX_ADDRESS, 3, 0, 0)
        fbuf.jump(top)
        code()
        self.assertEqual(weights(), [(3, 0, 255)])

    def test_the_table_is_per_function_and_what_does_not_fit_is_not_counted(self):
        for n in range(fbuf.MAX_WEIGHTS + 1):
            fbuf.op_fix(STA_ABS, fbuf.FIX_ADDRESS, 100 + n, 0, 0)
        code()
        self.assertEqual(len(weights()), fbuf.MAX_WEIGHTS)
        fbuf.begin()
        fbuf.op(RTS)
        code()
        self.assertEqual(weights(), [])


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
        fbuf.op(NOP)
        fbuf.op(NOP)
        fbuf.place(here)
        fbuf.branch(BCC, here)
        self.assertEqual(code(), bytes([NOP, NOP, BCC, 0xFE]))

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
        fbuf.place(fbuf.new_label())    # or what follows could not be reached, and would be left out
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
        fbuf.op(NOP)
        fbuf.place(a)
        fbuf.place(b)
        self.assertEqual(code(), bytes([BEQ, 3, BNE, 1, NOP]))

    def test_a_branch_to_the_next_instruction_is_taken_out(self):
        a, b = fbuf.new_label(), fbuf.new_label()
        fbuf.op(NOP)
        fbuf.branch(BEQ, a)
        fbuf.branch(BNE, b)
        fbuf.place(b)
        self.assertFalse(fbuf.is_used(b))
        fbuf.place(a)                   # the entry before the BEQ is not known any more
        fbuf.op(RTS)
        self.assertEqual(code(), bytes([NOP, BEQ, 0, RTS]))


class JoinTest(FbufTest):
    """Two labels made one place: both names lead to where the one that is placed is."""

    def test_a_label_joined_to_one_placed_later_goes_there(self):
        first, second = fbuf.new_label(), fbuf.new_label()
        fbuf.branch(BEQ, second)
        fbuf.join(first, second)
        fbuf.op(NOP)
        fbuf.place(first)
        self.assertEqual(code(), bytes([BEQ, 1, NOP]))

    def test_a_label_joined_to_one_already_placed_goes_back_to_it(self):
        top, again = fbuf.new_label(), fbuf.new_label()
        fbuf.place(top)
        fbuf.op(NOP)
        fbuf.branch(BNE, again)
        fbuf.join(top, again)
        fbuf.jump(again)
        self.assertEqual(code(), bytes([NOP, BNE, 0xFD, JMP, 0, 0]))
        self.assertEqual(fixups(), [(4, 1, OWN, 0xFF, 0)])

    def test_joins_can_follow_each_other(self):
        a, b, c = fbuf.new_label(), fbuf.new_label(), fbuf.new_label()
        fbuf.branch(BEQ, c)
        fbuf.join(b, c)
        fbuf.join(a, b)
        fbuf.place(a)
        self.assertEqual(code(), bytes([BEQ, 0]))

    def test_a_label_is_used_once_a_branch_or_jump_goes_to_it_or_to_one_joined_to_it(self):
        a, b, c = fbuf.new_label(), fbuf.new_label(), fbuf.new_label()
        self.assertFalse(fbuf.is_used(a))
        fbuf.branch(BEQ, b)
        self.assertTrue(fbuf.is_used(b))
        fbuf.join(a, b)
        self.assertTrue(fbuf.is_used(a))
        self.assertFalse(fbuf.is_used(c))
        fbuf.jump(c)
        self.assertTrue(fbuf.is_used(c))


class FuseTest(FbufTest):
    """A branch round nothing but a JMP is one branch (docs/codegen.md, "Statements")."""

    def test_a_branch_round_a_jump_becomes_the_opposite_branch(self):
        top, skip = fbuf.new_label(), fbuf.new_label()
        fbuf.place(top)
        fbuf.op(NOP)
        fbuf.branch(BNE, skip)
        fbuf.jump(top)
        fbuf.place(skip)
        fbuf.op(RTS)
        self.assertEqual(code(), bytes([NOP, BEQ, 0xFD, RTS]))
        self.assertEqual(fixups(), [])

    def test_the_label_is_no_longer_used_if_that_was_its_only_branch(self):
        top, skip, other = fbuf.new_label(), fbuf.new_label(), fbuf.new_label()
        fbuf.place(top)
        fbuf.branch(BNE, skip)
        fbuf.jump(top)
        fbuf.place(skip)
        self.assertFalse(fbuf.is_used(skip))
        fbuf.branch(BEQ, other)
        fbuf.branch(BNE, other)
        fbuf.jump(top)
        fbuf.place(other)
        self.assertTrue(fbuf.is_used(other))
        self.assertEqual(code(), bytes([BEQ, 0xFE, BEQ, 2, BEQ, 0xFA]))

    def test_a_branch_and_a_jump_that_both_come_here_are_both_taken_out(self):
        skip = fbuf.new_label()
        fbuf.op(NOP)
        fbuf.branch(BEQ, skip)
        fbuf.jump(skip)
        self.assertFalse(fbuf.runs_on())
        self.assertFalse(fbuf.arrive(skip))
        self.assertTrue(fbuf.runs_on())
        fbuf.op(RTS)
        self.assertEqual(code(), bytes([NOP, RTS]))

    def test_a_jump_far_away_still_gets_there(self):
        far, skip = fbuf.new_label(), fbuf.new_label()
        fbuf.branch(BNE, skip)
        fbuf.jump(far)
        fbuf.place(skip)
        nops(200)
        fbuf.place(far)
        self.assertEqual(code()[:5], bytes([BNE, 3, JMP, 0, 0]))

    def test_anything_between_the_branch_and_the_jump_keeps_them_apart(self):
        top, skip = fbuf.new_label(), fbuf.new_label()
        fbuf.place(top)
        fbuf.branch(BNE, skip)
        fbuf.op(NOP)
        fbuf.jump(top)
        fbuf.place(skip)
        self.assertEqual(code(), bytes([BNE, 4, NOP, JMP, 0, 0]))

    def test_a_branch_to_another_label_is_left_alone(self):
        top, skip, other = fbuf.new_label(), fbuf.new_label(), fbuf.new_label()
        fbuf.place(top)
        fbuf.branch(BNE, other)
        fbuf.jump(top)
        fbuf.place(skip)
        fbuf.place(other)
        self.assertEqual(code(), bytes([BNE, 3, JMP, 0, 0]))

    def test_a_jump_at_the_start_of_a_function_is_not_taken_for_one(self):
        top, skip = fbuf.new_label(), fbuf.new_label()
        fbuf.place(top)
        fbuf.branch(BNE, skip)
        fbuf.jump(top)
        fbuf.place(skip)
        code()
        fbuf.begin()                    # the old entries are still in the buffer
        again = fbuf.new_label()
        fbuf.jump(again)
        fbuf.place(fbuf.new_label())
        fbuf.place(again)
        self.assertEqual(code(), bytes([JMP, 0, 0]))


class UnreachedTest(FbufTest):
    """What follows a jump or a return, with no label between, is left out."""

    def test_instructions_after_a_return_are_left_out_until_a_label(self):
        skip = fbuf.new_label()
        fbuf.branch(BEQ, skip)
        fbuf.op(RTS)
        fbuf.op(NOP)
        fbuf.op_byte(LDA_IMM, 1)
        fbuf.op_word(JSR, 0xF009)
        fbuf.op_fix(STA_ABS, fbuf.FIX_ADDRESS, 3, 0xFF, 0)
        fbuf.branch(BNE, skip)
        fbuf.jump(skip)
        fbuf.place(skip)
        fbuf.op(NOP)
        self.assertEqual(code(), bytes([BEQ, 1, RTS, NOP]))
        self.assertEqual(fixups(), [])

    def test_instructions_after_a_jump_are_left_out(self):
        top = fbuf.new_label()
        fbuf.place(top)
        fbuf.jump(top)
        fbuf.op(NOP)
        fbuf.op(RTS)
        self.assertEqual(code(), bytes([JMP, 0, 0]))
        self.assertFalse(fbuf.runs_on())

    def test_a_new_function_can_be_reached_again(self):
        fbuf.op(RTS)
        fbuf.op(NOP)
        fbuf.begin()
        fbuf.op(NOP)
        self.assertEqual(code(), bytes([NOP]))


class AsWrittenTest(FbufTest):
    """While an `asm` block is being written, its instructions are kept as written: nothing
    is left out and no branch is fused or taken out."""

    def setUp(self):
        super().setUp()
        fbuf.as_written(True)
        self.addCleanup(fbuf.as_written, False)

    def test_instructions_after_a_jump_are_kept(self):
        top = fbuf.new_label()
        fbuf.place(top)
        fbuf.jump(top)
        fbuf.op(NOP)
        self.assertEqual(code(), bytes([JMP, 0, 0, NOP]))

    def test_a_branch_round_a_jump_stays_two_instructions(self):
        top, skip = fbuf.new_label(), fbuf.new_label()
        fbuf.place(top)
        fbuf.branch(BNE, skip)
        fbuf.jump(top)
        fbuf.place(skip)
        self.assertEqual(code(), bytes([BNE, 3, JMP, 0, 0]))

    def test_a_branch_round_nothing_stays(self):
        skip = fbuf.new_label()
        fbuf.branch(BNE, skip)
        fbuf.place(skip)
        self.assertEqual(code(), bytes([BNE, 0]))

    def test_afterwards_code_is_tidied_again(self):
        fbuf.op(RTS)
        fbuf.as_written(False)
        fbuf.op(NOP)
        self.assertEqual(code(), bytes([RTS]))

    def test_a_new_function_is_not_as_written(self):
        fbuf.begin()
        fbuf.op(RTS)
        fbuf.op(NOP)
        self.assertEqual(code(), bytes([RTS]))


class TailCallTest(FbufTest):
    """A JSR that a return follows becomes a JMP."""

    def test_a_jsr_to_a_fixed_address_becomes_a_jmp(self):
        fbuf.op_word(JSR, 0xF009)
        self.assertTrue(fbuf.tail_call())
        self.assertEqual(code(), bytes([JMP, 0x09, 0xF0]))
        self.assertFalse(fbuf.runs_on())

    def test_a_jsr_to_a_function_becomes_a_jmp_with_the_same_fix_up(self):
        fbuf.op_fix(JSR, fbuf.FIX_ADDRESS, 3, 0xFF, 0)
        self.assertTrue(fbuf.tail_call())
        self.assertEqual(code(), bytes([JMP, 0, 0]))
        self.assertEqual(fixups(), [(1, 1, 3, 0xFF, 0)])

    def test_anything_else_is_left_alone(self):
        self.assertFalse(fbuf.tail_call())
        fbuf.op_fix(LDA_ABS, fbuf.FIX_ADDRESS, 3, 0xFF, 0)
        self.assertFalse(fbuf.tail_call())
        fbuf.op_byte(LDA_IMM, JSR)
        self.assertFalse(fbuf.tail_call())

    def test_a_label_after_the_jsr_keeps_it(self):
        fbuf.op_word(JSR, 0xF009)
        fbuf.place(fbuf.new_label())
        self.assertFalse(fbuf.tail_call())

    def test_a_jsr_that_was_kept_as_written_stays_a_jsr(self):
        fbuf.op_fix(JSR, fbuf.FIX_ADDRESS, 3, 0xFF, 0)
        fbuf.keep_as_written()
        self.assertFalse(fbuf.tail_call())
        self.assertEqual(code(), bytes([JSR, 0, 0]))

    def test_only_the_instruction_kept_is_kept(self):
        fbuf.op_fix(JSR, fbuf.FIX_ADDRESS, 3, 0xFF, 0)
        fbuf.keep_as_written()
        fbuf.op_word(JSR, 0xF009)
        self.assertTrue(fbuf.tail_call())

    def test_a_new_function_keeps_nothing(self):
        fbuf.op_word(JSR, 0xF009)
        fbuf.keep_as_written()
        fbuf.begin()
        fbuf.op_word(JSR, 0xF009)
        self.assertTrue(fbuf.tail_call())


class TemporariesTest(FbufTest):
    def test_the_functions_own_temporaries_get_the_slot_numbers_after_its_locals(self):
        fbuf.op_fix(STA_ABS, fbuf.FIX_ADDRESS, OWN, 1, 0)
        fbuf.op_fix(STA_ABS, fbuf.FIX_ADDRESS, OWN, fbuf.FIRST_TEMP, 0)
        fbuf.op_fix(STA_ABS, fbuf.FIX_ADDRESS, OWN, fbuf.FIRST_TEMP + 2, 1)
        fbuf.op_fix(STA_ABS, fbuf.FIX_ADDRESS, 9, fbuf.FIRST_TEMP, 0)       # another function's slot
        fbuf.op_fix(JSR, fbuf.FIX_ADDRESS, OWN, fbuf.NO_SLOT, 0)
        fbuf.finish(OWN, 3)
        self.assertEqual([f[3] for f in fixups()], [1, 3, 5, fbuf.FIRST_TEMP, 0xFF])


class CapacityTest(FbufTest):
    def test_a_function_with_too_much_code_is_error_75(self):
        def fill():
            for _ in range(fbuf.MAX_CODE // 3 + 1):
                fbuf.op_word(JSR, 0xF009)
            fbuf.finish(OWN, 0)
        self.assertFatal(err.E_FUNC_BIG, fill)

    def test_a_function_can_fill_the_buffer(self):
        nops(fbuf.BUFFER_SIZE // 2)
        self.assertEqual(len(code()), fbuf.BUFFER_SIZE // 2)

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
            fbuf.finish(OWN, 0)
        self.assertFatal(err.E_FIXUPS_FULL, fill)

    def test_a_branch_to_a_label_that_was_never_placed_is_a_compiler_error(self):
        def lost():
            fbuf.branch(BEQ, fbuf.new_label())
            fbuf.finish(OWN, 0)
        self.assertFatal(err.E_INTERNAL, lost)


if __name__ == '__main__':
    unittest.main()


class ThreadTest(FbufTest):
    """At the end of the function, a JMP to an RTS becomes an RTS."""

    def test_a_jump_to_a_return_becomes_a_return_whatever_labels_are_between(self):
        done, also, other = fbuf.new_label(), fbuf.new_label(), fbuf.new_label()
        fbuf.branch(BNE, other)
        fbuf.op(NOP)
        fbuf.jump(done)
        fbuf.place(other)
        fbuf.op(NOP)
        fbuf.place(done)
        fbuf.place(also)
        fbuf.op(RTS)
        self.assertEqual(code(), bytes([BNE, 2, NOP, RTS, NOP, RTS]))

    def test_a_backward_jump_to_a_return_too(self):
        back, other = fbuf.new_label(), fbuf.new_label()
        fbuf.branch(BEQ, other)
        fbuf.place(back)
        fbuf.op(RTS)
        fbuf.place(other)
        fbuf.op(NOP)
        fbuf.jump(back)
        self.assertEqual(code(), bytes([BEQ, 1, RTS, NOP, RTS]))

    def test_a_branch_to_a_return_and_a_jump_to_anything_else_stay(self):
        done, loop = fbuf.new_label(), fbuf.new_label()
        fbuf.place(loop)
        fbuf.op(NOP)
        fbuf.branch(BEQ, done)
        fbuf.op(NOP)
        fbuf.jump(loop)
        fbuf.place(done)
        fbuf.op(RTS)
        self.assertEqual(code(), bytes([NOP, BEQ, 4, NOP, JMP, 0, 0, RTS]))

    def test_a_jump_an_asm_block_wrote_stays(self):
        done = fbuf.new_label()
        fbuf.as_written(True)
        fbuf.jump(done)
        fbuf.place(done)
        fbuf.op(RTS)
        fbuf.as_written(False)
        self.assertEqual(code(), bytes([JMP, 0, 0, RTS]))
