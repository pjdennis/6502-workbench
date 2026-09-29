"""Equivalence tests for the iterative expression parser (Phase 6).

For a corpus of expression inputs we parse the same tokens with both
the recursive `parse.Parser.parse_expr` and the iterative
`iter_parse.IterParser.parse_expr`, then assert that:

  * the resulting ASTs are structurally identical (ignoring source
    `Loc`), and
  * both parsers consume exactly the same number of tokens (so the
    iterative parser can be dropped in where the recursive one is
    called, stopping at the same boundary).

When these hold across the corpus, the iterative parser is a faithful
replacement for expression parsing -- the prerequisite for porting the
parser to Prog8, which forbids recursion.
"""
from __future__ import annotations

import dataclasses
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from p8c.ast import Node  # noqa: E402
from p8c.lex import lex  # noqa: E402
from p8c.parse import Parser, parse  # noqa: E402
from p8c.iter_parse import IterParser  # noqa: E402


def dump(x):
    """Structural serialization that ignores `loc` so two ASTs can be
    compared for shape + content regardless of source positions."""
    if isinstance(x, Node):
        fields = {}
        for f in dataclasses.fields(x):
            if f.name == "loc":
                continue
            fields[f.name] = dump(getattr(x, f.name))
        return (type(x).__name__, fields)
    if isinstance(x, list):
        return [dump(i) for i in x]
    return x


# Each entry is a self-contained expression: the whole token stream
# (before EOF) is one expression, so both parsers should land on EOF.
EXPRESSIONS = [
    # literals + atoms
    "42",
    "$ff",
    "%1010",
    "'A'",
    "'\\n'",
    '"hello"',
    "true",
    "false",
    "foo",
    "a.b",
    "a.b.c",
    # unary
    "-x",
    "- -x",
    "~x",
    "not flag",
    "not a",
    "&buf",
    "&counter",
    "@(ptr)",
    "@(ptr + 1)",
    "@($8000 + i)",
    # binary precedence ladder
    "a + b",
    "a - b - c",
    "a + b * c",
    "a * b + c",
    "a + b & c",
    "a | b & c",
    "a ^ b | c",
    "a << b + c",
    "a >> b",
    "a < b == c",
    "a <= b",
    "a > b >= c",
    "a != b",
    "a and b or c",
    "a or b and c",
    "a xor b",
    "a and b and c",
    # unary mixed with binary
    "-a * b",
    "a * -b",
    "not a and b",
    "-a + -b",
    "~a & ~b",
    # parens
    "(a)",
    "(a + b)",
    "(a + b) * c",
    "a * (b + c)",
    "((a + b) * (c - d)) | e",
    "(((x)))",
    # calls
    "f()",
    "f(a)",
    "f(a, b)",
    "f(a, b, c)",
    "foo.bar(1, $20, \"x\")",
    "peek($8000)",
    "mkword(a, b)",
    "f(a + b, c * d)",
    "f(g(h(x)))",
    "outer(inner(a), b)",
    "f(a) + g(b)",
    "lsb(addr) | msb(addr)",
    # indexing
    "arr[0]",
    "arr[i]",
    "arr[i + 1]",
    "tokens[idx].kind",
    "a.b[c]",
    "a.b[c].d",
    "arr[f(i)]",
    "arr[i] + arr[j]",
    # big mixed
    "a + b * c - d",
    "f(x) + arr[i] * 2 - @(p)",
    "not (a == b) and (c < d or e >= f)",
    "(lsb(x) << 8) | msb(y)",
    "&buf + i * 2",
]

# Inputs where the expression is followed by tokens that are NOT part of
# the expression; both parsers must stop at the same boundary token.
WITH_TRAILERS = [
    "a + b {",          # stop at '{' (e.g. `if a + b { ... }`)
    "x == 0 else",      # stop at a keyword
    "i to 10",          # `for i in lo to hi` shape
    "a + b = c",        # stop at '='
    "f(a) }",           # stop at '}'
    "arr[i] ;",         # ';' isn't lexed, but newline/other -- use '}'
    "a < b )",          # stray ')' ends the expression
    "p + 1 ,",          # stray ',' ends the expression
]


