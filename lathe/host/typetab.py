"""The type table.

Owns the types of the module being compiled. A type is known by its number in the table. The
basic types have fixed numbers; a type made from others (today only a pointer; arrays, records
and named types will follow) gets the next free one, and is made only once, so two types are
the same type exactly when their numbers are equal.

This is the component docs name `types`; the file cannot be called types.py, which would hide
Python's own module of that name from everything else on the path.
"""
import err

MAX_TYPES = 64

NO_TYPE = 0                # no type
BYTE_TYPE = 1
SBYTE_TYPE = 2
WORD_TYPE = 3
INT_TYPE = 4
BOOL_TYPE = 5
NUMBER_TYPE = 6              # a number written in the source, which takes the type its place needs
FIRST_MADE = 7

FORM_BASIC = 0
FORM_POINTER = 1        # base: the type pointed to

form = [0] * MAX_TYPES
base_type = [0] * MAX_TYPES
count = FIRST_MADE


def init():
    global count
    count = FIRST_MADE
    for t in range(0, FIRST_MADE):
        form[t] = FORM_BASIC


def size(t):
    """Bytes a value of type `t` takes."""
    if t == BYTE_TYPE or t == SBYTE_TYPE or t == BOOL_TYPE:
        return 1
    return 2


def is_pointer(t):
    return form[t] == FORM_POINTER


def base(t):
    """The type a pointer type points to."""
    return base_type[t]


def pointer_to(t):
    """The type `^t`."""
    global count
    for p in range(FIRST_MADE, count):
        if form[p] == FORM_POINTER and base_type[p] == t:
            return p
    if count == MAX_TYPES:
        err.fatal(err.E_TYPES_FULL)
    form[count] = FORM_POINTER
    base_type[count] = t
    count += 1
    return count - 1


def is_number(t):
    """True for the types a number can be given to."""
    return t == BYTE_TYPE or t == SBYTE_TYPE or t == WORD_TYPE or t == INT_TYPE


def number_fits(value, t):
    """True if the number `value`, as written in the source, can be a `t`."""
    if t == BYTE_TYPE:
        return value <= 0xFF
    if t == SBYTE_TYPE:
        return value <= 0x7F
    if t == INT_TYPE:
        return value <= 0x7FFF
    return t == WORD_TYPE
