"""The type table.

Owns the types of the module being compiled. A type is known by its number in the table. The
basic types have fixed numbers; a type made from others (a pointer or an array; records and
named types will follow) gets the next free one, and is made only once, so two types are the
same type exactly when their numbers are equal. An array is stored by column or, if declared
`rows`, by row (docs/language.md, "Arrays and their layout"): the two are different types.

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
NIL_TYPE = 8               # `nil`, which fits every pointer type
FIRST_MADE = 9

FORM_BASIC = 0
FORM_POINTER = 1        # base: the type pointed to
FORM_ARRAY = 2          # base: the element type; length: how many. Stored by column
FORM_ROWS = 3           # the same, declared `rows`: each element's bytes together

form = [0] * MAX_TYPES
base_type = [0] * MAX_TYPES
type_length = [0] * MAX_TYPES
type_size = [0] * MAX_TYPES
count = FIRST_MADE

# A type written as prefixes, `^` and `[n]`, before what they apply to is built from the inside
# out: the prefixes wait here, and build() applies them.
MAX_PREFIXES = 16
prefix_form = [0] * MAX_PREFIXES
prefix_length = [0] * MAX_PREFIXES
prefix_count = 0


def init():
    global count, prefix_count
    count = FIRST_MADE
    prefix_count = 0
    for t in range(0, FIRST_MADE):
        form[t] = FORM_BASIC
        type_size[t] = 2
    type_size[BYTE_TYPE] = 1
    type_size[SBYTE_TYPE] = 1
    type_size[BOOL_TYPE] = 1


def size(t):
    """Bytes a value of type `t` takes."""
    return type_size[t]


def is_pointer(t):
    return form[t] == FORM_POINTER


def is_array(t):
    return form[t] == FORM_ARRAY or form[t] == FORM_ROWS


def is_rows(t):
    return form[t] == FORM_ROWS


def base(t):
    """The type a pointer type points to, or the element type of an array."""
    return base_type[t]


def length(t):
    """How many elements an array type has."""
    return type_length[t]


def is_column(t):
    """True for an array whose elements are stored by column: they are larger than a byte."""
    return form[t] == FORM_ARRAY and size(base_type[t]) > 1


def made(kind, t, n):
    """The type of this form made from `t` (and `n` elements, for an array)."""
    global count
    for p in range(FIRST_MADE, count):
        if form[p] == kind and base_type[p] == t and type_length[p] == n:
            return p
    if count == MAX_TYPES:
        err.fatal(err.E_TYPES_FULL)
    if n != 0 and size(t) > 0xFFFF // n:
        err.fatal(err.E_RANGE)
    form[count] = kind
    base_type[count] = t
    type_length[count] = n
    type_size[count] = 2
    if kind != FORM_POINTER:
        type_size[count] = n * size(t)
    count += 1
    return count - 1


def pointer_to(t):
    """The type `^t`."""
    return made(FORM_POINTER, t, 0)


def prefix(kind, n):
    """A prefix of the type being read: FORM_POINTER, or FORM_ARRAY or FORM_ROWS of `n`
    elements. Returns how many prefixes waited before it."""
    global prefix_count
    if prefix_count == MAX_PREFIXES:
        err.fatal(err.E_TYPES_FULL)
    prefix_form[prefix_count] = kind
    prefix_length[prefix_count] = n
    prefix_count += 1
    return prefix_count - 1


def build(t, mark):
    """The type that the prefixes from number `mark` on make of `t`. They are used up."""
    global prefix_count
    while prefix_count > mark:
        prefix_count -= 1
        t = made(prefix_form[prefix_count], t, prefix_length[prefix_count])
    return t


def array_of(t, n, by_row):
    """The type `[n]t`, stored by row if `by_row`."""
    if by_row:
        return made(FORM_ROWS, t, n)
    return made(FORM_ARRAY, t, n)


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