# ---- randomized differential fuzzing ----------------------------------
#
# Generate random *valid* expressions from the supported grammar and
# check both parsers agree. Everything is space-separated so adjacent
# operators never collide into a multi-char token ('--', '<<', '&&', ...).

_IDENTS = ["a", "b", "c", "x", "y", "z", "foo", "bar", "count", "idx"]
_BINOPS = ["+", "-", "*", "&", "|", "^", "<<", ">>",
           "==", "!=", "<", "<=", ">", ">=", "and", "or", "xor"]
_UNOPS = ["-", "~", "not"]


def _gen_atom(rng: random.Random) -> str:
    r = rng.random()
    if r < 0.40:
        name = rng.choice(_IDENTS)
        if rng.random() < 0.15:                       # dotted path
            name += "." + rng.choice(_IDENTS)
        return name
    if r < 0.60:
        return f"${rng.randint(0, 255):02x}"
    if r < 0.66:
        return rng.choice(["true", "false"])
    if r < 0.70:
        return '"s"'
    if r < 0.78:
        return "&" + rng.choice(_IDENTS)
    return rng.choice(_IDENTS)


def _gen_expr(rng: random.Random, depth: int) -> str:
    if depth <= 0:
        return _gen_atom(rng)
    r = rng.random()
    if r < 0.30:                                       # binary
        return (f"{_gen_expr(rng, depth - 1)} {rng.choice(_BINOPS)} "
                f"{_gen_expr(rng, depth - 1)}")
    if r < 0.45:                                       # prefix unary
        return f"{rng.choice(_UNOPS)} {_gen_expr(rng, depth - 1)}"
    if r < 0.58:                                       # parenthesized
        return f"( {_gen_expr(rng, depth - 1)} )"
    if r < 0.72:                                       # call (0..3 args)
        nargs = rng.randint(0, 3)
        args = ", ".join(_gen_expr(rng, depth - 1) for _ in range(nargs))
        return f"{rng.choice(_IDENTS)}({args})"
    if r < 0.84:                                       # @(expr)
        return f"@( {_gen_expr(rng, depth - 1)} )"
    if r < 0.94:                                       # index, maybe .field
        base = f"{rng.choice(_IDENTS)}[ {_gen_expr(rng, depth - 1)} ]"
        if rng.random() < 0.4:
            base += "." + rng.choice(_IDENTS)
        return base
    return _gen_atom(rng)


class IterParseEquivalence(unittest.TestCase):
    def _both(self, src: str):
        toks = lex(src, "<test>")
        # Force the recursive descent for the baseline (it is now opt-in,
        # since the iterative parser is the default).
        rec = Parser(toks, "<test>", iter_expr=False, iter_stmt=False)
        rec_node = rec.parse_expr()
        it = IterParser(toks, "<test>")
        it_node = it.parse_expr()
        return rec, rec_node, it, it_node

    def test_full_expressions_match(self):
        for src in EXPRESSIONS:
            with self.subTest(src=src):
                rec, rec_node, it, it_node = self._both(src)
                self.assertEqual(dump(rec_node), dump(it_node),
                                 msg=f"AST mismatch for {src!r}")
                self.assertEqual(rec.pos, it.pos,
                                 msg=f"end-position mismatch for {src!r}")
                # A full expression consumes everything up to EOF.
                self.assertEqual(it.toks[it.pos].kind, "EOF",
                                 msg=f"did not reach EOF for {src!r}")

    def test_trailers_stop_at_same_boundary(self):
        for src in WITH_TRAILERS:
            with self.subTest(src=src):
                rec, rec_node, it, it_node = self._both(src)
                self.assertEqual(dump(rec_node), dump(it_node),
                                 msg=f"AST mismatch for {src!r}")
                self.assertEqual(rec.pos, it.pos,
                                 msg=f"stop-position mismatch for {src!r}")

    def test_randomized_differential(self):
        rng = random.Random(0xC0FFEE)
        for _ in range(4000):
            depth = rng.randint(0, 5)
            src = _gen_expr(rng, depth)
            rec, rec_node, it, it_node = self._both(src)
            # The generator only emits complete expressions, so both
            # parsers must consume everything and agree on the AST.
            self.assertEqual(dump(rec_node), dump(it_node),
                             msg=f"AST mismatch for {src!r}")
            self.assertEqual(rec.pos, it.pos,
                             msg=f"end-position mismatch for {src!r}")
            self.assertEqual(it.toks[it.pos].kind, "EOF",
                             msg=f"did not reach EOF for {src!r}")


