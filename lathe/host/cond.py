"""COND: comparisons and conditions (the middle one of GEN's three files).

Owns the code for everything that is a `bool` (docs/codegen.md, "Comparisons and
conditions"). A comparison leaves its answer in the flags and pushes a Condition: the branch
that is taken when it is true, and two labels that earlier parts of the test already go to,
one for true and one for false. `and`, `or` and `not` only move those labels about, so a
whole test becomes branches and nothing else. A Condition is used up at once: by a branch
(jump_false), or by becoming 0 or 1 in A (value) or the carry flag (carry). Whatever an
operation here has to store first is stored before its first branch, so that it is stored
on every path.

A condition that is known when compiling is a Condition too, with ALWAYS or NEVER for its
branch, so no case below has to treat constants apart.
"""
import err
import fbuf
import fold
import reg
import typetab

# The branch of a condition that is known without a test. Real branch opcodes are larger.
NEVER = 0
ALWAYS = 1

OP_BMI = 0x30
OP_BVC = 0x50
OP_BCC = 0x90
OP_BCS = 0xB0
OP_BNE = 0xD0
OP_BEQ = 0xF0
FLIP = 0x20         # the bit that differs between a branch and its opposite
SIGN_BIT = 0x80
F_COMPARED = 4          # a flag of a Condition, beside reg.F_TEMP and reg.F_ZP: it is "Z set"
#                         after a CMP, which has set the carry flag too if it is true

for_carry = False       # True while the test being compiled is wanted in the carry flag: a
#                         comparison then prefers the form that is true with the carry set


# ---- Conditions --------------------------------------------------------------------------

def wanted_in_carry(yes):
    """Say whether the tests compiled from now on are wanted in the carry flag."""
    global for_carry
    for_carry = yes


def push(branch):
    """Add a Condition that is true when `branch` would be taken."""
    reg.push(reg.O_COND, typetab.BOOL_TYPE, branch)


def opposite(branch):
    if branch <= ALWAYS:
        return branch ^ ALWAYS
    return branch ^ FLIP


def go(branch, target):
    """Go to label `target` when `branch` would be taken."""
    if branch == ALWAYS:
        fbuf.jump(target)
    elif branch != NEVER:
        fbuf.branch(branch, target)


def joined(target, other):
    """One label for two that mean the same place; either may be reg.NONE."""
    if target == reg.NONE:
        return other
    if other != reg.NONE:
        fbuf.join(target, other)
    return target


def make(i):
    """Make operand `i`, which must be a `bool`, a Condition."""
    if reg.op_type[i] != typetab.BOOL_TYPE:
        err.fatal(err.E_TYPE)
    if reg.op_kind[i] == reg.O_CONST:
        reg.op_kind[i] = reg.O_COND             # NEVER and ALWAYS are false and true
    elif reg.op_kind[i] != reg.O_COND:
        reg.release(i)
        reg.test_byte(i, 0)
        reg.become(i, reg.O_COND, typetab.BOOL_TYPE)
        reg.op_value[i] = OP_BNE


def is_plain(i):
    """True if Condition `i` is only a state of the flags: nothing branches for it yet."""
    return reg.op_true[i] == reg.NONE and reg.op_false[i] == reg.NONE


def leave(i, wanted):
    """Branch away when Condition `i` is not `wanted`, and go on here when it is. Returns
    the label branched to, which is still to be placed, or reg.NONE if nothing goes away:
    the condition is known to be as wanted."""
    target = reg.op_true[i]
    here = reg.op_false[i]
    branch = reg.op_value[i]
    if wanted:
        target = reg.op_false[i]
        here = reg.op_true[i]
        branch = opposite(branch)
    if target == reg.NONE and branch != NEVER:
        target = fbuf.new_label()
    go(branch, target)
    if here != reg.NONE:
        reg.label(here)
    return target


def away(i, wanted):
    """As leave(), but always returns a label."""
    target = leave(i, wanted)
    if target == reg.NONE:
        target = fbuf.new_label()
    return target


