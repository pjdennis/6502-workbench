"""FOLD: constant arithmetic.

Owns the numbers of the operators, which EXPR gives to GEN, and what each operator gives for
two constants.

A constant is 16 bits and a type. A number that has no type yet is exact: it is anywhere
from -32768 to 65535, a result outside that is an error, and whether it is below zero is told
by its type (typetab.NUMBER_TYPE or NEGATIVE_TYPE). A constant of a type wraps as a variable
of that type would. Values below zero are held in two's complement, sign-extended to 16 bits.
Exact arithmetic is done on sign and size, so nothing here needs more than 16 bits.
"""
import err
import typetab

# Operators. ADD to SHR are in the order of the compound assignment tokens `+=` to `>>=`.
ADD = 1
SUB = 2
BAND = 3
BOR = 4
BXOR = 5
SHL = 6
SHR = 7
MUL = 8
DIV = 9
REM = 10
EQ = 11
NE = 12
LT = 13
GE = 14
GT = 15
LE = 16

SIGN = 0x8000


def magnitude(value, negative):
    """The size of a number without its sign."""
    if negative:
        return (0 - value) & 0xFFFF
    return value


def signed_number(size, negative):
    """The exact number of this size and sign, and whether it is below zero."""
    if size == 0:
        return 0, False
    if not negative:
        return size, False
    if size > SIGN:
        err.fatal(err.E_RANGE)
    return (0 - size) & 0xFFFF, True


def sum_exact(size, negative, other, other_negative):
    """The sum of two numbers given as size and sign."""
    if negative == other_negative:
        total = (size + other) & 0xFFFF
        if total < size:
            err.fatal(err.E_RANGE)
        return signed_number(total, negative)
    if size >= other:
        return signed_number(size - other, negative)
    return signed_number(other - size, other_negative)


def product_exact(size, other, negative):
    if other != 0 and size > 0xFFFF // other:
        err.fatal(err.E_RANGE)
    return signed_number(size * other, negative)


def quotient(op, size, other):
    """`size` divided by `other`, or what is left over: both without signs."""
    if other == 0:
        err.fatal(err.E_DIV_ZERO)
    if op == DIV:
        return size // other
    return size % other


def bitwise(op, left, right):
    if op == BAND:
        return left & right
    if op == BOR:
        return left | right
    return left ^ right


def bitwise_exact(op, left, left_negative, right, right_negative):
    """Bit by bit, as if both numbers had endless sign bits."""
    result = bitwise(op, left, right)
    negative = left_negative != right_negative
    if op == BAND:
        negative = left_negative and right_negative
    elif op == BOR:
        negative = left_negative or right_negative
    if negative and result < SIGN:
        err.fatal(err.E_RANGE)          # below -32768
    return result, negative


def shifted_left(value, count):
    if count > 15:
        return 0
    return (value << count) & 0xFFFF


def shifted_right(value, negative, count):
    """Shifted right with the sign kept: the number divided by a power of two, rounded down."""
    if negative:
        if count > 15:
            return 0xFFFF
        return (~((~value & 0xFFFF) >> count)) & 0xFFFF
    if count > 15:
        return 0
    return value >> count


def shift_exact(op, left, negative, count):
    if op == SHR:
        return shifted_right(left, negative, count), negative
    size = magnitude(left, negative)
    if size != 0 and (count > 15 or size > (0xFFFF >> count)):
        err.fatal(err.E_RANGE)
    return signed_number(shifted_left(size, count), negative)


def exact(op, left, left_negative, right, right_negative):
    """`left op right` for two numbers without a type (for a shift, `right` is the count).
    Returns the number and whether it is below zero."""
    if op == SHL or op == SHR:
        return shift_exact(op, left, left_negative, right)
    if op == BAND or op == BOR or op == BXOR:
        return bitwise_exact(op, left, left_negative, right, right_negative)
    size = magnitude(left, left_negative)
    other = magnitude(right, right_negative)
    if op == ADD:
        return sum_exact(size, left_negative, other, right_negative)
    if op == SUB:
        return sum_exact(size, left_negative, other, not right_negative)
    if op == MUL:
        return product_exact(size, other, left_negative != right_negative)
    if op == DIV:
        return signed_number(quotient(op, size, other), left_negative != right_negative)
    return signed_number(quotient(op, size, other), left_negative)


def typed(op, t, left, right):
    """`left op right` for two constants of type `t` (for a shift, `right` is the count).
    Wraps as the type does."""
    left_negative = typetab.is_signed(t) and left >= SIGN
    right_negative = typetab.is_signed(t) and right >= SIGN
    if op == ADD:
        result = left + right
    elif op == SUB:
        result = left - right
    elif op == MUL:
        result = left * right           # the low 16 bits are those of a 16-bit multiply
    elif op == SHL:
        result = shifted_left(left, right)
    elif op == SHR:
        result = shifted_right(left, left_negative, right)
    elif op == DIV or op == REM:
        result = quotient(op, magnitude(left, left_negative), magnitude(right, right_negative))
        if (op == DIV and left_negative != right_negative) or (op == REM and left_negative):
            result = 0 - result
    else:
        result = bitwise(op, left, right)
    return typetab.narrow(result & 0xFFFF, t)


def compare(op, left, left_negative, right, right_negative):
    """What a comparison of two constants gives."""
    equal = left == right and left_negative == right_negative
    less = left < right
    if left_negative != right_negative:
        less = left_negative
    if op == EQ:
        return equal
    if op == NE:
        return not equal
    if op == LT:
        return less
    if op == GE:
        return not less
    if op == GT:
        return not less and not equal
    return less or equal