# Full programs exercising the statement surface. Parsed with the
# recursive statement parser and the iterative frame-stack driver
# (iter_stmt=True); the resulting whole-program ASTs must be identical.
STMT_PROGRAMS = [
    '%output raw\n%launcher none\nmain {\n  sub start() {   }\n}',
    'main {\n  sub start() { txt.print("hi")   }\n}',
    '%output raw\n%launcher none\nmain {\nubyte x\n  sub start() { x = 1 x += 2 x <<= 1   }\n}',
    '%output raw\n%launcher none\nmain {\nubyte x\n  sub start() { if x == 0 { x = 1 }   }\n}',
    '%output raw\n%launcher none\nmain {\nubyte x\n  sub start() { if x == 0 { x = 1 } else { x = 2 }   }\n}',
    # nested if / else
    '%output raw\n%launcher none\nmain {\nubyte x\nubyte y\n  sub start() { if x != 0 { if y != 0 { x = 1 } else { x = 2 } } else { y = 3 }   }\n}',
    '%output raw\n%launcher none\nmain {\nubyte i\n  sub start() { while i < 10 { i = i + 1 }   }\n}',
    'main {\nubyte i\n  sub start() { for i in 0 to 7 { txt.print("x") }   }\n}',
    '%output raw\n%launcher none\nmain {\n  sub start() { repeat { break }   }\n}',
    'main {\n  sub start() { repeat 5 { txt.print(".") }   }\n}',
    'main {\nubyte i\n  sub start() { for i in 0 to 3 { if i == 2 { continue } txt.print("y") }   }\n}',
    # when: multi-value choices + else
    "main {\n  sub start() {   }\n  sub f(ubyte c) { when c { $61 -> { txt.print(\"a\") } $62, $63 -> { txt.print(\"bc\") } else -> { txt.print(\"?\") } } }\n}",
    # defer (simple) and defer before a compound
    "main {\nubyte x\n  sub start() {   }\n  sub g() { defer txt.print(\"3\") defer txt.print(\"2\") txt.print(\"body\") }\n}",
    "main {\nubyte x\n  sub start() {   }\n  sub h() { defer if x != 0 { txt.print(\"z\") } x = 1 }\n}",
    # returns
    "main {\n  sub start() {   }\n  sub r() -> ubyte { return 5 }\n}",
    "main {\n  sub start() {   }\n  sub r2() -> bool { return true }\n}",
    "main {\n  sub start() {   }\n  sub r3() { return }\n}",
    # memory + array statements
    '%output raw\n%launcher none\nmain {\n  sub start() { @($f001) = 7   }\n}',
    '%output raw\n%launcher none\nmain {\nubyte[4] arr\n  sub start() { arr[0] = 1 arr[1] = arr[0] + 2   }\n}',
    # inline asm
    '%output raw\n%launcher none\nmain {\n  sub start() { %asm {{\nnop\n}}   }\n}',
    # deeply nested mix
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\n  sub start() { while a < 8 { for b in 0 to a { if b == 3 { break } } a = a + 1 }   }\n}',
]


class IterStmtEquivalence(unittest.TestCase):
    def test_full_program_asts_match(self):
        for src in STMT_PROGRAMS:
            with self.subTest(src=src):
                rec = parse(lex(src, "<t>"), "<t>",
                            iter_expr=False, iter_stmt=False)
                it = parse(lex(src, "<t>"), "<t>", iter_stmt=True)
                self.assertEqual(dump(rec), dump(it),
                                 msg=f"program AST mismatch for {src!r}")


if __name__ == "__main__":
    unittest.main()
