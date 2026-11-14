"""The lexer's test driver over the host lexer: lathe/src/lextest.lth in Python, printing the
same lines for the same source (see the top of lextest.lth for the format, and for what is done
after `#if` and `asm`). Run as `python3 lathe/tests/lextest_host.py SOURCE.lth`, or call
main() after env.start()."""
import os
import sys

HOST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'host')
if HOST not in sys.path:
    sys.path.append(HOST)

import env  # noqa: E402
import err  # noqa: E402
import kernel  # noqa: E402
import lex  # noqa: E402
import src  # noqa: E402

HEX = b'0123456789ABCDEF'
C_LF = 0x0A
MAX_WORD = 4


def put_hex(b):
    env.put_byte(HEX[b >> 4])
    env.put_byte(HEX[b & 15])


def put_word(w):
    put_hex((w >> 8) & 0xFF)
    put_hex(w & 0xFF)


quiet = False


def show():
    if quiet:
        return
    put_hex(lex.tok)
    env.put_byte(0x20)
    put_word(lex.line)
    env.put_byte(0x20)
    put_word(lex.col)
    if lex.tok == lex.T_NAME:
        env.put_byte(0x20)
        for i in range(kernel.name_length(lex.value)):
            env.put_byte(kernel.name_char(lex.value, i))
    elif lex.tok == lex.T_NUMBER:
        env.put_byte(0x20)
        put_word(lex.value)
    elif lex.tok == lex.T_STRING:
        env.put_byte(0x20)
        put_hex(lex.string_length)
        for i in range(lex.string_length):
            env.put_byte(0x20)
            put_hex(lex.string[i])
    env.put_byte(C_LF)


def asm_lines():
    while True:
        while not src.eof and src.ch in (0x20, 9, 13):
            src.advance()
        if src.eof:
            err.position(src.line, src.col)
            err.fatal(err.E_END_EXPECTED)
        at_line, at_col = src.line, src.col
        word = b''
        while not src.eof and (lex.is_letter(src.ch) or lex.is_digit(src.ch) or src.ch == 0x5F):
            if len(word) < MAX_WORD:
                word += bytes([lex.fold(src.ch)])
            src.advance()
        if word == b'end':
            lex.resume(lex.T_END, at_line, at_col)
            return
        while not src.eof and src.ch != C_LF:
            src.advance()
        src.advance()


def main():
    global quiet
    err.init()
    kernel.init()
    src.init()
    lex.init()
    if env.argc() == 0:
        err.fatal(err.E_USAGE)
    source = kernel.keep_argument(0)
    quiet = env.argc() > 1
    err.set_file(source)
    if not src.open_file(source):
        err.fatal(err.E_OPEN_SOURCE)
    ifs = 0
    if_open = asm_open = False
    while True:
        lex.next()
        show()
        if lex.tok == lex.T_EOF:
            break
        if lex.tok == lex.T_ASM:
            asm_open = True
        elif lex.tok == lex.T_HASH_IF:
            if_open = True
        elif lex.tok == lex.T_NL and if_open:
            if_open = False
            lex.choose(ifs & 1 == 1)
            ifs = (ifs + 1) & 0xFF
        elif lex.tok == lex.T_NL and asm_open:
            asm_open = False
            asm_lines()
            show()
    env.exit(0)


if env.is_program(__name__):
    main()
