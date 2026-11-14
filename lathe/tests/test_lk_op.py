"""The linker's opcode tables against the object tools' own (lathe/host/driver/cpu6502.py),
which were written separately from the same CPU.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'host'))
sys.path.insert(0, os.path.join(HERE, '..', 'host', 'driver'))
import cpu6502  # noqa: E402
import lk_op  # noqa: E402


class OpcodeTables(unittest.TestCase):
    def test_tables_cover_every_opcode(self):
        self.assertEqual((len(lk_op.OP_LEN), len(lk_op.ZP_FORM)), (256, 256))
        self.assertTrue(all(1 <= n <= 3 for n in lk_op.OP_LEN))

    def test_lengths_of_the_nmos_instructions(self):
        for op, (mnemonic, mode) in cpu6502.decode_table(cpu6502.CPU_6502).items():
            self.assertEqual(lk_op.length(op), 1 + cpu6502.OPERAND_BYTES[mode], '%s %s' % (mnemonic, mode))

    def test_zero_page_forms_of_the_nmos_instructions(self):
        table = cpu6502.table(cpu6502.CPU_6502)
        shrinkable = 0
        for op, (mnemonic, mode) in cpu6502.decode_table(cpu6502.CPU_6502).items():
            zp_mode = cpu6502.shrinks(cpu6502.CPU_6502, mnemonic, mode)
            form, has_one = lk_op.zp_opcode(op, lk_op.CPU_6502)
            if zp_mode is None:
                self.assertFalse(has_one, '%s %s' % (mnemonic, mode))
            else:
                shrinkable += 1
                self.assertEqual((form, has_one), (table[mnemonic][zp_mode], True), '%s %s' % (mnemonic, mode))
        self.assertEqual(shrinkable, 37)

    def test_nothing_else_shrinks_on_an_nmos_cpu(self):
        known = cpu6502.decode_table(cpu6502.CPU_6502)
        for op in range(256):
            if op not in known:
                self.assertEqual(lk_op.zp_opcode(op, lk_op.CPU_6502), (0, False), hex(op))

    def test_branches(self):
        for op, (mnemonic, mode) in cpu6502.decode_table(cpu6502.CPU_6502).items():
            self.assertEqual(lk_op.is_branch(op, lk_op.CPU_6502), mode == cpu6502.REL, mnemonic)

    def test_65c02_additions(self):
        c02 = lk_op.CPU_65C02
        self.assertEqual([lk_op.zp_opcode(op, c02) for op in (0x9C, 0x9E, 0x0C, 0x1C, 0x3C)],
                         [(0x64, True), (0x74, True), (0x04, True), (0x14, True), (0x34, True)])
        self.assertEqual(lk_op.zp_opcode(0x7C, c02), (0, False))            # JMP (abs,X)
        self.assertTrue(lk_op.is_branch(0x80, c02) and lk_op.is_branch(0x0F, c02))
        self.assertFalse(lk_op.is_branch(0x80, lk_op.CPU_6502))
        # BBR is three bytes, the one-byte NOPs one, (zp) two
        self.assertEqual([lk_op.length(op) for op in (0x0F, 0x03, 0xB2, 0x80, 0x7C)], [3, 1, 2, 2, 3])


if __name__ == '__main__':
    unittest.main()
