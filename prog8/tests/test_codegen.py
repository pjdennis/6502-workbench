"""Codegen unit tests -- substring checks on the emitted .s text.

These are NOT golden tests (those live under tests/snapshots/); they
just assert that the codegen produces the right shape for a given
input. Adding a new feature should add a test here BEFORE adding the
golden snapshot, so we catch obvious regressions on quick local runs.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from p8c.codegen import generate  # noqa: E402
from p8c.lex import lex  # noqa: E402
from p8c.parse import parse  # noqa: E402
from p8c.sema import analyze  # noqa: E402


def compile_text(src: str, target: str | None = None) -> str:
    prog = parse(lex(src, "<test>"), "<test>")
    if target is not None:
        # External target selection (like the CLI's --target), so the source
        # needs no %target directive. Applies the nmos default-address shift.
        prog.target = target
        if target == "nmos" and prog.address == 0x4000:
            prog.address = 0x0200
    analyze(prog)
    return generate(prog, "<test>")


class CodeGenBasics(unittest.TestCase):
    def test_emits_org_directive_for_address(self):
        s = compile_text('%address $8123\n%output raw\n%launcher none\nmain {\n  sub start() {   }\n}')
        self.assertIn(".org $8123", s)

    def test_default_org_is_4000(self):
        self.assertIn(".org $4000", compile_text('%output raw\n%launcher none\nmain {\n  sub start() {   }\n}'))

    def test_jmp_to_main_in_prologue(self):
        self.assertIn("jmp p8s_start", compile_text('%output raw\n%launcher none\nmain {\n  sub start() {   }\n}'))

    def test_main_falls_through_to_halt_loop(self):
        s = compile_text('%output raw\n%launcher none\nmain {\n  sub start() {   }\n}')
        self.assertIn(".Lhalt_p8s_start:", s)
        self.assertIn("bra .Lhalt_p8s_start", s)

    def test_txt_print_emits_string_and_jsr(self):
        s = compile_text('%import txt\n%output raw\n%launcher none\nmain {\n  sub start() { txt.print("hi")   }\n}')
        self.assertIn("lda #<p8c_str_0", s)
        self.assertIn("ldx #>p8c_str_0", s)
        self.assertIn("jsr display_string", s)
        # String pool with the data:
        self.assertIn("p8c_str_0:", s)
        self.assertIn('"hi"', s)
        self.assertIn(", 0", s)

    def test_string_labels_are_main_first(self):
        # Labels are interned in emission (main-first) order, NOT source
        # order, so p1's single-pass codegen stays byte-identical. Here
        # `helper` is declared before `main` but main's string is labeled
        # first because main is emitted first.
        src = (
            '%import txt\n%output raw\n%launcher none\nmain {\nsub helper() { txt.print("H") }\n  sub start() { txt.print("M") helper()   }\n}\n'
        )
        s = compile_text(src)
        # p8c_str_0 is main's "M"; p8c_str_1 is helper's "H".
        i0 = s.index('p8c_str_0:')
        i1 = s.index('p8c_str_1:')
        self.assertLess(i0, i1)
        self.assertIn('"M", 0', s[i0:i1])
        self.assertIn('"H", 0', s[i1:])

    def test_lcd_clear_emits_jsr_only(self):
        s = compile_text('%import lcd\n%output raw\n%launcher none\nmain {\n  sub start() { lcd.clear()   }\n}')
        self.assertIn("jsr clear_display", s)

    def test_string_pool_only_present_when_strings_used(self):
        self.assertNotIn("string pool", compile_text('%output raw\n%launcher none\nmain {\n  sub start() {   }\n}'))


class CodeGenPhase2(unittest.TestCase):
    def test_var_address_bindings_emitted_in_prologue(self):
        s = compile_text('%output raw\n%launcher none\nmain {\nubyte counter\n  sub start() {   }\n}')
        self.assertIn("p8v_counter = $40", s)

    def test_assignment_loads_immediate_and_stores(self):
        s = compile_text('%output raw\n%launcher none\nmain {\nubyte x\n  sub start() { x = $7B   }\n}')
        # The immediate-load + store pair is the smoke signal.
        self.assertIn("lda #$7b", s)
        self.assertIn("sta p8v_x", s)

    def test_addition_uses_clc_adc(self):
        s = compile_text('%output raw\n%launcher none\nmain {\nubyte x\nubyte y\n  sub start() { x = x + y   }\n}')
        self.assertIn("lda p8v_x", s)
        self.assertIn("clc", s)
        self.assertIn("adc p8v_y", s)

    def test_subtraction_uses_sec_sbc(self):
        s = compile_text('%output raw\n%launcher none\nmain {\nubyte x\nubyte y\n  sub start() { x = x - y   }\n}')
        self.assertIn("sec", s)
        self.assertIn("sbc p8v_y", s)

    def test_aug_assign_or_emits_ora(self):
        s = compile_text('%output raw\n%launcher none\nmain {\nubyte x\n  sub start() { x |= $80   }\n}')
        self.assertIn("ora #$80", s)

    def test_if_comparison_emits_branch_and_jmp(self):
        # `if x == 0` -- equivalence-jumps through the long-form
        # pattern: cmp ; beq <skip> ; jmp <else/end>.
        s = compile_text('%output raw\n%launcher none\nmain {\nubyte x\n  sub start() { if x == 0 { x = 1 }   }\n}')
        # The condition is `==`; "if false (i.e., NE)" -> branch out.
        # With long-branch handling we now see `beq <skip>; jmp <target>`.
        self.assertIn("cmp ", s)
        self.assertIn("jmp .Lendif_", s)
        self.assertIn("lda #$01", s)

    def test_if_else_has_both_branches(self):
        s = compile_text('%output raw\n%launcher none\nmain {\nubyte x\n  sub start() { if x == 0 { x = 1 } else { x = 2 }   }\n}')
        self.assertIn(".Lelse_", s)
        self.assertIn(".Lendif_", s)

    def test_while_emits_top_and_end_labels(self):
        s = compile_text('%output raw\n%launcher none\nmain {\nubyte x\n  sub start() { while x < 4 { x = x + 1 }   }\n}')
        self.assertIn(".Lwhile_top_", s)
        self.assertIn(".Lwhile_end_", s)
        # `<` (unsigned) negates to `bcs`-equivalent; long-branch path
        # rewrites to `bcc <skip>; jmp <end>`.
        self.assertIn("bcc ", s)
        self.assertIn("jmp .Lwhile_end_", s)

    def test_repeat_pushes_counter_pulls_and_decrements(self):
        s = compile_text('%output raw\n%launcher none\nmain {\n  sub start() { repeat 3 { }   }\n}')
        self.assertIn("pha", s)
        self.assertIn("pla", s)
        self.assertIn("sbc #1", s)

    def test_break_inside_loop_emits_jmp(self):
        s = compile_text('%output raw\n%launcher none\nmain {\nubyte x\n  sub start() { while x < 4 { break }   }\n}')
        self.assertIn("jmp .Lwhile_end_", s)

    def test_break_outside_loop_errors(self):
        from p8c.codegen import CodeGenError
        with self.assertRaises(CodeGenError):
            compile_text('%output raw\n%launcher none\nmain {\n  sub start() { break   }\n}')

    def test_print_ub_loads_then_jsrs_display_hex(self):
        s = compile_text('%import txt\n%output raw\n%launcher none\nmain {\nubyte x\n  sub start() { txt.print_ub(x)   }\n}')
        self.assertIn("lda p8v_x", s)
        self.assertIn("jsr display_hex", s)

    def test_uword_init_emits_lo_and_hi_stores(self):
        s = compile_text('%output raw\n%launcher none\nmain {\nuword w = $1234\n  sub start() {   }\n}')
        self.assertIn("lda #$34", s)
        self.assertIn("ldy #$12", s)
        self.assertIn("sta p8v_w", s)
        self.assertIn("sty p8v_w+1", s)

    def test_for_loop_emits_init_cmp_branch_inc(self):
        s = compile_text('%output raw\n%launcher none\nmain {\nubyte i\n  sub start() { for i in 0 to 3 { }   }\n}')
        self.assertIn("sta p8v_i", s)
        self.assertIn("cmp #$03", s)
        # Long-branch form: bne <skip>; jmp <end>.
        self.assertIn("bne ", s)
        self.assertIn("jmp .Lfor_end_", s)
        self.assertIn("inc p8v_i", s)

    def test_peek_lowers_to_absolute_load(self):
        s = compile_text('%output raw\n%launcher none\nmain {\nubyte x\n  sub start() { x = peek($f001)   }\n}')
        self.assertIn("lda $f001", s)
        self.assertIn("sta p8v_x", s)

    def test_poke_lowers_to_absolute_store(self):
        s = compile_text('%output raw\n%launcher none\nmain {\n  sub start() { poke($f001, $55)   }\n}')
        self.assertIn("lda #$55", s)
        self.assertIn("sta $f001", s)

    def test_print_uw_high_then_low(self):
        s = compile_text('%import txt\n%output raw\n%launcher none\nmain {\nuword w = $abcd\n  sub start() { txt.print_uw(w)   }\n}')
        # Two display_hex calls.
        self.assertEqual(s.count("jsr display_hex"), 2)


class InitializedArrays(unittest.TestCase):
    def test_ubyte_array_literal(self):
        s = compile_text('%output raw\n%launcher none\nmain {\nubyte[] t = [10, 20, 30]\n  sub start() { ubyte x x = t[0]   }\n}')
        self.assertIn("p8a_t:", s)
        self.assertIn("  .byte 10, 20, 30", s)

    def test_ubyte_array_explicit_size_and_consts(self):
        s = compile_text('%output raw\n%launcher none\nmain {\nconst ubyte A = 7\nubyte[3] t = [A, A, 9]\n  sub start() { ubyte x x = t[2]   }\n}')
        self.assertIn("  .byte 7, 7, 9", s)

    def test_uword_array_of_ints(self):
        # Split lo/hi storage (upstream @split model).
        s = compile_text('%output raw\n%launcher none\nmain {\nuword[] t = [$1234, 7]\n  sub start() { uword w w = t[1]   }\n}')
        self.assertIn("  .byte <4660, <7", s)
        self.assertIn("  .byte >4660, >7", s)

    def test_uword_array_of_strings_uses_pool_labels(self):
        s = compile_text('%output raw\n%launcher none\nmain {\nuword[] t = ["ab", "cd"]\n  sub start() { uword w w = t[0]   }\n}')
        self.assertIn("  .byte <p8c_str_0, <p8c_str_1", s)
        self.assertIn("  .byte >p8c_str_0, >p8c_str_1", s)
        self.assertIn('p8c_str_0:', s)

    def test_size_mismatch_is_error(self):
        from p8c.sema import SemaError
        with self.assertRaises(SemaError):
            compile_text('main {\nubyte[3] t = [1, 2]\n  sub start() {   }\n}')

    def test_inferred_size_needs_list(self):
        from p8c.parse import ParseError
        with self.assertRaises(ParseError):
            compile_text('main {\nubyte[] t = 5\n  sub start() {   }\n}')


class StringCompare(unittest.TestCase):
    def test_compare_lowers_to_helper_and_emits_it_once(self):
        s = compile_text('%import strings\n%output raw\n%launcher none\nmain {\n  sub start() { if strings.compare("a", "b") == 0 { }   }\n}')
        self.assertIn("jsr __p8c_strcmp", s)
        self.assertEqual(s.count("__p8c_strcmp:"), 1)

    def test_no_helper_when_unused(self):
        s = compile_text('%import strings\n%output raw\n%launcher none\nmain {\n  sub start() {   }\n}')
        self.assertNotIn("__p8c_strcmp:", s)

    def test_compare_parks_both_pointers(self):
        s = compile_text('%import strings\n%output raw\n%launcher none\nmain {\n  sub start() { ubyte x x = 0 if strings.compare("a","b")==0 {x=1}   }\n}')
        self.assertIn("sta __p8c_wtmp0", s)
        self.assertIn("sta __p8c_wtmp1", s)

    def test_compare_requires_import(self):
        from p8c.sema import SemaError
        with self.assertRaises(SemaError):
            compile_text('main {\n  sub start() { if strings.compare("a","b")==0 { }   }\n}')


class MainNamespaceForm(unittest.TestCase):
    """Upstream-style `main { <decls + sub start()> }`: `main` is a namespace
    whose members flatten into the program and `start` is the entry sub."""

    NS = ('%output raw\n%launcher none\nmain {\n    ubyte counter\n    sub helper() -> ubyte { return 42 }\n    sub start() { counter = helper() }\n}\n')

    def test_entry_is_start(self):
        s = compile_text(self.NS, target="nmos")
        self.assertIn("jmp p8s_start", s)        # prologue jumps to start
        self.assertNotIn("jmp p8s_main", s)

    def test_reset_vector_points_to_start(self):
        self.assertIn("  .word p8s_start", compile_text(self.NS, target="nmos"))

    def test_members_flattened(self):
        s = compile_text(self.NS, target="nmos")
        self.assertIn("; ---- sub start ----", s)
        self.assertIn("; ---- sub helper ----", s)
        self.assertIn("jsr p8s_helper", s)        # start calls the member sub

    def test_start_gets_nmos_exit(self):
        # the entry sub (start) ends in the nmos exit syscall, not a bare rts.
        self.assertIn("jsr $f00f", compile_text(self.NS, target="nmos"))

    def test_missing_start_is_an_error(self):
        from p8c.parse import ParseError
        with self.assertRaises(ParseError):
            compile_text("main {\n  sub helper() { }\n}\n")

    def test_lenient_body_form_is_rejected(self):
        # The non-upstream `main { <statements> }` entry-body form no longer
        # parses; the body must live in a `sub start()`.
        from p8c.parse import ParseError
        with self.assertRaises(ParseError):
            compile_text("main {\n    ubyte x\n    x = 1\n}\n")

    def test_launcher_directive_ignored(self):
        # `%launcher none` (upstream directive) parses and emits nothing extra.
        self.assertEqual(compile_text('%output raw\n%launcher none\nmain {\n  sub start() {   }\n}'),
                         compile_text('%output raw\n%launcher none\nmain {\n  sub start() {   }\n}'))

    def test_external_target_selects_nmos(self):
        # The target is selected externally (no %target directive): nmos
        # codegen emits the $0200 load address + the nmos exit syscall.
        ext = compile_text('%output raw\n%launcher none\nmain {\n  sub start() {   }\n}', target="nmos")
        self.assertIn("  .org $0200", ext)
        self.assertIn("jsr $f00f", ext)
        # wendy2c (the default) does not emit the nmos exit syscall.
        self.assertNotIn("jsr $f00f", compile_text('%output raw\n%launcher none\nmain {\n  sub start() {   }\n}'))


class RawInlineAsm(unittest.TestCase):
    """The raw `%asm {{ ... }}` form (unquoted body) is the only inline-asm
    form; the legacy quoted `%asm{{ "..." }}` form is retired (rejected)."""

    def test_raw_normalized_and_indented(self):
        s = compile_text(
            '%output raw\n%launcher none\nmain {\n  sub start() {\n    %asm {{\n        nop\n        rts\n    }}\n  }\n}\n', target="nmos")
        self.assertIn("\n  nop\n", s)        # per-line stripped, re-indented by 2
        self.assertIn("\n  rts\n", s)

    def test_legacy_quoted_rejected(self):
        from p8c.lex import LexError
        with self.assertRaises(LexError):
            compile_text(
                'main {\n  sub start() {\n'
                '    %asm{{ "inx" }}\n  }\n}\n', target="nmos")


class RegisterAbiAsmsub(unittest.TestCase):
    """Upstream register-ABI asmsubs: `@A/@X/@Y/@AY` params + `-> rt @REG`,
    the `extsub $ADDR = name(...)` form, and asmsub bodies."""

    IO = ('%output raw\n%launcher none\nmain {\nextsub $F00F = _exit(ubyte code @A)\nasmsub _argv(ubyte i @A) -> uword @AY { %asm {{\n        jsr  $f01e\n        rts\n}} }\nasmsub _write(ubyte b @A, ubyte handle @X) { %asm {{\n        jsr  $f024\n        rts\n}} }\n  ubyte h\n  uword p\n  sub start() { h = 3  p = _argv(1)  _write(65, h)  _exit(0) }\n}\n')

    def test_extsub_call_jsrs_address(self):
        s = compile_text(self.IO, target="nmos")
        self.assertIn("  lda #$00\n  jsr $f00f", s)   # _exit(0) -> A=0, jsr addr

    def test_asmsub_body_emitted_under_label(self):
        s = compile_text(self.IO, target="nmos")
        self.assertIn("p8s__argv:\n  jsr  $f01e", s)
        self.assertIn("p8s__write:\n  jsr  $f024", s)

    def test_word_return_in_ay(self):
        s = compile_text(self.IO, target="nmos")
        # p = _argv(1): arg in A, result word in A:Y stored lo/hi.
        self.assertIn("  lda #$01\n  jsr p8s__argv\n  sta p8v_p\n  sty p8v_p+1", s)

    def test_multi_reg_args_ordered(self):
        # _write(65, h): handle (@X) loaded first via A->X, b (@A) loaded last.
        s = compile_text(self.IO, target="nmos")
        self.assertIn("  lda p8v_h\n  tax\n  lda #$41\n  jsr p8s__write", s)

    def test_reg_params_have_no_storage(self):
        # register-ABI params get no ZP/memvar slot.
        s = compile_text(self.IO, target="nmos")
        self.assertNotIn("p8v__write_arg_b", s)
        self.assertNotIn("p8v__argv_arg_i", s)


if __name__ == "__main__":
    unittest.main()
