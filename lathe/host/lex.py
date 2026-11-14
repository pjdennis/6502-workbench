"""LEX: characters to tokens.

Owns the current token (the parser looks one token ahead and no further) and everything the
lexical rules of docs/language.md say: case folding, numbers, strings, comments, and where a
line ends. The parser sees one T_NL at the end of each statement and never a blank line: the
continuation rule is applied here and nowhere else.

Conditional compilation is done here too: the lines of a part that is not compiled never
become tokens (directive()). A saved token run (src.open_saved()) is read as tokens, not
characters (saved_token()); the format is at SAVED_LINE. The line mode of `asm` blocks, where whole lines pass through
until a line whose first word is `end`, is ASM's: it reads the source itself.
"""
import err
import kernel
import src

# ---- Tokens ------------------------------------------------------------------------------

T_EOF = 0
T_NL = 1                # the end of a statement's last line
T_NAME = 2              # value: the name
T_NUMBER = 3            # value: the number; a character constant is a number
T_STRING = 4            # the bytes are in `string`

T_LPAREN = 5
T_RPAREN = 6
T_LBRACKET = 7
T_RBRACKET = 8
T_COMMA = 9
T_COLON = 10
T_DOT = 11
T_ADDRESS = 12          # @
T_TILDE = 13
T_ARROW = 14            # ->
T_ASSIGN = 15
T_PLUS_ASSIGN = 16
T_MINUS_ASSIGN = 17
T_AND_ASSIGN = 18
T_OR_ASSIGN = 19
T_XOR_ASSIGN = 20
T_SHL_ASSIGN = 21
T_SHR_ASSIGN = 22

# The binary operators that are not words, T_PLUS to T_GE. A line that ends with one continues.
T_PLUS = 23
T_MINUS = 24
T_STAR = 25
T_SLASH = 26
T_AMP = 27
T_BAR = 28
T_CARET = 29
T_SHL = 30
T_SHR = 31
T_EQ = 32
T_NE = 33
T_LT = 34
T_LE = 35
T_GT = 36
T_GE = 37
T_HASH_IF = 38          # `#if`: the parser works out its condition and calls choose()

# Keywords, numbered in the order of KEYWORDS.
T_AND = 64
T_ASM = 65
T_AT = 66
T_BOOL = 67
T_BREAK = 68
T_BYTE = 69
T_CASE = 70
T_CONST = 71
T_CONTINUE = 72
T_CRITICAL = 73
T_DO = 74
T_DOWNTO = 75
T_ELIF = 76
T_ELSE = 77
T_END = 78
T_ENUM = 79
T_EXTERN = 80
T_FOR = 81
T_FORWARD = 82
T_FUNC = 83
T_IF = 84
T_IMPORT = 85
T_IN = 86
T_INLINE = 87
T_INT = 88
T_INTERRUPT = 89
T_LOOP = 90
T_MOD = 91
T_MODULE = 92
T_NOT = 93
T_NOZP = 94
T_OF = 95
T_OR = 96
T_PUB = 97
T_RECORD = 98
T_RECURSIVE = 99
T_RETURN = 100
T_ROWS = 101
T_SBYTE = 102
T_STATIC = 103
T_THEN = 104
T_TO = 105
T_TYPE = 106
T_UNTIL = 107
T_VAR = 108
T_WHILE = 109
T_WORD = 110
T_ZP = 111
T_LONG = 112            # reserved for later

KEYWORDS = (
    b"and asm at bool break byte case const continue critical do downto elif else end enum "
    b"extern for forward func if import in inline int interrupt loop mod module not nozp of "
    b"or pub record recursive return rows sbyte static then to type until var while word zp "
    b"long "
)
ERROR_WORD = b"error"   # the directive #error, which is not a keyword

# ---- Characters --------------------------------------------------------------------------