def jump_false():
    """Use up the newest operand as a test: go on here when it is true. Returns the label
    that is gone to when it is false."""
    make(reg.depth - 1)
    target = away(reg.depth - 1, True)
    reg.pop()
    return target


def left(wanted):
    """The left side of `and` (`wanted` True) or `or` (False) is the newest operand: go on
    to the right side only when it is `wanted`. What is left on the stack remembers the label
    for the other case."""
    i = reg.depth - 1
    make(i)
    if reg.op_value[i] <= ALWAYS:
        reg.claim(reg.A)        # the right side may never be run: it cannot be what stores A
    target = leave(i, wanted)
    reg.op_true[i] = reg.NONE
    reg.op_false[i] = reg.NONE
    if wanted:
        reg.op_value[i] = ALWAYS
        reg.op_false[i] = target
    else:
        reg.op_value[i] = NEVER
        reg.op_true[i] = target


def right():
    """The right side of `and` or `or` is the newest operand and what left() made is under
    it: the result is the right side, with the left side's label joined to its own."""
    i = reg.depth - 1
    make(i)
    reg.op_true[i] = joined(reg.op_true[i - 1], reg.op_true[i])
    reg.op_false[i] = joined(reg.op_false[i - 1], reg.op_false[i])
    reg.squeeze()


def invert():
    """`not` of the newest operand: true and false change places."""
    i = reg.depth - 1
    make(i)
    target = reg.op_true[i]
    reg.op_true[i] = reg.op_false[i]
    reg.op_false[i] = target
    reg.op_value[i] = opposite(reg.op_value[i])


def value():
    """If the newest operand is a Condition, make it a value: 0 or 1 in A, or a constant."""
    i = reg.depth - 1
    if reg.op_kind[i] != reg.O_COND:
        return
    branch = reg.op_value[i]
    if is_plain(i) and branch <= ALWAYS:
        reg.op_kind[i] = reg.O_CONST
        return
    reg.claim(reg.A)                            # before any branch: both ways need it done
    if is_plain(i) and (branch == OP_BCS or branch == OP_BCC):
        reg.load_const(reg.A, 0)                # leaves the carry flag alone
        reg.accumulator(reg.OP_ROL)
        if branch == OP_BCC:
            reg.immediate(reg.OP_EOR, 1)
        reg.become(i, reg.O_A, typetab.BOOL_TYPE)
    else:
        no = jump_false()
        done = fbuf.new_label()
        reg.force(reg.A, 1)
        fbuf.branch(OP_BNE, done)               # always taken: A is 1
        reg.label(no)
        reg.force(reg.A, 0)
        reg.label(done)
        reg.push_register(typetab.BOOL_TYPE)


def carry(i):
    """Put operand `i`, a `bool`, in the carry flag: set for true. A stays as it is unless
    the operand is a variable. The operand is left for the caller to pop."""
    if reg.op_type[i] != typetab.BOOL_TYPE:
        err.fatal(err.E_TYPE)
    if reg.op_kind[i] == reg.O_CONST:
        if reg.op_value[i] != 0:
            reg.implied(reg.OP_SEC)
        else:
            reg.implied(reg.OP_CLC)
    elif reg.op_kind[i] != reg.O_COND:
        reg.release(i)
        reg.load(reg.A, i, 0)
        reg.accumulator(reg.OP_LSR)
    elif is_plain(i) and reg.op_value[i] == OP_BEQ and reg.op_flags[i] & F_COMPARED != 0:
        done = fbuf.new_label()                 # equal: the CMP has set the carry as well
        fbuf.branch(OP_BEQ, done)
        reg.implied(reg.OP_CLC)
        reg.label(done)
    elif reg.op_value[i] != OP_BCS or (reg.op_true[i] != reg.NONE and reg.op_false[i] != reg.NONE):
        yes = away(i, False)
        done = fbuf.new_label()
        reg.implied(reg.OP_CLC)
        fbuf.branch(OP_BCC, done)               # always taken
        reg.label(yes)
        reg.implied(reg.OP_SEC)
        reg.label(done)
    elif reg.op_false[i] != reg.NONE:
        done = fbuf.new_label()                 # the flag is right already, except for those
        fbuf.branch(OP_BCS, done)               # who branched away because the answer is false
        reg.label(reg.op_false[i])
        reg.implied(reg.OP_CLC)
        reg.label(done)
    elif reg.op_true[i] != reg.NONE:
        done = fbuf.new_label()
        fbuf.branch(OP_BCC, done)
        reg.label(reg.op_true[i])
        reg.implied(reg.OP_SEC)
        reg.label(done)


