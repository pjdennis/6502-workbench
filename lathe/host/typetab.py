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
NUMBER_TYPE = 6            # a number of no type yet, zero or above: it takes the type its place needs
NEGATIVE_TYPE = 7          # the same, below zero: held as 16 bits in two's complement
FIRST_MADE = 8

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


def is_untyped(t):
    """True for a constant that has not taken a type yet."""
    return t == NUMBER_TYPE or t == NEGATIVE_TYPE


def is_signed(t):
    """True for the types whose values can be below zero. Such a constant is held sign-extended
    to 16 bits, whatever its size."""
    return t == SBYTE_TYPE or t == INT_TYPE or t == NEGATIVE_TYPE


def limit(t):
    """The largest value of number type `t`."""
    if t == BYTE_TYPE:
        return 0xFF
    if t == SBYTE_TYPE:
        return 0x7F
    if t == INT_TYPE:
        return 0x7FFF
    return 0xFFFF


def number_fits(value, negative, t):
    """True if the untyped number `value`, which is below zero if `negative`, can be a `t`."""
    if negative:
        return t == INT_TYPE or (t == SBYTE_TYPE and value >= 0xFF80)
    return is_number(t) and value <= limit(t)


def narrow(value, t):
    """`value` cut to what a `t` holds: the low byte for the one-byte types, with the sign
    carried up to 16 bits for `sbyte`."""
    if size(t) == 2:
        return value & 0xFFFF
    value = value & 0xFF
    if t == SBYTE_TYPE and value >= 0x80:
        value = value | 0xFF00
    return value
