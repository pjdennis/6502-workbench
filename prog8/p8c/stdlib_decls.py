"""Stdlib symbol declarations.

The actual implementation lives in `stdlib/*.p8` (eventually a mix of
Prog8 source and inline-asm wrappers around the repo's existing .inc
helpers). For Phase 1 we just declare the symbols and let codegen emit
JSRs to fixed entry points exported by the wendy2c boot ROM / include
files.
"""
from __future__ import annotations

from .ast import Symbol, BYTE, STR, UBYTE, UWORD, VOID


# txt.print(str) -- print zero-terminated string at the LCD cursor.
# Lowers to: lda #<str ; ldx #>str ; jsr display_string.
TXT_PRINT = Symbol(
    name="print", mangled="display_string", type=VOID, kind="extsub",
    asm_target="display_string",
)

# lcd.clear() -- clear LCD and home cursor.
LCD_CLEAR = Symbol(
    name="clear", mangled="clear_display", type=VOID, kind="extsub",
    asm_target="clear_display",
)


# txt.print_ub(b) -- print byte as 2 ASCII hex chars (display_hex.inc).
TXT_PRINT_UB = Symbol(
    name="print_ub", mangled="display_hex", type=VOID, kind="extsub",
    asm_target="display_hex",
)


# txt.print_uw(w) -- print uword as 4 hex chars (high byte first).
# No standalone .inc helper; codegen inlines a two-call sequence using
# display_hex twice.
TXT_PRINT_UW = Symbol(
    name="print_uw", mangled="__p8c_print_uw", type=VOID, kind="extsub",
    asm_target="__p8c_print_uw",
)


# Builtins (kind="builtin") -- codegen has special-cased lowering for
# each. Calls look like `peek($f001)` etc. (unqualified, not dotted).
# `type` is the return type (UBYTE for peek; VOID for poke / for the
# stmt-only forms).
BUILTINS = [
    Symbol(name="peek",   mangled="peek",   type=UBYTE, kind="builtin"),
    Symbol(name="poke",   mangled="poke",   type=VOID,  kind="builtin"),
    Symbol(name="peekw",  mangled="peekw",  type=UWORD, kind="builtin"),
    Symbol(name="pokew",  mangled="pokew",  type=VOID,  kind="builtin"),
    Symbol(name="lsb",    mangled="lsb",    type=UBYTE, kind="builtin"),
    Symbol(name="msb",    mangled="msb",    type=UBYTE, kind="builtin"),
    Symbol(name="mkword", mangled="mkword", type=UWORD, kind="builtin"),
    Symbol(name="len",    mangled="len",    type=UBYTE, kind="builtin"),
    Symbol(name="sizeof", mangled="sizeof", type=UBYTE, kind="builtin"),
]


# strings.compare(a, b) -> byte: idiomatic zero-terminated string compare,
# returning -1 / 0 / 1 (a<b / a==b / a>b), like upstream Prog8. Operands are
# uword addresses (string literals, &buffer, or a uword pointer). kind="builtin"
# so codegen lowers it to a JSR to the lazily-emitted __p8c_strcmp helper.
STRINGS_COMPARE = Symbol(
    name="compare", mangled="__p8c_strcmp", type=BYTE, kind="builtin",
)


STDLIB_SYMBOLS: dict[str, list[Symbol]] = {
    "txt": [TXT_PRINT, TXT_PRINT_UB, TXT_PRINT_UW],
    "lcd": [LCD_CLEAR],
    "strings": [STRINGS_COMPARE],
}


def get_builtin(name: str) -> Symbol | None:
    """Builtins are always in scope (no `%import` needed)."""
    for sym in BUILTINS:
        if sym.name == name:
            return sym
    return None