# ---- Comparisons -------------------------------------------------------------------------

def result(branch):
    """Replace the two operands compared by the Condition `branch`."""
    reg.pop()
    reg.pop()
    push(branch)


def known(truth):
    """Replace the two operands compared by a constant: the answer needs no code."""
    reg.pop()
    reg.pop()
    reg.push(reg.O_CONST, typetab.BOOL_TYPE, int_of(truth))


def int_of(truth):
    if truth:
        return 1
    return 0


def is_negative(i):
    """True if constant operand `i` is below zero."""
    return typetab.is_signed(reg.op_type[i]) and reg.op_value[i] >= 0x8000


def is_zero(i):
    return reg.op_kind[i] == reg.O_CONST and reg.op_value[i] == 0


def mirror(op):
    """The comparison that gives the same answer with its operands exchanged."""
    if op <= fold.GE:
        return op + 2
    return op - 2


def bytes_compared(t, first, second):
    """How many bytes a comparison in type `t` must look at: one if the high bytes are the
    same constant."""
    if typetab.size(t) == 2 and reg.is_const_byte(first, 1) and reg.is_const_byte(second, 1) \
            and reg.const_byte(first, 1) == reg.const_byte(second, 1):
        return 1
    return typetab.size(t)


def equal_bytes(first, second, k):
    """Set the Z flag if byte `k` of the two operands is equal. A byte that is known goes
    on the right, where 0 needs no instruction at all. Returns True if a CMP did it: the
    carry is then set too if they are equal."""
    if reg.is_const_byte(first, k) and not reg.is_const_byte(second, k):
        other = first
        first = second
        second = other
    if reg.is_const_byte(second, k) and reg.const_byte(second, k) == 0:
        reg.test_byte(first, k)
        return False
    reg.load(reg.A, first, k)
    reg.compare(second, k)
    return True


def equality(op, t):
    """`==` or `!=`: the answer is the Z flag. For two bytes, the low bytes decide alone if
    they differ, and a branch for that is part of the Condition."""
    if reg.op_kind[reg.depth - 2] == reg.O_CONST or reg.in_registers(reg.depth - 1):
        reg.swap()                      # a constant goes right, what is in the registers left
    first = reg.depth - 2
    second = reg.depth - 1
    count = bytes_compared(t, first, second)
    reg.release(first)
    differ = reg.NONE
    compared = False
    if count == 2 and is_zero(second) and reg.op_kind[first] == reg.O_VAR:
        reg.load(reg.A, first, 0)
        reg.alu(reg.OP_ORA, first, 1)
        count = 0
    for k in range(0, count):
        if k == 1:
            differ = fbuf.new_label()
            fbuf.branch(OP_BNE, differ)
        compared = equal_bytes(first, second, k)
    if op == fold.EQ:
        result(OP_BEQ)
        reg.op_false[reg.depth - 1] = differ
        if compared:
            reg.op_flags[reg.depth - 1] = F_COMPARED
    else:
        result(OP_BNE)
        reg.op_true[reg.depth - 1] = differ


