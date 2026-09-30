"""Lexer for the Prog8 subset.

Produces a flat list of Token objects. Multi-char tokens (==, !=, <=,
>=, <<, >>, ++, --, +=, -=, *=, /=, &=, |=, ^=, <<=, >>=, ->, &&) are
recognized as single tokens. Strings honor \\n \\r \\" \\\\ \\xHH; no
\\u yet -- we stay 7-bit ASCII until Phase 2 adds encoding pragmas.

Whitespace and ;-comments are dropped; newlines are dropped too --
Prog8 is whitespace-insensitive once you're inside a block.
"""
from __future__ import annotations

from dataclasses import dataclass


KEYWORDS = {
    "sub", "asmsub", "extsub", "inline", "private", "defer",
    "if", "else", "when", "while", "do", "until", "for", "in", "to",
    "downto", "step", "repeat", "break", "continue", "return", "goto",
    "as", "and", "or", "xor", "not",
    "true", "false",
    "ubyte", "byte", "uword", "word", "bool", "str", "void",
    "const", "enum", "struct",
    "main",
}


@dataclass
class Token:
    kind: str          # 'INT' 'STR' 'IDENT' 'KW' or punctuation/op like '+', '==', ...
    value: object      # int / str / identifier text
    line: int
    col: int

    def __repr__(self) -> str:
        return f"Token({self.kind!r}, {self.value!r}, {self.line}:{self.col})"


class LexError(Exception):
    pass


_MULTI_CHARS = sorted(
    [
        "<<=", ">>=", "==", "!=", "<=", ">=", "<<", ">>",
        "++", "--", "+=", "-=", "*=", "/=", "&=", "|=", "^=", "->", "&&",
    ],
    key=len, reverse=True,
)

_SINGLE = set("()[]{},.:;+-*/%&|^~<>=!@?")


