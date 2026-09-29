"""Sema unit tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from p8c.lex import lex  # noqa: E402
from p8c.parse import parse  # noqa: E402
from p8c.sema import SemaError, analyze  # noqa: E402


def compile_to_sema(src: str):
    prog = parse(lex(src, "<test>"), "<test>")
    analyze(prog)
    return prog


class SemaBasics(unittest.TestCase):
    def test_main_required(self):
        with self.assertRaises(SemaError) as ctx:
            compile_to_sema("%import txt")
        self.assertIn("main", str(ctx.exception))

    def test_unknown_import_errors(self):
        with self.assertRaises(SemaError):
            compile_to_sema('%import bogusmod\nmain {\n  sub start() {   }\n}')

    def test_unknown_call_errors(self):
        with self.assertRaises(SemaError) as ctx:
            compile_to_sema('%import txt\nmain {\n  sub start() { whatever.beep()   }\n}')
        self.assertIn("whatever.beep", str(ctx.exception))

    def test_resolves_txt_print(self):
        prog = compile_to_sema('%import txt\n%output raw\n%launcher none\nmain {\n  sub start() { txt.print("x")   }\n}')
        stmt = prog.subs[0].body.stmts[0]
        sym = stmt.expr.sym
        self.assertIsNotNone(sym)
        self.assertEqual(sym.kind, "extsub")
        self.assertEqual(sym.asm_target, "display_string")

    def test_main_gets_mangled(self):
        prog = compile_to_sema('%output raw\n%launcher none\nmain {\n  sub start() {   }\n}')
        self.assertEqual(prog.subs[0].mangled, "p8s_start")

    def test_strings_typed_but_not_yet_labeled(self):
        # Labels + Program.strings are now owned by codegen (assigned
        # lazily, main-first, to stay byte-identical with p1). Sema only
        # fixes the type.
        prog = compile_to_sema('%import txt\n%output raw\n%launcher none\nmain {\n  sub start() { txt.print("a") txt.print("b")   }\n}')
        self.assertEqual(len(prog.strings), 0)
        lit = prog.subs[0].body.stmts[0].expr.args[0]
        self.assertIsNone(lit.label)
        self.assertEqual(lit.type.__class__.__name__, "TStr")


class SemaPhase2(unittest.TestCase):
    def test_var_gets_zp_address_and_mangled_name(self):
        prog = compile_to_sema('%output raw\n%launcher none\nmain {\nubyte counter\n  sub start() {   }\n}')
        sym = prog.module_vars[0].sym
        self.assertIsNotNone(sym)
        self.assertEqual(sym.mangled, "p8v_counter")
        self.assertIsNotNone(sym.address)
        self.assertGreaterEqual(sym.address, 0x40)

    def test_sub_local_mangled_with_sub_name(self):
        prog = compile_to_sema('%output raw\n%launcher none\nmain {\n  sub start() { ubyte tmp   }\n}')
        body = prog.subs[0].body.stmts
        sym = body[0].sym
        self.assertEqual(sym.mangled, "p8v_start_tmp")

    def test_duplicate_var_in_same_scope_errors(self):
        with self.assertRaises(SemaError):
            compile_to_sema('main {\nubyte x\nubyte x\n  sub start() {   }\n}')

    def test_comparison_requires_ubyte_operands(self):
        # Bool == ubyte is a type error.
        with self.assertRaises(SemaError):
            compile_to_sema('main {\n  sub start() { if true == 0 { }   }\n}')

    def test_assignment_type_mismatch_errors(self):
        # Cannot assign string to ubyte.
        with self.assertRaises(SemaError):
            compile_to_sema('%import txt\nmain {\nubyte x\n  sub start() { x = "abc"   }\n}')

    def test_repeat_count_must_be_ubyte(self):
        with self.assertRaises(SemaError):
            compile_to_sema('%import txt\nmain {\n  sub start() { repeat "boom" { }   }\n}')

    def test_uword_allocates_two_zp_bytes(self):
        prog = compile_to_sema('%output raw\n%launcher none\nmain {\nuword a\nuword b\n  sub start() {   }\n}')
        sym_a = prog.module_vars[0].sym
        sym_b = prog.module_vars[1].sym
        self.assertEqual(sym_a.type.__repr__(), "uword")
        self.assertEqual(sym_b.address - sym_a.address, 2)

    def test_uword_can_be_initialized_from_ubyte_literal(self):
        prog = compile_to_sema('%output raw\n%launcher none\nmain {\nuword w = $42\n  sub start() {   }\n}')
        self.assertEqual(prog.module_vars[0].sym.type.__repr__(), "uword")

    def test_uword_aug_assign_works(self):
        # +=/-= on uword now lowers to `w = w + rhs`.
        prog = compile_to_sema('%output raw\n%launcher none\nmain {\nuword w\n  sub start() { w += $1   }\n}')
        self.assertEqual(prog.subs[0].body.stmts[0].op, "+=")

    def test_for_loop_var_must_pre_exist(self):
        with self.assertRaises(SemaError) as ctx:
            compile_to_sema('main {\n  sub start() { for nope in 0 to 3 { }   }\n}')
        self.assertIn("must be declared", str(ctx.exception))

    def test_builtin_peek_resolves_without_import(self):
        prog = compile_to_sema('%output raw\n%launcher none\nmain {\nubyte x\n  sub start() { x = peek($f001)   }\n}')
        rhs = prog.subs[0].body.stmts[0].rhs
        self.assertEqual(rhs.sym.kind, "builtin")
        self.assertEqual(rhs.sym.name, "peek")


if __name__ == "__main__":
    unittest.main()