def subtract(count, signed, one_more):
    """Compare the operand under the newest one, through A, with the newest, by subtracting.
    Afterwards carry clear, or for signed types N set, means it is the smaller; if `one_more`
    is subtracted as well, carry clear means it is the smaller or equal."""
    first = reg.depth - 2
    second = reg.depth - 1
    reg.load(reg.A, first, 0)
    if one_more:
        reg.implied(reg.OP_CLC)
        reg.alu(reg.OP_SBC, second, 0)
    elif count == 1 and signed:
        reg.implied(reg.OP_SEC)
        reg.alu(reg.OP_SBC, second, 0)
    else:
        reg.compare(second, 0)
    if count == 2:
        reg.load(reg.A, first, 1)
        reg.alu(reg.OP_SBC, second, 1)
    if signed:
        same = fbuf.new_label()
        fbuf.branch(OP_BVC, same)       # after an overflow the sign is the wrong way round
        reg.immediate(reg.OP_EOR, SIGN_BIT)
        reg.label(same)


def arranged(op, t, signed):
    """Bring `<` `>=` `>` `<=` to `<` or `>=` with a constant, if there is one, on the right:
    by exchanging the operands, or by adding 1 to the constant. Returns that operator, or 0 if
    the answer needs no code and has replaced the operands."""
    if reg.op_kind[reg.depth - 2] == reg.O_CONST:
        reg.swap()
        op = mirror(op)
    second = reg.depth - 1
    if reg.op_kind[second] != reg.O_CONST:
        if op == fold.GT or op == fold.LE:
            reg.swap()
            op = mirror(op)
        return op
    if op == fold.GT or op == fold.LE:
        if reg.op_value[second] == typetab.limit(t):
            known(op == fold.LE)
            return 0
        reg.op_value[second] = (reg.op_value[second] + 1) & 0xFFFF
        if op == fold.GT:               # > c is >= c + 1, <= c is < c + 1
            op = fold.GE
        else:
            op = fold.LT
    if not signed and reg.op_value[second] == 0:
        known(op == fold.GE)
        return 0
    return op


def turned(op, signed):
    """If the answer is wanted in the carry flag, turn an unsigned `<` round so that it is
    true with the carry set: a < b is b - 1 >= a. Returns the operator, and True if the 1 is
    still to be subtracted, which a constant has had done already."""
    second = reg.depth - 1
    if not for_carry or op != fold.LT or signed or reg.in_registers(second - 1):
        return op, False
    one_more = reg.op_kind[second] != reg.O_CONST
    if not one_more:
        reg.op_value[second] -= 1
    reg.swap()
    return fold.GE, one_more


def ordering(op, t, signed):
    """`<` `>=` `>` `<=`: the left operand goes through A and is compared with the right by
    subtracting. The answer is the carry flag, or for signed types the sign."""
    op = arranged(op, t, signed)
    if op == 0:
        return
    op, one_more = turned(op, signed)
    second = reg.depth - 1
    if reg.in_registers(second):
        reg.spill(second)
    reg.release(second - 1)
    branch = OP_BCC
    if signed:
        branch = OP_BMI
    if signed and is_zero(second):
        reg.test_byte(second - 1, typetab.size(t) - 1)      # the sign is all that matters
    else:
        subtract(typetab.size(t), signed, one_more)
    if op == fold.GE:
        branch = branch ^ FLIP
    result(branch)


def compare(op):
    """A comparison of the two newest operands. Leaves a Condition, or a constant."""
    value()
    first = reg.depth - 2
    second = reg.depth - 1
    t = reg.unify(first, second)
    if t == typetab.BOOL_TYPE and op > fold.NE:
        err.fatal(err.E_TYPE)
    if reg.op_kind[first] == reg.O_CONST and reg.op_kind[second] == reg.O_CONST:
        known(fold.compare(op, reg.op_value[first], is_negative(first),
                           reg.op_value[second], is_negative(second)))
    elif op > fold.NE:
        ordering(op, t, typetab.is_signed(t))
    elif for_carry and (is_zero(first) or is_zero(second)):
        if is_zero(first):
            reg.swap()
        if op == fold.EQ:
            ordering(fold.LE, t, False)         # as unsigned numbers, == 0 is <= 0
        else:
            ordering(fold.GT, t, False)         # and != 0 is > 0: both end in the carry
    else:
        equality(op, t)