def lex(src: str, filename: str = "<input>") -> list[Token]:
    out: list[Token] = []
    i = 0
    line = 1
    col = 1
    n = len(src)

    def loc():
        return line, col

    def advance(k: int = 1) -> None:
        nonlocal i, line, col
        for _ in range(k):
            if i < n and src[i] == "\n":
                line += 1
                col = 1
            else:
                col += 1
            i += 1

    while i < n:
        c = src[i]
        # whitespace + ;-comment
        if c in " \t\r\n":
            advance()
            continue
        if c == ";":
            while i < n and src[i] != "\n":
                advance()
            continue
        # %word -- directive (lowercased)
        if c == "%" and i + 1 < n and (src[i + 1].isalpha() or src[i + 1] == "_"):
            l0, c0 = loc()
            advance()
            j = i
            while j < n and (src[j].isalnum() or src[j] == "_"):
                j += 1
            name = src[i:j]
            advance(j - i)
            out.append(Token("DIRECTIVE", name, l0, c0))
            # `%asm {{ ... }}` -- the upstream / register-ABI raw form: when the
            # `{{` body is NOT a quoted string, capture it and normalize it
            # (strip each line, drop blank lines) into a single STR token, then
            # synthesize the `{{ STR }}` token shape the parser already expects.
            # The LEGACY quoted form (`%asm{{ "..." }}`, body IS a string) is
            # left to normal tokenization, so it lexes byte-for-byte as before.
            if name == "asm":
                k = i
                while k < n and src[k] in " \t\r\n":
                    k += 1
                if src.startswith("{{", k):
                    m = k + 2
                    while m < n and src[m] in " \t\r\n":
                        m += 1
                    if m < n and src[m] == '"':
                        raise LexError(
                            f"{filename}:{l0}:{c0}: the quoted inline-asm form "
                            f'`%asm{{{{ \"...\" }}}}` is retired; use the raw '
                            f"`%asm {{{{ ... }}}}` form")
                    advance(k - i + 2)              # consume up to + incl `{{`
                    bl, bc = loc()
                    end = src.find("}}", i)
                    if end == -1:
                        raise LexError(
                            f"{filename}:{bl}:{bc}: unterminated %asm {{{{ block")
                    body = "\n".join(
                        ln.strip() for ln in src[i:end].split("\n")
                        if ln.strip())
                    advance(end - i + 2)            # consume body + `}}`
                    out.append(Token("{", "{", bl, bc))
                    out.append(Token("{", "{", bl, bc))
                    out.append(Token("STR", body, bl, bc))
                    out.append(Token("}", "}", bl, bc))
                    out.append(Token("}", "}", bl, bc))
            continue
        # numeric literal: $ff, %1010, 42
        if c == "$" and i + 1 < n and src[i + 1] in "0123456789abcdefABCDEF":
            l0, c0 = loc()
            advance()
            j = i
            while j < n and src[j] in "0123456789abcdefABCDEF_":
                j += 1
            text = src[i:j].replace("_", "")
            try:
                v = int(text, 16)
            except ValueError as e:
                raise LexError(f"{filename}:{l0}:{c0}: bad hex literal {text!r}: {e}")
            advance(j - i)
            out.append(Token("INT", v, l0, c0))
            continue
        if c == "%" and i + 1 < n and src[i + 1] in "01":
            l0, c0 = loc()
            advance()
            j = i
            while j < n and src[j] in "01_":
                j += 1
            text = src[i:j].replace("_", "")
            advance(j - i)
            out.append(Token("INT", int(text, 2), l0, c0))
            continue
        if c.isdigit():
            l0, c0 = loc()
            j = i
            while j < n and (src[j].isdigit() or src[j] == "_"):
                j += 1
            text = src[i:j].replace("_", "")
            advance(j - i)
            out.append(Token("INT", int(text, 10), l0, c0))
            continue
        # character literal: 'X' or '\n' -> INT token with ASCII value.
        if c == "'":
            l0, c0 = loc()
            advance()
            if i >= n:
                raise LexError(f"{filename}:{l0}:{c0}: unterminated char literal")
            ch = src[i]
            if ch == "\\":
                if i + 1 >= n:
                    raise LexError(f"{filename}:{line}:{col}: bad escape in char")
                e = src[i + 1]
                advance(2)
                m = {"n": "\n", "r": "\r", "t": "\t", "0": "\0",
                     "'": "'", "\\": "\\", '"': '"'}
                if e in m:
                    val = ord(m[e])
                elif e == "x":
                    if i + 2 > n:
                        raise LexError(f"{filename}:{line}:{col}: \\x needs 2 hex")
                    val = int(src[i:i + 2], 16)
                    advance(2)
                else:
                    raise LexError(f"{filename}:{line}:{col}: bad char escape \\{e}")
            else:
                val = ord(ch)
                advance()
            if i >= n or src[i] != "'":
                raise LexError(f"{filename}:{line}:{col}: char literal not closed")
            advance()
            out.append(Token("INT", val, l0, c0))
            continue
        # string literal
        if c == '"':
            l0, c0 = loc()
            advance()
            buf: list[str] = []
            while i < n and src[i] != '"':
                ch = src[i]
                if ch == "\\":
                    if i + 1 >= n:
                        raise LexError(f"{filename}:{line}:{col}: unterminated escape")
                    e = src[i + 1]
                    advance(2)
                    if e == "n": buf.append("\n")
                    elif e == "r": buf.append("\r")
                    elif e == "t": buf.append("\t")
                    elif e == "0": buf.append("\0")
                    elif e == '"': buf.append('"')
                    elif e == "\\": buf.append("\\")
                    elif e == "x":
                        if i + 1 >= n:
                            raise LexError(f"{filename}:{line}:{col}: \\x needs 2 hex digits")
                        hexpair = src[i:i + 2]
                        try:
                            buf.append(chr(int(hexpair, 16)))
                        except ValueError as exc:
                            raise LexError(f"{filename}:{line}:{col}: bad \\x escape: {exc}")
                        advance(2)
                    else:
                        raise LexError(f"{filename}:{line}:{col}: unknown escape \\{e}")
                else:
                    buf.append(ch)
                    advance()
            if i >= n:
                raise LexError(f"{filename}:{l0}:{c0}: unterminated string literal")
            advance()  # closing "
            out.append(Token("STR", "".join(buf), l0, c0))
            continue
        # identifier / keyword
        if c.isalpha() or c == "_":
            l0, c0 = loc()
            j = i
            while j < n and (src[j].isalnum() or src[j] == "_"):
                j += 1
            text = src[i:j]
            advance(j - i)
            if text in KEYWORDS:
                out.append(Token("KW", text, l0, c0))
            else:
                out.append(Token("IDENT", text, l0, c0))
            continue
        # multi-char operators
        matched = False
        for mc in _MULTI_CHARS:
            if src.startswith(mc, i):
                l0, c0 = loc()
                advance(len(mc))
                out.append(Token(mc, mc, l0, c0))
                matched = True
                break
        if matched:
            continue
        # single-char punctuation / operator
        if c in _SINGLE:
            l0, c0 = loc()
            advance()
            out.append(Token(c, c, l0, c0))
            continue
        raise LexError(f"{filename}:{line}:{col}: unexpected character {c!r}")

    out.append(Token("EOF", None, line, col))
    return out