C_TAB = 0x09
C_LF = 0x0A
C_CR = 0x0D
C_SPACE = 0x20
C_BANG = 0x21
C_DQUOTE = 0x22
C_HASH = 0x23
C_DOLLAR = 0x24
C_PERCENT = 0x25
C_AMP = 0x26
C_QUOTE = 0x27
C_LPAREN = 0x28
C_RPAREN = 0x29
C_STAR = 0x2A
C_PLUS = 0x2B
C_COMMA = 0x2C
C_MINUS = 0x2D
C_DOT = 0x2E
C_SLASH = 0x2F
C_0 = 0x30
C_9 = 0x39
C_COLON = 0x3A
C_SEMICOLON = 0x3B
C_LESS = 0x3C
C_EQUALS = 0x3D
C_GREATER = 0x3E
C_AT = 0x40
C_UPPER_A = 0x41
C_UPPER_F = 0x46
C_UPPER_Z = 0x5A
C_LBRACKET = 0x5B
C_BACKSLASH = 0x5C
C_RBRACKET = 0x5D
C_CARET = 0x5E
C_UNDERSCORE = 0x5F
C_A = 0x61
C_F = 0x66
C_N = 0x6E
C_R = 0x72
C_T = 0x74
C_X = 0x78
C_Z = 0x7A
C_BAR = 0x7C
C_TILDE = 0x7E

# A saved token run is, for each token: its token number, its column (one byte, at most 255),
# and for T_NAME the name and for T_NUMBER the value (two bytes each), for T_STRING its length
# (one byte: INLINE does not save a longer string) and its bytes. Before a token on a later
# line than the one before it: SAVED_LINE and how many lines later, one or more times (each at
# most 255). Every token number is below SAVED_LINE.
SAVED_LINE = 0x7F
MAX_COLUMN = 0xFF

# ---- The current token -------------------------------------------------------------------

MAX_STRING = 2048       # as long as a constant table can be (out.MAX_TABLE)

tok = T_NL              # T_NL before the first token: a file begins at the start of a line
value = 0
line = 0                # where the token's first character is
col = 0
string = bytearray(MAX_STRING)
string_length = 0
open_brackets = 0       # how many ( and [ are open: no line ends inside them
end_line = 0            # where a line end is that the lexer passed over looking for a further
end_col = 0             # piece of a string, and must still give as a token; line 0: none

MAX_NESTING = 16
nesting = 0             # how many `#if` are open around the line being read
else_parts = 0          # bit n set: the `#if` at depth n + 1 is in its `#else` part


def init():
    """Give the keywords their tokens. Needs a new name heap."""
    global tok, open_brackets, nesting, else_parts, end_line
    tok = T_NL
    open_brackets = 0
    end_line = 0
    nesting = 0
    else_parts = 0
    token = T_AND
    kernel.name_begin()
    for i in range(0, len(KEYWORDS)):
        if KEYWORDS[i] == C_SPACE:
            kernel.name_set_token(kernel.name_end(), token)
            token += 1
            kernel.name_begin()
        else:
            kernel.name_add(KEYWORDS[i])


def fail_here(number):
    """Report an error at the character being looked at, not at the start of the token."""
    err.position(src.line, src.col)
    err.fatal(number)


def fold(c):
    """Upper-case letters as lower case; anything else unchanged."""
    if c >= C_UPPER_A and c <= C_UPPER_Z:
        return c + (C_A - C_UPPER_A)
    return c


def is_letter(c):
    c = fold(c)
    return c >= C_A and c <= C_Z


def is_digit(c):
    return c >= C_0 and c <= C_9


def digit_value(c):
    """The value of `c` as a digit of any base up to 16, and whether it is one."""
    if is_digit(c):
        return c - C_0, True
    c = fold(c)
    if c >= C_A and c <= C_F:
        return c - C_A + 10, True
    return 0, False


def skip_blanks():
    """Pass over blanks and comments. Stops at a line end: that may be a token."""
    while not src.eof:
        if src.ch == C_SEMICOLON:
            while not src.eof and src.ch != C_LF:
                src.advance()
        elif src.ch == C_SPACE or src.ch == C_TAB or src.ch == C_CR:
            src.advance()
        else:
            return


def name_or_keyword():
    """A name or a keyword."""
    global tok, value
    kernel.name_begin()
    while is_letter(src.ch) or is_digit(src.ch) or src.ch == C_UNDERSCORE:
        kernel.name_add(fold(src.ch))
        src.advance()
    name = kernel.name_end()
    tok = kernel.name_token(name)
    if tok == 0:
        tok = T_NAME
        value = name


