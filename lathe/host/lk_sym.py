"""Symbols as references: what a `module.name` the object files define or refer to stands for.

There is no table of symbols. A symbol is known by a reference, a word: its kind in the top
three bits and below them the row of what defines it, in lk_tab.fn_ (a function), lk_tab.def_ (a
variable or constant data) or lk_tab.cls_ (a pointer class). A symbol nothing defines has UNDEF
set and a number of its own below it. While the files are read every symbol is known by such a
number, and lk_name holds what it has become so far; once they are read every reference is
replaced by what it stands for (lk_name.resolve). lk_name.local holds the reference each object
file's symbol numbers stand for.

A call names a function or a class in 13 bits (lk_tab.edge_word): edge_bits and edge_ref.
"""
import lk_err

MAX_SYMS = 1600                     # below 2048: a call holds a symbol's number in 11 bits

FUNCTION = 1
VARIABLE = 2
CONSTANT = 3
CLASS = 4
KIND_SHIFT = 13
UNDEF = 0x1000                      # nothing defines it (yet): its number is below
ROW = 0x0FFF
EDGE_CLASS = 0x0800                 # in a call: the symbol is a class
EDGE_ROW = 0x07FF

count = 0                           # symbols so far


def new_number():
    """The number of a new symbol."""
    global count
    if count == MAX_SYMS:
        lk_err.fail(lk_err.E_SYMBOLS)
    count += 1
    return count - 1


def ref(kind, index):
    """The reference of row `index` of the table of this kind."""
    return (kind << KIND_SHIFT) | index


def kind_of(r):
    return r >> KIND_SHIFT


def row_of(r):
    """The row of what defines symbol r."""
    return r & ROW


def is_defined(r):
    return (r & UNDEF) == 0


def edge_bits(r):
    """Function or class r as a call names it."""
    b = r & (UNDEF | EDGE_ROW)
    if kind_of(r) == CLASS:
        b |= EDGE_CLASS
    return b


def edge_ref(b):
    """The function or class that a call naming it as `b` calls."""
    if (b & EDGE_CLASS) != 0:
        return ref(CLASS, b & (UNDEF | EDGE_ROW))
    return ref(FUNCTION, b & (UNDEF | EDGE_ROW))
