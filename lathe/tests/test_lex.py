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


def conditional(text, truth):
    """The tokens of `text`, which starts with an `#if` line, when its condition is `truth`:
    as the parser does, the `#if` token and the line end after it are read, then choose()."""
    start(text)
    lex.next()
    assert lex.tok == lex.T_HASH_IF, lex.tok
    lex.next()
    assert lex.tok == lex.T_NL, lex.tok
    lex.choose(truth)
    found = []
    lex.next()
    while lex.tok != lex.T_EOF:
        found.append(lex.tok)
        lex.next()
    return found


NAME_LINE = [lex.T_NAME, lex.T_NL]
NUMBER_LINE = [lex.T_NUMBER, lex.T_NL]


class ConditionalTest(LexTest):
    def assertConditionalError(self, text, truth, number, line, col):
        with self.assertRaises(SystemExit):
            conditional(text, truth)
        self.assertIn('error %d:' % number, support.error_text())
        self.assertEqual((err.line, err.col), (line, col))

    def test_if_is_a_token_and_its_condition_follows(self):
        self.assertEqual(tokens('a\n#if X\n'), [lex.T_NAME, lex.T_NL, lex.T_HASH_IF, lex.T_NAME, lex.T_NL])
        self.assertEqual(tokens('  #IF x'), [lex.T_HASH_IF, lex.T_NAME, lex.T_NL])

    def test_the_part_chosen_is_compiled(self):
        text = '#if\na\n#else\n9\n#end\n'
        self.assertEqual(conditional(text, True), NAME_LINE)
        self.assertEqual(conditional(text, False), NUMBER_LINE)
        self.assertEqual(conditional('#if\na\n#end\n9', False), NUMBER_LINE)
        self.assertEqual(conditional('#if\na\n  #end  ; done\n9', True), NAME_LINE + NUMBER_LINE)

    def test_skipped_lines_need_not_lex(self):
        self.assertEqual(conditional('#if\n"open ` \\q\n$$ #else\n#elsewhere\n#end\na', False), NAME_LINE)

    def test_nesting_is_followed_in_skipped_lines(self):
        text = '#if\n#if\nx\n#else\nx\n#end\n#else\n9\n#end\n'
        self.assertEqual(conditional(text, False), NUMBER_LINE)
        self.assertEqual(conditional('#if\na\n#else\n#if\n#else\n#end\n#end\n9', True),
                         NAME_LINE + NUMBER_LINE)

    def test_a_directive_must_start_its_line(self):
        self.assertError('a #end', err.E_DIRECTIVE, 1, 3)
        self.assertError('#define', err.E_DIRECTIVE, 1, 1)
        self.assertError('# if', err.E_DIRECTIVE, 1, 1)
        self.assertConditionalError('#if\n#end b', True, err.E_DIRECTIVE, 2, 6)
        self.assertConditionalError('#if\n#else b\n#end', False, err.E_DIRECTIVE, 2, 7)

    def test_else_and_end_need_their_if(self):
        self.assertError('#else', err.E_NO_IF, 1, 1)
        self.assertError('a\n  #end', err.E_NO_IF, 2, 3)
        self.assertConditionalError('#if\n#end\n#end', True, err.E_NO_IF, 3, 1)
        self.assertConditionalError('#if\n#else\n#else\n#end', False, err.E_NO_IF, 3, 1)
        self.assertConditionalError('#if\n#else\n#else\n#end', True, err.E_NO_IF, 3, 1)

    def test_an_if_needs_its_end(self):
        self.assertConditionalError('#if\na\n', True, err.E_IF_OPEN, 3, 1)
        self.assertConditionalError('#if\na\n#else\n', False, err.E_IF_OPEN, 4, 1)
        self.assertConditionalError('#if\na\n#else\n', True, err.E_IF_OPEN, 4, 1)

    def test_nesting_has_a_limit(self):
        start('')
        for i in range(lex.MAX_NESTING):
            lex.choose(True)
        with self.assertRaises(SystemExit):
            lex.choose(True)
        self.assertIn('error %d:' % err.E_IF_DEEP, support.error_text())


class SavedTokensTest(LexTest):
    """A saved token run (src.open_saved): LEX reads its tokens, with their places, and goes
    back to the source below at its end."""

    def test_tokens_values_and_places_are_replayed(self):
        start('a\nb')
        lex.next()
        self.assertEqual((lex.tok, lex.line), (lex.T_NAME, 1))
        name = lex.value
        run = bytes([lex.T_NAME, 3, name & 0xFF, name >> 8,
                     lex.T_NUMBER, 5, 0x34, 0x12,
                     lex.SAVED_LINE, 2,
                     lex.T_STRING, 1, 2, ord('h'), ord('i'),
                     lex.T_NL, 9,
                     lex.SAVED_LINE, 255, lex.SAVED_LINE, 1,
                     lex.T_END, 255])
        begin, end = support.put_text(run, 0x9000)
        src.open_saved(begin, end, 0, 10)
        self.assertTrue(src.replaying)
        found = []
        for _ in range(5):
            lex.next()
            found.append((lex.tok, lex.line, lex.col))
        self.assertEqual(found, [(lex.T_NAME, 10, 3), (lex.T_NUMBER, 10, 5), (lex.T_STRING, 12, 1),
                                 (lex.T_NL, 12, 9), (lex.T_END, 268, 255)])
        self.assertEqual(bytes(lex.string[:lex.string_length]), b'hi')
        lex.next()
        self.assertEqual(lex.tok, lex.T_NL)         # the last line ends, as in a file
        lex.next()
        self.assertEqual(lex.tok, lex.T_EOF)
        src.close()
        self.assertFalse(src.replaying)
        lex.resume(lex.T_NAME, 1, 1)
        lex.next()
        self.assertEqual((lex.tok, lex.line), (lex.T_NL, 1))
        lex.next()
        self.assertEqual((lex.tok, lex.line, lex.col), (lex.T_NAME, 2, 1))

    def test_a_number_in_a_run_is_two_bytes(self):
        start('')
        begin, end = support.put_text(bytes([lex.T_NUMBER, 1, 0xFF, 0xFF]), 0x9000)
        src.open_saved(begin, end, 0, 1)
        lex.next()
        self.assertEqual((lex.tok, lex.value), (lex.T_NUMBER, 0xFFFF))


if __name__ == '__main__':
    unittest.main()