def number(base):
    """The value of the digits here, of which there must be one or more."""
    n = 0
    count = 0
    while True:
        digit, ok = digit_value(src.ch)
        if not ok or digit >= base:
            break
        if n > (0xFFFF - digit) // base:
            err.fatal(err.E_NUMBER_RANGE)
        n = n * base + digit
        count += 1
        src.advance()
    if count == 0:
        err.fatal(err.E_BAD_NUMBER)
    return n


def hex_digit():
    """The value of the hexadecimal digit of an escape, which is passed over."""
    digit, ok = digit_value(src.ch)
    if not ok:
        err.fatal(err.E_BAD_ESCAPE)
    src.advance()
    return digit


def escape():
    """The value of the escape whose backslash is here."""
    err.position(src.line, src.col)         # a bad escape is reported at its backslash
    src.advance()
    c = src.ch
    src.advance()
    if c == C_N:
        c = C_LF
    elif c == C_R:
        c = C_CR
    elif c == C_T:
        c = C_TAB
    elif c == C_0:
        c = 0
    elif c == C_X:
        c = hex_digit() << 4
        c = c | hex_digit()
    elif c != C_BACKSLASH and c != C_DQUOTE and c != C_QUOTE:
        err.fatal(err.E_BAD_ESCAPE)
    err.position(line, col)
    return c


def literal_char():
    """The value of one character or escape inside a string or character constant."""
    c = src.ch
    if c == C_BACKSLASH:
        return escape()
    if c < C_SPACE or c > C_TILDE:
        fail_here(err.E_BAD_CHAR)
    src.advance()
    return c


def character():
    """The value of a character constant, after its opening quote."""
    if src.eof or src.ch == C_LF or src.ch == C_QUOTE:
        err.fatal(err.E_BAD_CHAR_CONST)
    c = literal_char()
    if src.ch != C_QUOTE:
        err.fatal(err.E_BAD_CHAR_CONST)
    src.advance()
    return c


def string_token():
    """Collect a string, after its opening quote, into `string`, after what is there."""
    global string_length
    while src.ch != C_DQUOTE:
        if src.eof or src.ch == C_LF:
            err.fatal(err.E_OPEN_STRING)
        c = literal_char()
        if string_length == MAX_STRING:
            err.fatal(err.E_STRING_LONG)
        string[string_length] = c
        string_length += 1
    src.advance()


def string_pieces():
    """After a string: the strings that follow it, on its line or at the start of later lines,
    with nothing but blanks, comments and line ends between, are joined to it. A line end
    passed over is the next token if no string follows."""
    global end_line, end_col
    while True:
        skip_blanks()
        if src.eof or (src.ch != C_DQUOTE and src.ch != C_LF):
            return
        if src.ch == C_LF and end_line == 0:
            end_line = src.line
            end_col = src.col
        if src.ch == C_DQUOTE:
            end_line = 0
        src.advance()
        if end_line == 0:
            string_token()


def directive_word():
    """The word after a `#`, which has been passed over, as a token: T_IF, T_ELSE, T_END or
    another."""
    name_or_keyword()
    return tok


def line_end():
    """The rest of a directive's line must be blank or a comment: pass over it and its end."""
    skip_blanks()
    if not src.eof:
        if src.ch != C_LF:
            fail_here(err.E_DIRECTIVE)
        src.advance()


def skip_part(to_else):
    """Pass over the lines of a part that is not compiled, without making tokens of them, up
    to the `#end` that closes it or, if `to_else`, its `#else`; and that directive's line.
    Only a line that starts with `#` is looked at, for the nesting of `#if`. Returns True if
    it stopped at an `#else`."""
    depth = 0
    while True:
        while src.ch == C_SPACE or src.ch == C_TAB:
            src.advance()
        if src.eof:
            fail_here(err.E_IF_OPEN)
        if src.ch == C_HASH:
            err.position(src.line, src.col)
            src.advance()
            found = directive_word()
            if found == T_IF:
                depth += 1
            elif depth > 0 and found == T_END:
                depth -= 1
            elif depth == 0 and found == T_END:
                line_end()
                return False
            elif depth == 0 and found == T_ELSE:
                if not to_else:
                    err.fatal(err.E_NO_IF)          # a second #else
                line_end()
                return True
        while not src.eof and src.ch != C_LF:
            src.advance()
        src.advance()


