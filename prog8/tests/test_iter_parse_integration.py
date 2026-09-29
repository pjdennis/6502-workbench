"""Whole-program integration check for the iterative expression parser.

`tests/test_iter_parse.py` proves the iterative parser matches the
recursive one on isolated expressions. This file goes one step further:
it compiles every real `.p8` in the repo (examples + snapshot corpus)
through the full pipeline (parse -> sema -> codegen) twice -- once with
the recursive expression parser, once with the iterative one -- and
asserts the generated assembly is byte-identical.

That exercises the iterative parser on every expression that actually
appears in the project's source, integrated with sema and codegen, not
just in a unit harness. Identical output across the corpus is the
strongest equivalence evidence short of switching the compiler over.
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

EXAMPLES = ROOT / "examples"
SNAPS = ROOT / "tests" / "snapshots"
TINYP8 = ROOT / "tinyp8" / "tinyp8.p8"


def _compile(p8_path: Path, **flags) -> str:
    src = p8_path.read_text()
    prog = parse(lex(src, str(p8_path)), str(p8_path), **flags)
    analyze(prog)
    return generate(prog, p8_path.name)


def _corpus() -> list[Path]:
    paths: list[Path] = []
    for d in (EXAMPLES, SNAPS):
        if d.exists():
            paths.extend(sorted(d.glob("*.p8")))
    if TINYP8.exists():
        paths.append(TINYP8)
    return paths


class IterParseIntegration(unittest.TestCase):
    def test_iter_expr_codegen_identical(self):
        corpus = _corpus()
        self.assertGreater(len(corpus), 0, "no .p8 corpus found")
        for p8 in corpus:
            with self.subTest(p8=p8.name):
                recursive = _compile(p8, iter_expr=False, iter_stmt=False)
                iterative = _compile(p8, iter_expr=True, iter_stmt=False)
                self.assertEqual(recursive, iterative,
                                 msg=f"codegen differs for {p8.name} "
                                     f"with the iterative expression parser")

    def test_iter_stmt_codegen_identical(self):
        # iter_stmt routes the whole block/statement chain through the
        # frame-stack driver (and implies iter_expr), so this exercises
        # the iterative parser end to end -- now the default path.
        corpus = _corpus()
        self.assertGreater(len(corpus), 0, "no .p8 corpus found")
        for p8 in corpus:
            with self.subTest(p8=p8.name):
                recursive = _compile(p8, iter_expr=False, iter_stmt=False)
                iterative = _compile(p8, iter_stmt=True)
                self.assertEqual(recursive, iterative,
                                 msg=f"codegen differs for {p8.name} "
                                     f"with the iterative statement parser")


if __name__ == "__main__":
    unittest.main()
