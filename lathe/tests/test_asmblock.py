"""asmblock.py: the embedded assembler. The instruction table is checked against asm/pyasm.py,
the repository's work-alike of asm17, which assembles the same lines independently."""
import contextlib
import gc
import io
import os
import sys
import tempfile
import unittest
import warnings
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lathec_support as support  # noqa: E402
import asmblock  # noqa: E402
import decl  # noqa: E402
import err  # noqa: E402
import expr  # noqa: E402
import fbuf  # noqa: E402
import gen  # noqa: E402
import kernel  # noqa: E402
import lex  # noqa: E402
import out  # noqa: E402
import reg  # noqa: E402
import src  # noqa: E402
import typetab  # noqa: E402

sys.path.insert(0, os.path.join(support.LATHE, '..', 'asm'))
import pyasm  # noqa: E402

FILE_NAME = support.TEXT + 0x2000       # where the name errors are reported in goes

MODE_NAMES = ['IMP', 'ACC', 'IMM', 'ZP', 'ZPX', 'ZPY', 'ABS', 'ABSX', 'ABSY', 'INDX', 'INDY', 'IND', 'REL']
# The operand written for each mode, for this assembler and for pyasm.
OPERANDS = {'IMP': ('', ''), 'ACC': (' A', ''), 'IMM': (' #$12', ' #$12'), 'ZP': (' $12', ' $12'),
            'ZPX': (' $12,X', ' $12,X'), 'ZPY': (' $12,Y', ' $12,Y'), 'ABS': (' $1234', ' $1234'),
            'ABSX': (' $1234,X', ' $1234,X'), 'ABSY': (' $1234,Y', ' $1234,Y'),
            'INDX': (' ($12,X)', ' ($12,X)'), 'INDY': (' ($12),Y', ' ($12),Y'),
            'IND': (' ($1234)', ' ($1234)')}


def name(text):
    kernel.name_begin()
    for ch in text:
        kernel.name_add(ch)
    return kernel.name_end()


def mnemonics():
    m = asmblock.MNEMONICS
    return [m[i:i + 3].decode().upper() for i in range(0, len(m), 3)]


def pyasm_bytes(lines):
    """The code pyasm makes of `lines` at $0200, or None if it reports an error."""
    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, 't.asm')
        binary = os.path.join(tmp, 't.bin')
        with open(source, 'w') as f:
            f.write('* = $0200\n' + ''.join('%s\n' % line for line in lines))
        try:
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                pyasm.Assembler(source, binary).run()
        except SystemExit:
            return None                     # (pyasm leaves its source open when it stops)
        with open(binary, 'rb') as f:
            return f.read()


class AsmTest(unittest.TestCase):
    def setUp(self):
        self.start()

    def start(self):
        support.fresh()
        err.init()
        kernel.init()
        typetab.init()
        src.init()
        lex.init()
        out.init()
        gen.init()
        expr.init()
        decl.init()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(support.fresh)          # closes the object file
        self.path = os.path.join(self.tmp.name, 'm.lo')
        pointer, _ = support.put_text(self.path.encode())
        out.open(pointer)
        kernel.module_add(name(b'm'))
        self.own = out.symbol(out.SYM_FUNCTION, name(b'm'), 0, name(b'f'))

    def assemble(self, text, before=None):
        """Assemble `text` (bytes, its lines) as an asm block that is a function's whole body.
        The block's first line is line 2. Returns the code; the fix-ups are in self.fixups and
        the calls noted in self.calls."""
        start, stop = support.put_text(b'asm\n' + text + b'end\n')
        src.open_memory(start, stop)
        support.put_text(b't.lth', FILE_NAME)
        err.set_file(FILE_NAME)
        lex.next()
        self.assertEqual(lex.tok, lex.T_ASM)
        gen.function_begin(self.own)
        if before:
            before()
        asmblock.block()
        self.assertEqual(lex.tok, lex.T_NL)
        self.calls = [out.call_callee[i] for i in range(out.call_count)]
        self.after_block()
        gen.function_end(0)
        self.fixups = [(fbuf.fix_offset[i], fbuf.fix_kind[i], fbuf.fix_symbol[i], fbuf.fix_slot[i],
                        fbuf.fix_addend[i]) for i in range(fbuf.fix_count)]
        return bytes(fbuf.code[i] for i in range(fbuf.code_length))

    def after_block(self):
        pass

    def fails(self, text, number, line, col):
        before = len(support.error_text())
        with self.assertRaises(SystemExit):
            self.assemble(text)
        reported = support.error_text()[before:]
        self.assertTrue(reported.startswith('t.lth:%d:%d: error %d: ' % (line, col, number)), reported)
        src.init()                              # what the failed block left open
        for stream in range(kernel.MAX_STREAMS):
            if kernel.stream_kind[stream] == kernel.STREAM_MEMORY:
                kernel.stream_kind[stream] = kernel.STREAM_FREE

    def function(self, text, extern_at=None):
        s = kernel.sym_add(kernel.SCOPE_MODULE, name(text), kernel.K_FUNC)
        if extern_at is not None:
            kernel.sym_flags[s] = kernel.SF_EXTERN
            kernel.sym_value[s] = extern_at
        return s

    def constant(self, text, value):
        s = kernel.sym_add(kernel.SCOPE_MODULE, name(text), kernel.K_CONST)
        kernel.sym_type[s] = typetab.NUMBER_TYPE
        kernel.sym_value[s] = value