def choose(yes):
    """The parser has worked out the condition of an `#if` and read its line to the end:
    what follows is compiled if `yes`, and otherwise only its `#else` part, if it has one."""
    global tok, nesting, else_parts
    if nesting == MAX_NESTING:
        err.fatal(err.E_IF_DEEP)
    nesting += 1
    if not yes:
        if skip_part(True):
            else_parts = else_parts | (1 << (nesting - 1))
        else:
            nesting -= 1
        tok = T_NL                  # skip_part() read the directives' words as tokens


def directive():
    """A directive, whose `#` has been passed over, which must start its line (docs/language.md,
    "Conditional compilation"). `#if` is a token: the parser works out its condition and calls
    choose(). `#else` ends the part being compiled, and the lines up to its `#end` are passed
    over. `#else` and `#end` leave a T_NL, as a blank line would, so the parser never sees them."""
    global tok, nesting, else_parts
    if tok != T_NL:
        err.fatal(err.E_DIRECTIVE)
    found = directive_word()
    if found == T_IF:
        tok = T_HASH_IF
        return
    if found == T_NAME and is_error_word(value):
        error_directive()
    if found != T_ELSE and found != T_END:
        err.fatal(err.E_DIRECTIVE)
    if nesting == 0:
        err.fatal(err.E_NO_IF)
    bit = 1 << (nesting - 1)
    if found == T_ELSE and else_parts & bit != 0:
        err.fatal(err.E_NO_IF)
    line_end()
    if found == T_ELSE:
        skip_part(False)
    nesting -= 1
    else_parts = else_parts & (~bit & 0xFFFF)
    tok = T_NL


def is_error_word(name):
    """True if `name` is `error`, which is not a keyword: it means something only after `#`."""
    if kernel.name_length(name) != len(ERROR_WORD):
        return False
    for i in range(0, len(ERROR_WORD)):
        if kernel.name_char(name, i) != ERROR_WORD[i]:
            return False
    return True


def error_directive():
    """`#error`, with a string after it or nothing, in a part that is compiled: error 181 at the
    `#`, with ": " and the string's text after the error's."""
    global string_length
    skip_blanks()
    string_length = 0
    if not src.eof and src.ch == C_DQUOTE:
        src.advance()
        string_token()
    err.position(line, col)
    err.fatal_start(err.E_ERROR_DIRECTIVE)
    if string_length > 0:
        err.put_char(C_COLON)
        err.put_char(C_SPACE)
    for i in range(0, string_length):
        err.put_char(string[i])
    err.fatal_end()


def followed_by(c, yes, no):
    """`yes` if the next character is `c`, which is then passed over; `no` if it is not."""
    if src.ch == c:
        src.advance()
        return yes
    return no


def mark(c):
    """The operator or punctuation token that starts with `c`, which has been passed over."""
    if c == C_LPAREN:
        return T_LPAREN
    if c == C_RPAREN:
        return T_RPAREN
    if c == C_LBRACKET:
        return T_LBRACKET
    if c == C_RBRACKET:
        return T_RBRACKET
    if c == C_COMMA:
        return T_COMMA
    if c == C_COLON:
        return T_COLON
    if c == C_DOT:
        return T_DOT
    if c == C_AT:
        return T_ADDRESS
    if c == C_TILDE:
        return T_TILDE
    if c == C_STAR:
        return T_STAR
    if c == C_SLASH:
        return T_SLASH
    if c == C_PLUS:
        return followed_by(C_EQUALS, T_PLUS_ASSIGN, T_PLUS)
    if c == C_AMP:
        return followed_by(C_EQUALS, T_AND_ASSIGN, T_AMP)
    if c == C_BAR:
        return followed_by(C_EQUALS, T_OR_ASSIGN, T_BAR)
    if c == C_CARET:
        return followed_by(C_EQUALS, T_XOR_ASSIGN, T_CARET)
    if c == C_EQUALS:
        return followed_by(C_EQUALS, T_EQ, T_ASSIGN)
    if c == C_MINUS:
        if src.ch == C_GREATER:
            src.advance()
            return T_ARROW
        return followed_by(C_EQUALS, T_MINUS_ASSIGN, T_MINUS)
    if c == C_LESS:
        if src.ch == C_LESS:
            src.advance()
            return followed_by(C_EQUALS, T_SHL_ASSIGN, T_SHL)
        return followed_by(C_EQUALS, T_LE, T_LT)
    if c == C_GREATER:
        if src.ch == C_GREATER:
            src.advance()
            return followed_by(C_EQUALS, T_SHR_ASSIGN, T_SHR)
        return followed_by(C_EQUALS, T_GE, T_GT)
    if c == C_BANG and src.ch == C_EQUALS:
        src.advance()
        return T_NE
    err.fatal(err.E_BAD_CHAR)
    return T_EOF


