"""lex.py: characters to tokens, by the lexical rules of docs/language.md."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lathec_support as support  # noqa: E402
import err  # noqa: E402
import kernel  # noqa: E402
import lex  # noqa: E402
import src  # noqa: E402

KEYWORDS = ('and asm at bool break byte case const continue critical do downto elif else end '
            'enum extern for forward func if import in inline int interrupt loop mod module '
            'not nozp of or pub record recursive return rows sbyte static then to type until '
            'var while word zp').split()

OPERATORS = {
    '(': lex.T_LPAREN, ')': lex.T_RPAREN, '[': lex.T_LBRACKET, ']': lex.T_RBRACKET,
    ',': lex.T_COMMA, ':': lex.T_COLON, '.': lex.T_DOT, '@': lex.T_ADDRESS, '~': lex.T_TILDE,
    '->': lex.T_ARROW, '=': lex.T_ASSIGN, '+=': lex.T_PLUS_ASSIGN, '-=': lex.T_MINUS_ASSIGN,
    '&=': lex.T_AND_ASSIGN, '|=': lex.T_OR_ASSIGN, '^=': lex.T_XOR_ASSIGN,
    '<<=': lex.T_SHL_ASSIGN, '>>=': lex.T_SHR_ASSIGN,
    '+': lex.T_PLUS, '-': lex.T_MINUS, '*': lex.T_STAR, '/': lex.T_SLASH, '&': lex.T_AMP,
    '|': lex.T_BAR, '^': lex.T_CARET, '<<': lex.T_SHL, '>>': lex.T_SHR,
    '==': lex.T_EQ, '!=': lex.T_NE, '<': lex.T_LT, '<=': lex.T_LE, '>': lex.T_GT, '>=': lex.T_GE,
}
BINARY = ['+', '-', '*', '/', '&', '|', '^', '<<', '>>', '==', '!=', '<', '<=', '>', '>=',
          'and', 'or', 'mod']


def start(text):
    kernel.init()
    src.init()
    lex.init()
    begin, end = support.put_text(text.encode('latin-1'))
    src.open_memory(begin, end)


def tokens(text):
    """The tokens of `text` up to and without the end of file, as a list of token numbers."""
    start(text)
    found = []
    lex.next()
    while lex.tok != lex.T_EOF:
        found.append(lex.tok)
        lex.next()
    return found


def first(text):
    """The first token of `text` as (token, value)."""
    start(text)
    lex.next()
    return lex.tok, lex.value


def spelling(name):
    return bytes(kernel.name_char(name, i) for i in range(kernel.name_length(name))).decode()


def string(text):
    token, _ = first(text)
    assert token == lex.T_STRING, token
    return bytes(lex.string[i] for i in range(lex.string_length))


class LexTest(unittest.TestCase):
    def setUp(self):
        support.fresh()
        err.init()

    def assertError(self, text, number, line, col):
        with self.assertRaises(SystemExit):
            tokens(text)
        self.assertIn('error %d:' % number, support.error_text())
        self.assertEqual((err.line, err.col), (line, col))


class WordsTest(LexTest):
    def test_every_keyword_is_a_token_of_its_own(self):
        seen = set()
        for word in KEYWORDS + ['long']:
            token, _ = first(word)
            self.assertGreaterEqual(token, lex.T_AND, word)
            self.assertNotIn(token, seen, word)
            seen.add(token)
            self.assertEqual(token, getattr(lex, 'T_' + word.upper()), word)

    def test_keywords_are_not_case_sensitive(self):
        self.assertEqual(tokens('WHILE While wHiLe'), [lex.T_WHILE] * 3 + [lex.T_NL])

    def test_a_name_is_a_name_token_with_its_name_as_value(self):
        token, value = first('put_byte2')
        self.assertEqual(token, lex.T_NAME)
        self.assertEqual(spelling(value), 'put_byte2')

    def test_names_fold_to_lower_case(self):
        _, lower = first('count')
        start('Count COUNT cOUNT')
        for _ in range(3):
            lex.next()
            self.assertEqual((lex.tok, spelling(lex.value)), (lex.T_NAME, 'count'))
        self.assertEqual(spelling(lower), 'count')

    def test_the_same_name_twice_has_the_same_value(self):
        start('abc xyz abc')
        lex.next()
        abc = lex.value
        lex.next()
        self.assertNotEqual(lex.value, abc)
        lex.next()
        self.assertEqual(lex.value, abc)

    def test_a_name_that_starts_like_a_keyword_is_a_name(self):
        self.assertEqual(tokens('ifx endif in_ at2'), [lex.T_NAME] * 4 + [lex.T_NL])

    def test_predeclared_names_and_registers_are_ordinary_names(self):
        self.assertEqual(tokens('true false nil lo hi len sizeof a x y ax ay xy c'),
                         [lex.T_NAME] * 14 + [lex.T_NL])

    def test_a_name_cannot_start_with_an_underscore(self):
        self.assertError('_x', err.E_BAD_CHAR, 1, 1)


class NumbersTest(LexTest):
    def number(self, text):
        token, value = first(text)
        self.assertEqual(token, lex.T_NUMBER, text)
        return value

    def test_decimal(self):
        self.assertEqual(self.number('0'), 0)
        self.assertEqual(self.number('123'), 123)
        self.assertEqual(self.number('65535'), 65535)
        self.assertEqual(self.number('007'), 7)

    def test_hexadecimal_in_either_case(self):
        self.assertEqual(self.number('$7F'), 0x7F)
        self.assertEqual(self.number('$f009'), 0xF009)
        self.assertEqual(self.number('$FFFF'), 0xFFFF)
        self.assertEqual(self.number('$0'), 0)

    def test_binary(self):
        self.assertEqual(self.number('%1010'), 10)
        self.assertEqual(self.number('%1111111111111111'), 0xFFFF)

    def test_character(self):
        self.assertEqual(self.number("'A'"), 65)
        self.assertEqual(self.number("'a'"), 97)            # not folded
        self.assertEqual(self.number("' '"), 32)
        self.assertEqual(self.number("';'"), 59)            # not a comment
        self.assertEqual(self.number("'\"'"), 34)

    def test_character_escapes(self):
        for text, value in ((r"'\n'", 10), (r"'\r'", 13), (r"'\t'", 9), (r"'\0'", 0),
                            (r"'\\'", 92), (r"'\"'", 34), (r"'\''", 39), (r"'\x41'", 0x41),
                            (r"'\xfF'", 0xFF)):
            self.assertEqual(self.number(text), value, text)

    def test_a_number_ends_where_its_digits_end(self):
        self.assertEqual(tokens('12ab'), [lex.T_NUMBER, lex.T_NAME, lex.T_NL])
        self.assertEqual(tokens('%102'), [lex.T_NUMBER, lex.T_NUMBER, lex.T_NL])
        self.assertEqual(tokens('$1G'), [lex.T_NUMBER, lex.T_NAME, lex.T_NL])

    def test_numbers_above_65535_are_error_3(self):
        self.assertError('x = 65536', err.E_NUMBER_RANGE, 1, 5)
        self.assertError('99999999999', err.E_NUMBER_RANGE, 1, 1)
        self.assertError('$10000', err.E_NUMBER_RANGE, 1, 1)
        self.assertError('%10000000000000000', err.E_NUMBER_RANGE, 1, 1)

    def test_a_prefix_without_digits_is_error_2(self):
        self.assertError('  $', err.E_BAD_NUMBER, 1, 3)
        self.assertError('$G', err.E_BAD_NUMBER, 1, 1)
        self.assertError('%2', err.E_BAD_NUMBER, 1, 1)

    def test_a_character_constant_must_be_one_character_and_closed(self):
        self.assertError("'AB'", err.E_BAD_CHAR_CONST, 1, 1)
        self.assertError("x 'A", err.E_BAD_CHAR_CONST, 1, 3)
        self.assertError("''", err.E_BAD_CHAR_CONST, 1, 1)
        self.assertError("'\n'", err.E_BAD_CHAR_CONST, 1, 1)


class StringsTest(LexTest):
    def test_a_string_keeps_its_characters_as_written(self):
        self.assertEqual(string('"Hello, World; 1+1"'), b'Hello, World; 1+1')
        self.assertEqual(string('""'), b'')
        self.assertEqual(string('"it\'s"'), b"it's")

    def test_string_escapes(self):
        self.assertEqual(string(r'"a\n\r\t\0\\\"\'\x7F\x00z"'), b'a\n\r\t\0\\"\'\x7f\0z')

    def test_a_string_can_be_as_long_as_the_buffer(self):
        self.assertEqual(string('"' + 'x' * lex.MAX_STRING + '"'), b'x' * lex.MAX_STRING)

    def test_a_longer_string_is_error_7(self):
        self.assertError('"' + 'x' * (lex.MAX_STRING + 1) + '"', err.E_STRING_LONG, 1, 1)

    def test_a_string_must_close_on_its_line(self):
        self.assertError('x = "abc\n"', err.E_OPEN_STRING, 1, 5)
        self.assertError('"abc', err.E_OPEN_STRING, 1, 1)

    def test_an_unknown_escape_is_error_6_at_the_backslash(self):
        self.assertError(r'"ab\q"', err.E_BAD_ESCAPE, 1, 4)
        self.assertError(r'"\N"', err.E_BAD_ESCAPE, 1, 2)          # escapes are case sensitive
        self.assertError(r'"\x4"', err.E_BAD_ESCAPE, 1, 2)
        self.assertError(r"'\xZZ'", err.E_BAD_ESCAPE, 1, 2)

    def test_only_printable_ascii_is_allowed_in_a_string(self):
        self.assertError('"a\tb"', err.E_BAD_CHAR, 1, 3)
        self.assertError('"caf\xe9"', err.E_BAD_CHAR, 1, 5)


class OperatorsTest(LexTest):
    def test_every_operator_and_punctuation_mark(self):
        for text, token in OPERATORS.items():
            self.assertEqual(tokens('x ' + text + ' y')[1], token, text)

    def test_operator_tokens_are_all_different(self):
        self.assertEqual(len(set(OPERATORS.values())), len(OPERATORS))

    def test_the_longest_operator_wins(self):
        self.assertEqual(tokens('a<<=b')[1:2], [lex.T_SHL_ASSIGN])
        self.assertEqual(tokens('a>>=b')[1:2], [lex.T_SHR_ASSIGN])
        self.assertEqual(tokens('a<=b')[1:2], [lex.T_LE])
        self.assertEqual(tokens('a->b')[1:2], [lex.T_ARROW])
        self.assertEqual(tokens('a-=b')[1:2], [lex.T_MINUS_ASSIGN])
        self.assertEqual(tokens('a==b')[1:2], [lex.T_EQ])

    def test_operators_need_no_spaces(self):
        self.assertEqual(tokens('f(a[1],-b)'),
                         [lex.T_NAME, lex.T_LPAREN, lex.T_NAME, lex.T_LBRACKET, lex.T_NUMBER,
                          lex.T_RBRACKET, lex.T_COMMA, lex.T_MINUS, lex.T_NAME, lex.T_RPAREN,
                          lex.T_NL])
        self.assertEqual(tokens('a<-b'), [lex.T_NAME, lex.T_LT, lex.T_MINUS, lex.T_NAME, lex.T_NL])
        self.assertEqual(tokens('p:^byte'),
                         [lex.T_NAME, lex.T_COLON, lex.T_CARET, lex.T_BYTE, lex.T_NL])

    def test_characters_with_no_meaning_are_error_1(self):
        self.assertError('a ? b', err.E_BAD_CHAR, 1, 3)
        self.assertError('a ! b', err.E_BAD_CHAR, 1, 3)        # "!" must be followed by "="
        self.assertError('a\n  {', err.E_BAD_CHAR, 2, 3)
        self.assertError('caf\xe9', err.E_BAD_CHAR, 1, 4)
        self.assertError('a\x01', err.E_BAD_CHAR, 1, 2)
        self.assertError('a\\b', err.E_BAD_CHAR, 1, 2)


class LinesTest(LexTest):
    def test_each_line_ends_with_one_end_of_line_token(self):
        self.assertEqual(tokens('a\nb\n'), [lex.T_NAME, lex.T_NL, lex.T_NAME, lex.T_NL])

    def test_the_last_line_needs_no_newline(self):
        self.assertEqual(tokens('a\nb'), [lex.T_NAME, lex.T_NL, lex.T_NAME, lex.T_NL])

    def test_blank_and_comment_lines_give_no_tokens(self):
        self.assertEqual(tokens('\n\n; comment\n  \t \na\n\n   ; more\n\nb\n\n'),
                         [lex.T_NAME, lex.T_NL, lex.T_NAME, lex.T_NL])
        self.assertEqual(tokens(''), [])
        self.assertEqual(tokens('; only a comment'), [])

    def test_a_comment_runs_to_the_end_of_its_line(self):
        self.assertEqual(tokens('a ; b c "d\nb'), [lex.T_NAME, lex.T_NL, lex.T_NAME, lex.T_NL])

    def test_carriage_returns_are_blanks(self):
        self.assertEqual(tokens('a\r\nb\r\n'), [lex.T_NAME, lex.T_NL, lex.T_NAME, lex.T_NL])

    def test_a_line_continues_after_a_binary_operator(self):
        for operator in BINARY:
            self.assertEqual(tokens('a ' + operator + '\n  b\nc')[2:],
                             [lex.T_NAME, lex.T_NL, lex.T_NAME, lex.T_NL], operator)

    def test_a_line_continues_after_a_comma(self):
        self.assertEqual(tokens('a,\nb'), [lex.T_NAME, lex.T_COMMA, lex.T_NAME, lex.T_NL])

    def test_a_line_continues_over_comments_and_blank_lines(self):
        self.assertEqual(tokens('a + ; one\n\n  ; two\n b'),
                         [lex.T_NAME, lex.T_PLUS, lex.T_NAME, lex.T_NL])

    def test_a_line_continues_while_a_bracket_is_open(self):
        self.assertEqual(tokens('f(a\n)\nb'),
                         [lex.T_NAME, lex.T_LPAREN, lex.T_NAME, lex.T_RPAREN, lex.T_NL,
                          lex.T_NAME, lex.T_NL])
        self.assertEqual(tokens('t[\n(\n1\n)\n]\nb')[-3:], [lex.T_NL, lex.T_NAME, lex.T_NL])

    def test_a_line_does_not_continue_after_anything_else(self):
        for text in ('a =', 'a +=', 'f()', 'not', 'a .', 'x :', '~', '@', 'a ->', 'then'):
            self.assertEqual(tokens(text + '\nb')[-3:], [lex.T_NL, lex.T_NAME, lex.T_NL], text)

    def test_a_closing_bracket_too_many_does_not_hide_later_line_ends(self):
        self.assertEqual(tokens(')\n(\na\n)\nb')[-3:], [lex.T_NL, lex.T_NAME, lex.T_NL])

    def test_the_end_of_the_file_ends_a_line_that_would_continue(self):
        self.assertEqual(tokens('f(a,'), [lex.T_NAME, lex.T_LPAREN, lex.T_NAME, lex.T_COMMA, lex.T_NL])

    def test_the_end_of_the_file_is_given_again_when_asked_again(self):
        tokens('a')
        lex.next()
        self.assertEqual(lex.tok, lex.T_EOF)


class PositionsTest(LexTest):
    def positions(self, text):
        start(text)
        found = []
        lex.next()
        while lex.tok != lex.T_EOF:
            found.append((lex.line, lex.col))
            self.assertEqual((err.line, err.col), (lex.line, lex.col))
            lex.next()
        return found

    def test_a_token_is_where_its_first_character_is(self):
        self.assertEqual(self.positions('ab  cd(12)\n  "s" $FF'),
                         [(1, 1), (1, 5), (1, 7), (1, 8), (1, 10), (1, 11),
                          (2, 3), (2, 7), (2, 10)])

    def test_the_end_of_the_file_has_a_position(self):
        start('a\n')
        for _ in range(3):
            lex.next()
        self.assertEqual((lex.tok, lex.line, lex.col), (lex.T_EOF, 2, 1))


class ExpectTest(LexTest):
    def test_expect_passes_over_the_token_it_wants(self):
        start('func x')
        lex.next()
        lex.expect(lex.T_FUNC, err.E_FUNC_EXPECTED)
        self.assertEqual(lex.tok, lex.T_NAME)

    def test_expect_reports_its_error_at_any_other_token(self):
        start('a  b')
        lex.next()
        lex.next()
        with self.assertRaises(SystemExit):
            lex.expect(lex.T_COLON, err.E_COLON_EXPECTED)
        self.assertIn('error 25:', support.error_text())
        self.assertEqual((err.line, err.col), (1, 4))


class LaterTest(LexTest):
    def test_conditional_compilation_is_not_implemented_yet(self):
        self.assertError('a\n#if X', err.E_UNSUPPORTED, 2, 1)


if __name__ == '__main__':
    unittest.main()