class TableTest(AsmTest):
    def test_there_are_56_mnemonics_each_with_a_base_and_a_class(self):
        self.assertEqual(len(mnemonics()), 56)
        self.assertEqual(asmblock.NMOS_COUNT, 56)
        self.assertEqual(len(asmblock.BASE), 56)
        self.assertEqual(len(asmblock.CLASS), 56)
        self.assertEqual(len(set(mnemonics())), 56)
        self.assertEqual(len(asmblock.MODE_OFFSET) % asmblock.MODES, 0)
        self.assertEqual(len(asmblock.MODE_OFFSET) // asmblock.MODES, max(asmblock.CLASS) + 1)

    def test_every_mnemonic_in_every_mode_assembles_as_pyasm_assembles_it(self):
        """For each mnemonic and each mode with a written form, pyasm and this assembler
        either both reject the line or give the same bytes. Branches are compared in their
        one mode. The opcodes of the modes the table claims cover all 151 of the NMOS 6502."""
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', ResourceWarning)
            claimed, mismatches = self.compare_with_pyasm()
            gc.collect()
        self.assertEqual(mismatches, [])
        self.assertEqual(len(claimed), 151)

    def compare_with_pyasm(self):
        claimed = set()
        mismatches = []
        for m, mnemonic in enumerate(mnemonics()):
            branch = asmblock.has_mode(m, asmblock.M_REL)
            for mode, mode_name in enumerate(MODE_NAMES):
                if branch != (mode_name == 'REL'):
                    continue
                if mode_name == 'REL':
                    ours = b'.back\n  ' + mnemonic.encode() + b' .back\n'
                    theirs = pyasm_bytes(['back:', '  ' + mnemonic + ' back'])
                else:
                    mine, other = OPERANDS[mode_name]
                    ours = ('  %s%s\n' % (mnemonic, mine)).encode()
                    theirs = pyasm_bytes(['  %s%s' % (mnemonic, other)])
                    if mode_name == 'ACC' and asmblock.has_mode(m, asmblock.M_IMP):
                        theirs = None       # pyasm writes the accumulator mode bare, like implied
                self.start()
                try:
                    with contextlib.redirect_stderr(io.StringIO()):
                        got = self.assemble(ours)
                except SystemExit:
                    got = None
                if theirs is not None and mnemonic not in ('JMP', 'RTS', 'RTI'):
                    theirs += b'\x60'       # the RTS the function ends with
                if got != theirs:
                    mismatches.append((mnemonic, mode_name, got, theirs))
                if asmblock.has_mode(m, mode):
                    claimed.add(asmblock.opcode(m, mode)[0])
                    if got is None:
                        mismatches.append((mnemonic, mode_name, 'claimed but rejected'))
        return claimed, mismatches

    def test_bare_shift_and_shift_a_are_both_the_accumulator_form(self):
        self.assertEqual(self.assemble(b'  ASL\n  lsr a\n  ROL A ; comment\n'), b'\x0a\x4a\x2a\x60')

    def test_branches_have_no_other_mode(self):
        self.fails(b'  BNE $12\n', err.E_ASM_BRANCH, 2, 7)


class LineTest(AsmTest):
    def test_blank_and_comment_lines_are_skipped_and_case_does_not_matter(self):
        self.assertEqual(self.assemble(b'\n  ; nothing\n\t\n  lDa #1\n  Rts\n'), b'\xa9\x01\x60')

    def test_the_block_ends_at_a_line_whose_first_word_is_end_in_any_case(self):
        start, stop = support.put_text(b'asm\n  NOP\n  END ; done\nreturn\n')
        src.open_memory(start, stop)
        lex.next()
        gen.function_begin(self.own)
        asmblock.block()
        self.assertEqual(lex.tok, lex.T_NL)
        lex.next()
        self.assertEqual(lex.tok, lex.T_RETURN)

    def test_the_end_is_given_back_to_lex_with_its_place(self):
        start, stop = support.put_text(b'asm\n  NOP\n    end x\n')
        src.open_memory(start, stop)
        lex.next()
        gen.function_begin(self.own)
        asmblock.block()
        self.assertEqual((lex.tok, lex.line), (lex.T_NAME, 3))

    def test_no_end_is_error_30(self):
        start, stop = support.put_text(b'asm\n  NOP\n')
        src.open_memory(start, stop)
        lex.next()
        gen.function_begin(self.own)
        with self.assertRaises(SystemExit):
            asmblock.block()
        self.assertIn('error 30:', support.error_text())

    def test_text_after_asm_is_error_22(self):
        start, stop = support.put_text(b'asm NOP\nend\n')
        src.open_memory(start, stop)
        lex.next()
        gen.function_begin(self.own)
        with self.assertRaises(SystemExit):
            asmblock.block()
        self.assertIn('error 22:', support.error_text())

    def test_text_after_an_operand_is_error_22(self):
        self.fails(b'  LDA #1 2\n', err.E_NL_EXPECTED, 2, 10)

    def test_an_unknown_mnemonic_is_error_146_at_the_word(self):
        self.fails(b'  NOP\n   LDQ #1\n', err.E_ASM_MNEMONIC, 3, 4)
        self.fails(b'  foo: NOP\n', err.E_ASM_MNEMONIC, 2, 3)
        self.fails(b'  * = $1000\n', err.E_ASM_MNEMONIC, 2, 3)

    def test_a_directive_is_error_145(self):
        self.fails(b'  .byte 1, 2\n', err.E_ASM_DIRECTIVE, 2, 3)
        self.fails(b'  .word label\n', err.E_ASM_DIRECTIVE, 2, 3)

    def test_registers_are_forgotten_after_the_block(self):
        code = self.assemble(b'  TAX\n', before=lambda: reg.load_const(reg.A, 5))
        self.assertEqual(code, b'\xa9\x05\xaa\xa9\x05\x60')

    def after_block(self):
        if self._testMethodName == 'test_registers_are_forgotten_after_the_block':
            reg.load_const(reg.A, 5)


class OperandTest(AsmTest):
    def test_numbers_in_every_base_and_characters(self):
        self.assertEqual(self.assemble(b'  LDA #$1f\n  LDA #%101\n  LDA #10\n  LDA #\'A\'\n'),
                         b'\xa9\x1f\xa9\x05\xa9\x0a\xa9\x41\x60')

    def test_an_expression_adds_and_subtracts_numbers_from_left_to_right(self):
        self.assertEqual(self.assemble(b'  LDA #$10 + 2 - $01\n  STA $D000+$20\n'),
                         b'\xa9\x11\x8d\x20\xd0\x60')

    def test_selectors_take_the_low_or_high_byte_of_the_whole_expression(self):
        self.assertEqual(self.assemble(b'  LDA #<$1234+1\n  LDX #>$12FF+1\n'), b'\xa9\x35\xa2\x13\x60')

    def test_a_numeric_address_below_256_takes_the_zero_page_form(self):
        self.assertEqual(self.assemble(b'  LDA $FF\n  LDA $100\n  LDA $0012,X\n  LDA $12,Y\n'),
                         b'\xa5\xff\xad\x00\x01\xb5\x12\xb9\x12\x00\x60')

    def test_jsr_and_jmp_always_take_the_absolute_form(self):
        self.assertEqual(self.assemble(b'  JSR $12\n  JMP $34\n'), b'\x20\x12\x00\x4c\x34\x00')

    def test_spaces_are_allowed_inside_operands(self):
        self.assertEqual(self.assemble(b'  LDA ( $12 ) , y\n  STA ( $10 , x )\n  LDA $20 , X\n'),
                         b'\xb1\x12\x81\x10\xb5\x20\x60')

    def test_a_constant_is_its_value(self):
        self.constant(b'border', 0xD020)
        self.constant(b'seven', 7)
        self.assertEqual(self.assemble(b'  LDA #seven+1\n  STA border\n  STA seven\n  LDA #<BORDER\n'),
                         b'\xa9\x08\x8d\x20\xd0\x85\x07\xa9\x20\x60')

    def test_an_extern_function_is_its_address(self):
        self.function(b'put', 0xF009)
        self.assertEqual(self.assemble(b'  JSR put\n  LDA #>put\n'), b'\x20\x09\xf0\xa9\xf0\x60')
        self.assertEqual(self.calls, [])

    def test_a_function_is_its_entry_through_a_fix_up_and_a_call_is_noted(self):
        self.function(b'g')
        code = self.assemble(b'  JSR g\n  LDA #<g+1\n  LDX #>g\n  JMP g\n')
        self.assertEqual(code, b'\x20\x00\x00\xa9\x00\xa2\x00\x4c\x00\x00')
        g = 1                                   # the SYM record after the function's own
        self.assertEqual(self.fixups, [(1, 1, g, 0xFF, 0), (4, 2, g, 0xFF, 1), (6, 3, g, 0xFF, 0),
                                       (8, 1, g, 0xFF, 0)])
        self.assertEqual(self.calls, [g])

    def test_a_function_of_another_module(self):
        kernel.module_add(name(b'util'))
        s = kernel.sym_add(kernel.SCOPE_MODULE, name(b'util'), kernel.K_MODULE)
        kernel.sym_value[s] = 1
        kernel.sym_add(1, name(b'go'), kernel.K_FUNC)
        self.assertEqual(self.assemble(b'  JSR util.go\n'), b'\x20\x00\x00\x60')
        self.assertEqual(self.fixups, [(1, 1, 1, 0xFF, 0)])

    def test_a_function_cannot_be_in_zero_page(self):
        self.function(b'g')
        self.fails(b'  LDA (g),Y\n', err.E_ASM_RANGE, 2, 8)

    def test_an_address_needs_a_selector_in_an_immediate(self):
        self.function(b'g')
        self.fails(b'  LDA #g\n', err.E_ASM_RANGE, 2, 8)

    def test_an_undefined_name_is_error_40(self):
        self.fails(b'  LDA nothing\n', err.E_UNDEFINED, 2, 7)
        self.fails(b'  LDA #<nothing\n', err.E_UNDEFINED, 2, 9)

    def test_operands_out_of_range_are_error_143(self):
        self.fails(b'  LDA #$100\n', err.E_ASM_RANGE, 2, 8)
        self.fails(b'  LDA ($100),Y\n', err.E_ASM_RANGE, 2, 8)
        self.fails(b'  STX $1234,Y\n', err.E_ASM_RANGE, 2, 7)
        self.fails(b'  LDA $FFFF+1\n', err.E_ASM_RANGE, 2, 7)
        self.fails(b'  LDA 1-2\n', err.E_ASM_RANGE, 2, 7)

    def test_a_mode_the_instruction_lacks_is_error_144(self):
        self.fails(b'  STA #1\n', err.E_ASM_MODE, 2, 7)
        self.fails(b'  LDA\n', err.E_ASM_MODE, 2, 6)
        self.fails(b'  JMP ($12),Y\n', err.E_ASM_MODE, 2, 8)
        self.fails(b'  LDA ($12,Y)\n', err.E_ASM_MODE, 2, 8)
        self.fails(b'  INX $12\n', err.E_ASM_MODE, 2, 7)


class LabelTest(AsmTest):
    def test_a_backward_branch(self):
        self.assertEqual(self.assemble(b'.loop\n  DEX\n  BNE .loop\n'), b'\xca\xd0\xfd\x60')

    def test_a_forward_branch_and_a_label_with_a_colon_before_an_instruction(self):
        self.assertEqual(self.assemble(b'  BCC .done\n  INX\n.done: RTS\n'), b'\x90\x01\xe8\x60')

    def test_a_label_without_a_colon_before_an_instruction(self):
        self.assertEqual(self.assemble(b'  BEQ .x\n.x INX\n'), b'\xf0\x00\xe8\x60')

    def test_jmp_to_a_label_is_a_fix_up_of_the_function_and_the_offset(self):
        code = self.assemble(b'.top\n  INX\n  JMP .top\n')
        self.assertEqual(code, b'\xe8\x4c\x00\x00')
        self.assertEqual(self.fixups, [(2, 1, self.own, 0xFF, 0)])

    def test_a_branch_that_does_not_reach_is_widened(self):
        nops = b'  NOP\n' * 130
        code = self.assemble(b'.back\n' + nops + b'  BNE .back\n  BEQ .ahead\n' + nops + b'.ahead\n')
        self.assertEqual(code[130:135], b'\xf0\x03\x4c\x00\x00')
        self.assertEqual(code[135:140], b'\xd0\x03\x4c\x00\x00')
        self.assertEqual(self.fixups, [(133, 1, self.own, 0xFF, 0), (138, 1, self.own, 0xFF, 270)])

    def test_labels_are_local_to_their_block(self):
        start, stop = support.put_text(b'asm\n.a\n  BNE .a\nend\nasm\n.a\n  BNE .a\nend\n')
        src.open_memory(start, stop)
        lex.next()
        gen.function_begin(self.own)
        asmblock.block()
        lex.next()
        asmblock.block()
        gen.function_end(0)
        self.assertEqual(bytes(fbuf.code[:fbuf.code_length]), b'\xd0\xfe\xd0\xfe\x60')

    def test_an_undefined_label_is_error_142_at_its_first_use(self):
        self.fails(b'  NOP\n  BNE .gone\n  BEQ .gone\n', err.E_ASM_NO_LABEL, 3, 7)

    def test_a_label_defined_twice_is_error_41(self):
        self.fails(b'.a\n  NOP\n .a: NOP\n', err.E_DUPLICATE, 4, 2)

    def test_a_branch_to_anything_but_a_label_of_the_block_is_error_140(self):
        self.function(b'g')
        self.fails(b'  BNE g\n', err.E_ASM_BRANCH, 2, 7)
        self.fails(b'  BNE $0200\n', err.E_ASM_BRANCH, 2, 7)

    def test_a_label_used_other_than_by_a_branch_or_jmp_is_error_141(self):
        self.fails(b'.a\n  LDA .a\n', err.E_ASM_LABEL_USE, 3, 7)
        self.fails(b'.a\n  JSR .a\n', err.E_ASM_LABEL_USE, 3, 7)
        self.fails(b'.a\n  LDA #<.a\n', err.E_ASM_LABEL_USE, 3, 9)
        self.fails(b'.a\n  JMP .a+1\n', err.E_ASM_LABEL_USE, 3, 7)
        self.fails(b'.a\n  JMP (.a)\n', err.E_ASM_LABEL_USE, 3, 8)


class StorageTest(AsmTest):
    """How instructions use variables and slots, through test doubles of name_operand() and
    storage_used(), so that only the instruction forms are checked here (TablesTest has the
    real ones). `v` is a module-level variable, symbol 7; `s` is slot 2 of the function."""
    VAR_SYMBOL = 7
    VAR_STORAGE = 30
    SLOT_STORAGE = 31

    def setUp(self):
        super().setUp()
        self.uses = []
        patcher = mock.patch.object(asmblock, 'name_operand', self.fake_name_operand)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(asmblock, 'storage_used', lambda s, zp: self.uses.append((s, zp)))
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake_name_operand(self, n, member):
        asmblock.found_function = False
        if n == name(b'v'):
            asmblock.found_symbol = self.VAR_SYMBOL
            asmblock.found_slot = fbuf.NO_SLOT
            asmblock.found_storage = self.VAR_STORAGE
        elif n == name(b's'):
            asmblock.found_symbol = self.own
            asmblock.found_slot = 2
            asmblock.found_storage = self.SLOT_STORAGE
        else:
            err.fatal(err.E_UNDEFINED)
        return asmblock.X_ADDRESS

    def test_a_variable_is_written_absolute_with_a_two_byte_fix_up_and_counts_a_use(self):
        code = self.assemble(b'  LDA v\n  STA v+1,X\n  LDA v,Y\n')
        self.assertEqual(code, b'\xad\x00\x00\x9d\x00\x00\xb9\x00\x00\x60')
        self.assertEqual(self.fixups, [(1, 1, 7, 0xFF, 0), (4, 1, 7, 0xFF, 1), (7, 1, 7, 0xFF, 0)])
        self.assertEqual(self.uses, [(30, False)] * 3)

    def test_a_slot_is_its_function_and_number(self):
        code = self.assemble(b'  INC s\n  LDX s+1,Y\n')
        self.assertEqual(code, b'\xee\x00\x00\xbe\x00\x00\x60')
        self.assertEqual(self.fixups, [(1, 1, self.own, 2, 0), (4, 1, self.own, 2, 1)])
        self.assertEqual(self.uses, [(31, False)] * 2)

    def test_the_indirect_modes_are_zero_page_fix_ups_and_need_zero_page(self):
        code = self.assemble(b'  LDA (v),Y\n  STA (s+2,X)\n')
        self.assertEqual(code, b'\xb1\x00\x81\x00\x60')
        self.assertEqual(self.fixups, [(1, 4, 7, 0xFF, 0), (3, 4, self.own, 2, 2)])
        self.assertEqual(self.uses, [(30, True), (31, True)])

    def test_stx_zp_y_has_only_a_zero_page_form(self):
        code = self.assemble(b'  STX v,Y\n  STY s,X\n')
        self.assertEqual(code, b'\x96\x00\x94\x00\x60')
        self.assertEqual(self.fixups, [(1, 4, 7, 0xFF, 0), (3, 4, self.own, 2, 0)])
        self.assertEqual(self.uses, [(30, True), (31, True)])

    def test_immediates_of_an_address_are_its_low_and_high_byte(self):
        code = self.assemble(b'  LDA #<v\n  LDX #>s+1\n')
        self.assertEqual(code, b'\xa9\x00\xa2\x00\x60')
        self.assertEqual(self.fixups, [(1, 2, 7, 0xFF, 0), (3, 3, self.own, 2, 1)])
        self.assertEqual(self.uses, [])

    def test_jmp_indirect_through_a_variable_is_absolute(self):
        code = self.assemble(b'  JMP (v)\n')
        self.assertEqual(code, b'\x6c\x00\x00')
        self.assertEqual(self.fixups, [(1, 1, 7, 0xFF, 0)])
        self.assertEqual(self.uses, [(30, False)])

    def test_jsr_to_a_variable_is_not_a_call(self):
        self.assemble(b'  JSR v\n')
        self.assertEqual(self.calls, [])

    def test_a_named_a_is_a_variable_where_there_is_no_accumulator_mode(self):
        with self.assertRaises(SystemExit):
            self.assemble(b'  LDA a\n')
        self.assertIn('error 40:', support.error_text())


class NameOperandTest(AsmTest):
    """The real name_operand(), on constants, functions and modules."""

    def test_a_constant(self):
        self.constant(b'k', 0x1234)
        self.assertEqual(asmblock.name_operand(name(b'k'), 0), asmblock.X_NUMBER)
        self.assertEqual(asmblock.found_value, 0x1234)

    def test_true_and_false_are_constants(self):
        self.assertEqual(asmblock.name_operand(name(b'true'), 0), asmblock.X_NUMBER)
        self.assertEqual(asmblock.found_value, 1)

    def test_a_function(self):
        self.function(b'g')
        self.assertEqual(asmblock.name_operand(name(b'g'), 0), asmblock.X_ADDRESS)
        self.assertEqual((asmblock.found_symbol, asmblock.found_slot, asmblock.found_storage,
                          asmblock.found_function), (1, fbuf.NO_SLOT, asmblock.NO_STORAGE, True))

    def test_a_module_needs_a_member(self):
        kernel.module_add(name(b'util'))
        s = kernel.sym_add(kernel.SCOPE_MODULE, name(b'util'), kernel.K_MODULE)
        kernel.sym_value[s] = 1
        with self.assertRaises(SystemExit):
            asmblock.name_operand(name(b'util'), 0)
        self.assertIn('error 36:', support.error_text())


class TablesTest(AsmTest):
    """name_operand() and storage_used() on the real symbol table and frame: module-level,
    `static` and imported variables, parameters and locals, through stage 2a's columns."""

    def variable(self, text, flags=0, scope=kernel.SCOPE_MODULE, inner=0):
        s = kernel.sym_add(scope, name(text), kernel.K_VAR)
        kernel.sym_type[s] = typetab.WORD_TYPE
        kernel.sym_flags[s] = flags
        if flags & kernel.SF_AT == 0:
            kernel.sym_obj[s] = out.symbol(out.SYM_VARIABLE, name(b'm'), inner, name(text))
        return s

    def slot(self, text, zp_class=reg.CLASS_EITHER, kind=reg.SLOT_LOCAL):
        """A slot of the function, made once its frame has begun (from assemble's `before`)."""
        s = kernel.sym_add(kernel.SCOPE_LOCAL, name(text), kernel.K_LOCAL)
        kernel.sym_type[s] = typetab.WORD_TYPE
        kernel.sym_value[s] = reg.new_slot(2, zp_class, kind, name(text))
        return s

    def imported(self, text, flags=0):
        kernel.module_add(name(b'util'))
        u = kernel.sym_add(kernel.SCOPE_MODULE, name(b'util'), kernel.K_MODULE)
        kernel.sym_value[u] = 1
        s = kernel.sym_add(1, name(text), kernel.K_VAR)
        kernel.sym_type[s] = typetab.BYTE_TYPE
        kernel.sym_flags[s] = flags
        return s

    def test_a_module_variable_is_its_symbol_through_a_two_byte_fix_up(self):
        v = self.variable(b'v')
        code = self.assemble(b'  LDA v\n  STA v+1\n')
        self.assertEqual(code, b'\xad\x00\x00\x8d\x00\x00\x60')
        self.assertEqual(self.fixups, [(1, 1, kernel.sym_obj[v], fbuf.NO_SLOT, 0),
                                       (4, 1, kernel.sym_obj[v], fbuf.NO_SLOT, 1)])
        self.assertEqual(kernel.sym_weight[v], 2)
        self.assertEqual(kernel.sym_flags[v] & kernel.SF_ZP, 0)

    def test_name_operand_finds_a_variable_and_storage_used_counts_it(self):
        v = self.variable(b'v')
        self.assertEqual(asmblock.name_operand(name(b'v'), 0), asmblock.X_ADDRESS)
        self.assertEqual((asmblock.found_symbol, asmblock.found_slot, asmblock.found_function),
                         (kernel.sym_obj[v], fbuf.NO_SLOT, False))
        self.assertNotEqual(asmblock.found_storage, asmblock.NO_STORAGE)
        asmblock.storage_used(asmblock.found_storage, False)
        self.assertEqual(kernel.sym_weight[v], 1)
        asmblock.storage_used(asmblock.found_storage, True)
        self.assertEqual(kernel.sym_weight[v], 2)
        self.assertNotEqual(kernel.sym_flags[v] & kernel.SF_ZP, 0)

    def test_an_indirect_mode_makes_a_module_variable_class_0(self):
        v = self.variable(b'v')
        code = self.assemble(b'  LDA (v),Y\n')
        self.assertEqual(code, b'\xb1\x00\x60')
        self.assertEqual(self.fixups, [(1, 4, kernel.sym_obj[v], fbuf.NO_SLOT, 0)])
        self.assertNotEqual(kernel.sym_flags[v] & kernel.SF_ZP, 0)

    def test_a_static_variable_is_its_own_symbol(self):
        code = self.assemble(b'  INC st\n', before=self.make_static)
        self.assertEqual(code, b'\xee\x00\x00\x60')
        self.assertEqual(self.fixups, [(1, 1, self.static_obj, fbuf.NO_SLOT, 0)])

    def make_static(self):
        kernel.scope_begin()
        s = self.variable(b'st', 0, kernel.SCOPE_LOCAL, name(b'f'))
        self.static_obj = kernel.sym_obj[s]

    def test_a_variable_at_a_fixed_address_is_its_address(self):
        v = self.variable(b'hw', kernel.SF_AT)
        kernel.sym_value[v] = 0x0080
        self.assertEqual(self.assemble(b'  LDA hw+1\n  STA (hw),Y\n'), b'\xa5\x81\x91\x80\x60')
        self.assertEqual(self.fixups, [])

    def test_a_parameter_and_a_local_are_slots_of_the_function(self):
        def frame():
            kernel.scope_begin()
            self.p = self.slot(b'p', reg.CLASS_EITHER, reg.SLOT_PARAMETER)
            self.q = self.slot(b'q')
        code = self.assemble(b'  LDA p\n  STA q+1\n', before=frame)
        self.assertEqual(code, b'\xad\x00\x00\x8d\x00\x00\x60')
        self.assertEqual(self.fixups, [(1, 1, self.own, 0, 0), (4, 1, self.own, 1, 1)])
        self.assertEqual((reg.slot_weight[0], reg.slot_weight[1]), (1, 1))
        self.assertEqual((reg.slot_class[0], reg.slot_class[1]), (reg.CLASS_EITHER, reg.CLASS_EITHER))

    def test_a_zero_page_only_instruction_makes_a_slot_class_0(self):
        def frame():
            kernel.scope_begin()
            self.slot(b'p')
        code = self.assemble(b'  STX p,Y\n  LDA (p),Y\n', before=frame)
        self.assertEqual(code, b'\x96\x00\xb1\x00\x60')
        self.assertEqual(self.fixups, [(1, 4, self.own, 0, 0), (3, 4, self.own, 0, 0)])
        self.assertEqual(reg.slot_class[0], reg.CLASS_ZP)

    def test_a_use_inside_loops_weighs_as_compiled_code_does(self):
        def frame():
            kernel.scope_begin()
            self.slot(b'p')
            reg.loop_depth = 2
        self.assemble(b'  LDA p\n  LDA p\n', before=frame)
        self.assertEqual(reg.slot_weight[0], 2 * reg.WEIGHTS[2])

    def test_weights_stop_at_255(self):
        v = self.variable(b'v')
        kernel.sym_weight[v] = 250
        self.assemble(b'  LDA v\n  LDA v\n  LDA v\n  LDA v\n  LDA v\n  LDA v\n')
        self.assertEqual(kernel.sym_weight[v], 255)

    def test_a_variable_of_another_module_is_its_symbol(self):
        self.imported(b'w')
        code = self.assemble(b'  LDA util.w\n  STA util.w+1\n')
        self.assertEqual(code, b'\xad\x00\x00\x8d\x00\x00\x60')
        self.assertEqual([f[1:] for f in self.fixups], [(1, 1, fbuf.NO_SLOT, 0), (1, 1, fbuf.NO_SLOT, 1)])
        self.assertEqual(self.fixups[0][2], self.fixups[1][2])

    def test_a_variable_of_another_module_declared_zp_can_be_used_indirectly(self):
        self.imported(b'w', kernel.SF_ZP)
        self.assertEqual(self.assemble(b'  LDA (util.w),Y\n'), b'\xb1\x00\x60')
        self.assertEqual(self.fixups[0][1], 4)

    def test_a_variable_of_another_module_not_zp_cannot_be_made_class_0(self):
        self.imported(b'w')
        self.fails(b'  LDA (util.w),Y\n', err.E_ASM_NOT_ZP, 2, 8)

    def test_a_nozp_variable_cannot_be_made_class_0(self):
        self.variable(b'v', kernel.SF_NOZP)
        self.fails(b'  NOP\n  LDA (v),Y\n', err.E_ASM_NOT_ZP, 3, 8)

    def test_a_nozp_slot_cannot_be_made_class_0(self):
        def frame():
            kernel.scope_begin()
            self.slot(b'p', reg.CLASS_NOT_ZP)
        before = len(support.error_text())
        with self.assertRaises(SystemExit):
            self.assemble(b'  STY p,X\n', before=frame)
        self.assertIn('t.lth:2:7: error %d: ' % err.E_ASM_NOT_ZP, support.error_text()[before:])

    def test_a_variable_used_as_a_function_is_not_a_call(self):
        self.variable(b'v')
        self.assemble(b'  JMP (v)\n  JSR v\n')
        self.assertEqual(self.calls, [])


class AsmFunctionFileTest(unittest.TestCase):
    """An asm function as lathec writes it: FUNC flags and the interface entry."""
    LIB = os.path.join(support.CASES, 'snap', 'asm_lib.lth')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.assertEqual(support.run_lathec(self.LIB, self.tmp.name), (0, ''))

    def test_its_func_record_has_the_registers_flag(self):
        funcs = [body for kind, body in support.records(os.path.join(self.tmp.name, 'asm_lib.lo'))
                 if kind == 7]
        self.assertEqual(funcs, [b'\x00\x00' + bytes([out.FUNC_EXPORTED | out.FUNC_REGISTERS])])

    def test_its_interface_entry_has_the_asm_flag_and_the_registers(self):
        with open(os.path.join(self.tmp.name, 'asm_lib.li'), 'rb') as f:
            li = f.read()
        self.assertEqual(li, b'LI\x01\x07asm_lib' + b'\x01\x05twice' + bytes([decl.LI_ASM])
                         + b'\x01\x01\x01' + b'\x02\x01\x01\x05\x07' + b'\x00')


if __name__ == '__main__':
    unittest.main()