def saved_token():
    """Read one token from the saved token run that is the top source. Its end is T_EOF, at the
    place of the token before it."""
    global tok, value, line, col, string_length
    while not src.eof and src.ch == SAVED_LINE:
        src.next_byte()
        src.line += src.next_byte()
    if src.eof:
        tok = T_EOF
        return
    line = src.line
    tok = src.next_byte()
    col = src.next_byte()
    err.position(line, col)
    if tok == T_NAME or tok == T_NUMBER:
        value = src.next_byte()
        value = value | (src.next_byte() << 8)
    elif tok == T_STRING:
        string_length = src.next_byte()
        for i in range(0, string_length):
            string[i] = src.next_byte()


def scan():
    """Read one token, taking every line end as a token."""
    global tok, value, line, col, string_length, end_line
    if src.replaying:
        saved_token()
        return
    if end_line != 0:
        tok = T_NL
        line = end_line
        col = end_col
        end_line = 0
        err.position(line, col)
        return
    skip_blanks()
    line = src.line
    col = src.col
    err.position(line, col)
    if src.eof:
        if nesting != 0:
            err.fatal(err.E_IF_OPEN)
        tok = T_EOF
        return
    c = src.ch
    if is_letter(c):
        name_or_keyword()
        return
    if is_digit(c):
        tok = T_NUMBER
        value = number(10)
        return
    src.advance()
    if c == C_LF:
        tok = T_NL
    elif c == C_DOLLAR:
        tok = T_NUMBER
        value = number(16)
    elif c == C_PERCENT:
        tok = T_NUMBER
        value = number(2)
    elif c == C_QUOTE:
        tok = T_NUMBER
        value = character()
    elif c == C_DQUOTE:
        tok = T_STRING
        string_length = 0
        string_token()
        string_pieces()
    elif c == C_HASH:
        directive()
    else:
        tok = mark(c)


def joins_lines(token):
    """True if a line that ends with `token` continues on the next: binary operators and the comma."""
    if token >= T_PLUS and token <= T_GE:
        return True
    return token == T_COMMA or token == T_AND or token == T_OR or token == T_MOD


def next():
    """Make the next token the current one."""
    global tok, open_brackets
    before = tok
    scan()
    while tok == T_NL and (before == T_NL or open_brackets > 0 or joins_lines(before)):
        scan()
    if tok == T_EOF and before != T_NL and before != T_EOF:
        tok = T_NL              # the last line ends even without a newline, and whatever is open
    elif tok == T_LPAREN or tok == T_LBRACKET:
        open_brackets += 1
    elif (tok == T_RPAREN or tok == T_RBRACKET) and open_brackets > 0:
        open_brackets -= 1


def expect(token, number):
    """Pass over the current token if it is `token`; if not, that is error `number`."""
    if tok != token:
        err.fatal(number)
    next()


def resume(token, at_line, at_col):
    """Make `token`, found at that place, the current token. ASM reads the lines of an `asm`
    block itself and gives back the `end` that closes it, with the source just after it."""
    global tok, line, col
    tok = token
    line = at_line
    col = at_col
    err.position(line, col)
