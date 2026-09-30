"""Lexer unit tests. Each Prog8 feature added in later phases gets
fresh cases here before it ships."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from p8c.lex import Token, lex, LexError  # noqa: E402

import unittest


class LexBasics(unittest.TestCase):
    def kinds(self, src: str) -> list[str]:
        return [t.kind for t in lex(src, "<test>")]

    def test_empty_input_yields_eof(self):
        self.assertEqual(self.kinds(""), ["EOF"])

    def test_keywords_vs_idents(self):
        toks = lex("sub main banana", "<test>")
        self.assertEqual(toks[0].kind, "KW")
        self.assertEqual(toks[0].value, "sub")
        self.assertEqual(toks[1].kind, "KW")
        self.assertEqual(toks[1].value, "main")
        # `banana` is NOT a keyword:
        self.assertEqual(toks[2].kind, "IDENT")
        self.assertEqual(toks[2].value, "banana")

    def test_int_literals_hex_bin_dec(self):
        toks = lex("$ff %10110010 42", "<test>")
        self.assertEqual([t.value for t in toks[:3]], [0xFF, 0b10110010, 42])

    def test_string_with_escapes(self):
        toks = lex(r'"hi\n" "tab\t" "hex\x41"', "<test>")
        self.assertEqual(toks[0].value, "hi\n")
        self.assertEqual(toks[1].value, "tab\t")
        self.assertEqual(toks[2].value, "hexA")

    def test_unterminated_string_errors(self):
        with self.assertRaises(LexError):
            lex('"abc', "<test>")

    def test_multi_char_operators(self):
        kinds = self.kinds("== != <= >= << >> ++ -- += -> &&")
        self.assertEqual(kinds[:10],
                         ["==", "!=", "<=", ">=", "<<", ">>", "++", "--", "+=", "->"])

    def test_directive_token(self):
        toks = lex("%address $4000", "<test>")
        self.assertEqual(toks[0].kind, "DIRECTIVE")
        self.assertEqual(toks[0].value, "address")
        self.assertEqual(toks[1].kind, "INT")
        self.assertEqual(toks[1].value, 0x4000)

    def test_comment_to_end_of_line(self):
        toks = lex("$ff ; comment\n42", "<test>")
        self.assertEqual([t.kind for t in toks], ["INT", "INT", "EOF"])
        self.assertEqual([t.value for t in toks[:2]], [0xFF, 42])

    def test_location_tracking(self):
        toks = lex("foo\nbar", "<test>")
        self.assertEqual((toks[0].line, toks[0].col), (1, 1))
        self.assertEqual((toks[1].line, toks[1].col), (2, 1))


if __name__ == "__main__":
    unittest.main()
