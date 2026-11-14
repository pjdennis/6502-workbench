"""GEN: instruction selection (the top one of its three files; REG and COND are below).

Owns
- arithmetic. An operator on two operands is not turned into code at once: it stays pending,
  with its operands as the two newest on the stack, until what follows shows where the
  result must go. An assignment or an argument then computes it straight into its
  destination, which gives `x = y + z` on words in seven instructions and `i = i + 1` as one
  INC; anything else takes it into A, or A and X (docs/codegen.md, "Bytes" and "Words").
  Only one operation is pending at a time: pushing the next operand settles it;
- stores, conversions, calls and returns;
- the function being compiled, from its first instruction to its records in the object file;
- the list of initial values, which becomes the function `module.$init`.

EXPR, STMT and DECL push operands only through this file, so that a pending operation is
settled first; they read the stack in REG.
"""
import cond
import err
import fbuf
import fold
import kernel
import out
import reg
import typetab

# Where a parameter or result of an `extern` or `asm` function is. Pairs are low byte first.
REG_NONE = 0
REG_A = 1
REG_X = 2
REG_Y = 3
REG_AX = 4
REG_AY = 5
REG_XY = 6
REG_C = 7               # a bool in the carry flag

# For each of those, which byte of the value A, X and Y get: 0, 1 or NO_BYTE.
REGISTER_BYTES = (b"\xFF\xFF\xFF" b"\x00\xFF\xFF" b"\xFF\x00\xFF" b"\xFF\xFF\x00"
                  b"\x00\x01\xFF" b"\x00\xFF\x01" b"\xFF\x00\x01" b"\xFF\xFF\xFF")
NO_BYTE = 0xFF

REGISTERS = reg.NONE    # as the target of an operation: A, or A and X

OP_BCC = 0x90
OP_BCS = 0xB0
OP_BNE = 0xD0
OP_BEQ = 0xF0
OP_BPL = 0x10
OP_PHA = 0x48
OP_PLA = 0x68
OP_TXA = 0x8A
OP_TYA = 0x98
OP_TAX = 0xAA
OP_RTS = 0x60

MAX_INITS = 64
INIT_FLUSH = 32         # DECL writes the list out between declarations when it is this long

cpu = 0                 # 0 6502, 1 65C02; from the environment description, when that is read
pend_op = 0             # the pending operation (a fold.ADD to fold.SHR), or 0
pend_type = 0           # the type of its result
outer = out.NO_OUTER    # the function whose arguments are being stored, as CALL records name it

init_symbol = [0] * MAX_INITS       # the variables with initial values: as for reg.push_memory
init_address = [0] * MAX_INITS
init_flags = [0] * MAX_INITS
init_type = [0] * MAX_INITS
init_value = [0] * MAX_INITS
init_count = 0
init_part = kernel.NO_OBJ           # the function that sets the values written out earlier


def init():
    global cpu, init_count, init_part
    cpu = 0
    init_count = 0
    init_part = kernel.NO_OBJ


# ---- Pushing operands --------------------------------------------------------------------

def settle():
    """Nothing may stay pending: compute the pending operation into the registers."""
    resolve(False)


def resolve(in_memory):
    """Compute the pending operation, if there is one: into a temporary if it is a word and
    that is asked for, because the result must be an instruction's operand, and otherwise
    into the registers."""
    global pend_op
    if pend_op == 0:
        return
    op = pend_op
    pend_op = 0
    first = reg.depth - 2
    if typetab.size(pend_type) == 2 and (in_memory or is_shift(op)):
        reg.describe_temp(reg.depth, pend_type)     # a word is also shifted in memory
        operate(op, pend_type, first, first + 1, first + 2)
        reg.pop()
        reg.pop()
        reg.keep(first + 2)
    else:
        operate(op, pend_type, first, first + 1, REGISTERS)
        reg.pop()
        reg.pop()
        reg.push_register(pend_type)


def constant(t, value):
    settle()
    reg.push(reg.O_CONST, t, value)


def function(s):
    """Push function `s` by name; a call must follow."""
    settle()
    reg.push(reg.O_FUNC, typetab.NO_TYPE, 0)
    reg.op_var[reg.depth - 1] = s


def object_symbol(s):
    """The object-file number of function or variable `s`, which gets its SYM record when it
    is first used."""
    if kernel.sym_obj[s] == kernel.NO_OBJ:
        kind = out.SYM_FUNCTION
        if kernel.sym_kind[s] == kernel.K_VAR:
            kind = out.SYM_VARIABLE
        kernel.sym_obj[s] = out.symbol(kind, kernel.module_name[kernel.sym_scope[s]], 0,
                                       kernel.sym_name[s])
    return kernel.sym_obj[s]


def variable(s):
    """Push variable `s`, which lives for the whole program or is at a fixed address."""
    settle()
    if kernel.sym_flags[s] & kernel.SF_AT != 0:
        reg.push_memory(kernel.sym_type[s], kernel.NO_OBJ, fbuf.NO_SLOT, kernel.sym_value[s], 0,
                        kernel.NO_SYM)
    else:
        reg.push_memory(kernel.sym_type[s], object_symbol(s), fbuf.NO_SLOT, 0, zp_flag(s), s)


def zp_flag(s):
    if kernel.sym_flags[s] & kernel.SF_ZP != 0:
        return reg.F_ZP
    return 0


def local(t, slot):
    """Push a parameter or local of the function being compiled."""
    settle()
    reg.push_slot(t, slot)


def parameter(f, i):
    """Push parameter `i` of function `f`, for an argument to be stored in. From the second
    one on, an argument is waiting in `f`'s frame while the next is worked out."""
    global outer
    settle()
    reg.push_memory(kernel.member_type[kernel.sym_members[f] + i], object_symbol(f), i, 0, 0,
                    kernel.NO_SYM)
    if i > 0:
        outer = object_symbol(f)


def arguments_end(saved):
    """The arguments of a call are all stored: `saved` is what `outer` was before them."""
    global outer
    outer = saved


# ---- Arithmetic --------------------------------------------------------------------------

def is_shift(op):
    return op == fold.SHL or op == fold.SHR


def commutes(op):
    return op == fold.ADD or op == fold.BAND or op == fold.BOR or op == fold.BXOR


def operation_type(op):
    """The type of `op` on the two newest operands, which take it. Without a type if both
    are numbers without one."""
    first = reg.depth - 2
    second = reg.depth - 1
    t = reg.op_type[first]
    if is_shift(op):
        if typetab.is_untyped(reg.op_type[second]):
            reg.fit(second, typetab.BYTE_TYPE)
        if reg.op_type[second] != typetab.BYTE_TYPE:
            err.fatal(err.E_TYPE)
        if typetab.is_untyped(t) and reg.op_kind[second] != reg.O_CONST:
            err.fatal(err.E_TYPE)       # a number shifted by a variable: of which size?
    else:
        t = reg.unify(first, second)
    if not typetab.is_number(t) and not typetab.is_untyped(t):
        err.fatal(err.E_TYPE)
    return t


def fold_constants(op, t):
    """Replace the two newest operands, both constants, by what `op` gives for them."""
    first = reg.depth - 2
    second = reg.depth - 1
    if typetab.is_untyped(t):
        value, negative = fold.exact(op, reg.op_value[first], reg.op_type[first] == typetab.NEGATIVE_TYPE,
                                     reg.op_value[second], reg.op_type[second] == typetab.NEGATIVE_TYPE)
        t = typetab.NUMBER_TYPE
        if negative:
            t = typetab.NEGATIVE_TYPE
    else:
        value = fold.typed(op, t, reg.op_value[first], reg.op_value[second])
    reg.pop()
    reg.pop()
    reg.push(reg.O_CONST, t, value)


def exponent(value):
    """n if `value` is 2 to the power n, or reg.NONE."""
    for n in range(0, 16):
        if value == 1 << n:
            return n
    return reg.NONE


def reduce(op, t):
    """Turn `*`, `/` or `mod` by a constant power of two into a shift or a mask, by changing
    the constant. Returns the operator to use. Anything else is for the run-time library."""
    if op == fold.MUL and reg.op_kind[reg.depth - 2] == reg.O_CONST:
        reg.swap()
    second = reg.depth - 1
    if reg.op_kind[second] != reg.O_CONST:
        err.fatal(err.E_NEEDS_RT)
    n = exponent(reg.op_value[second])
    if op == fold.MUL and reg.op_value[second] == 0:
        return fold.BAND                # x * 0 is x & 0
    if op != fold.MUL and reg.op_value[second] == 0:
        err.fatal(err.E_DIV_ZERO)
    if n == reg.NONE or (op != fold.MUL and typetab.is_signed(t)):
        err.fatal(err.E_NEEDS_RT)       # a shift rounds a negative number the wrong way
    if op == fold.REM:
        reg.op_value[second] -= 1
        return fold.BAND
    reg.op_value[second] = n
    reg.op_type[second] = typetab.BYTE_TYPE
    if op == fold.MUL:
        return fold.SHL
    return fold.SHR


def changes_nothing(op, t, value):
    """True if `op` with the constant `value` on its right gives its left operand."""
    if op == fold.BAND:
        return typetab.narrow(value, t) == typetab.narrow(0xFFFF, t)
    return value == 0


def gives_zero(op, t, value):
    """True if `op` with the constant `value` on its right gives 0 whatever is on its left."""
    if op == fold.BAND:
        return value == 0
    if op == fold.SHL or (op == fold.SHR and not typetab.is_signed(t)):
        return value >= 8 * typetab.size(t)
    return False


def binary(op):
    """An arithmetic operator on the two newest operands. The result replaces them: at once
    if no code or only code for a byte in A is needed, and otherwise as the pending operation."""
    global pend_op, pend_type
    resolve(not commutes(op))
    t = operation_type(op)
    if reg.op_kind[reg.depth - 2] == reg.O_CONST and reg.op_kind[reg.depth - 1] == reg.O_CONST:
        fold_constants(op, t)
        return
    if op >= fold.MUL:
        op = reduce(op, t)
    if commutes(op) and reg.op_kind[reg.depth - 2] == reg.O_CONST:
        reg.swap()
    second = reg.depth - 1
    if reg.op_kind[second] == reg.O_CONST:
        if changes_nothing(op, t, reg.op_value[second]):
            reg.pop()
            reg.op_type[reg.depth - 1] = t
            return
        if gives_zero(op, t, reg.op_value[second]):
            reg.pop()
            reg.pop()
            reg.push(reg.O_CONST, t, 0)
            return
        if is_shift(op) and reg.op_value[second] >= 8 * typetab.size(t):
            reg.op_value[second] = 8 * typetab.size(t) - 1      # signed: only the sign is left
    elif is_shift(op):
        variable_shift(op, t)
        return
    if reg.in_registers(second):
        if commutes(op):
            reg.swap()
        elif typetab.size(t) == 1:
            reverse_subtract(t)
            return
        else:
            reg.spill(second)
    pend_op = op
    pend_type = t


def reverse_subtract(t):
    """A byte subtraction whose right side is in A: add the left side to its complement."""
    reg.release(reg.depth - 1)
    reg.immediate(reg.OP_EOR, 0xFF)
    reg.implied(reg.OP_SEC)
    reg.alu(reg.OP_ADC, reg.depth - 2, 0)
    reg.pop()
    reg.pop()
    reg.push_register(t)


def shift_a(op, signed):
    """Shift A by one place."""
    if op == fold.SHL:
        reg.accumulator(reg.OP_ASL)
    elif signed:
        reg.compare_const(0x80)         # the sign into the carry flag, to be shifted back in
        reg.accumulator(reg.OP_ROR)
    else:
        reg.accumulator(reg.OP_LSR)


def variable_shift(op, t):
    """A byte shifted by a count that is not a constant: a loop counted in X."""
    first = reg.depth - 2
    second = reg.depth - 1
    if typetab.size(t) != 1:
        err.fatal(err.E_NEEDS_RT)
    if reg.in_registers(second):
        reg.release(second)
        reg.load(reg.X, second, 0)
        reg.load(reg.A, first, 0)
    else:
        reg.release(first)
        reg.load(reg.A, first, 0)
        reg.load(reg.X, second, 0)
    reg.test(reg.X)
    done = fbuf.new_label()
    again = fbuf.new_label()
    fbuf.branch(OP_BEQ, done)
    reg.loop_label(again)
    shift_a(op, op == fold.SHR and typetab.is_signed(t))
    reg.step_x(reg.OP_DEX)
    fbuf.branch(OP_BNE, again)
    reg.label(done)
    reg.pop()
    reg.pop()
    reg.push_register(t)


def negate():
    """Unary `-` of the newest operand: 0 minus it."""
    settle()
    t = reg.op_type[reg.depth - 1]
    if typetab.is_untyped(t):
        t = typetab.NUMBER_TYPE
    reg.push(reg.O_CONST, t, 0)
    reg.swap()
    binary(fold.SUB)


def complement():
    """Unary `~` of the newest operand: it exclusive-or all ones."""
    settle()
    t = reg.op_type[reg.depth - 1]
    if typetab.is_untyped(t):
        reg.push(reg.O_CONST, typetab.NEGATIVE_TYPE, 0xFFFF)
    else:
        reg.push(reg.O_CONST, t, typetab.narrow(0xFFFF, t))
    binary(fold.BXOR)


# ---- Computing an operation into its destination -----------------------------------------

def alu_opcode(op):
    if op == fold.ADD:
        return reg.OP_ADC
    if op == fold.SUB:
        return reg.OP_SBC
    if op == fold.BAND:
        return reg.OP_AND
    if op == fold.BOR:
        return reg.OP_ORA
    return reg.OP_EOR


def in_place(first, target):
    """True if the result, of two bytes, goes where the left operand is."""
    if target == REGISTERS:
        return reg.op_kind[first] == reg.O_AX
    return reg.same_place(first, target)


def leaves(op, value, chained):
    """True if `op` with the constant byte `value` gives the byte on its left unchanged. For `+`
    and `-` that also needs no carry or borrow to be on its way from the bytes below."""
    if op == fold.BAND:
        return value == 0xFF
    if op == fold.ADD or op == fold.SUB:
        return value == 0 and not chained
    return value == 0


def move(first, k, target):
    """Byte `k` of the result is value `k` of the left operand."""
    if target != REGISTERS:
        if not reg.same_place(first, target):
            reg.put(first, k, target, k)
    elif k == 0:
        reg.load(reg.A, first, 0)
    else:
        reg.load(reg.X, first, 1)


def zero(k, target):
    """Byte `k` of the result is 0."""
    if target != REGISTERS:
        reg.put_const(0, target, k)
    elif k == 0:
        reg.load_const(reg.A, 0)
    else:
        reg.load_const(reg.X, 0)


def ripple(op, k, target):
    """Byte `k` of the result is where its left operand is and only a carry or borrow can
    change it: INC or DEC it if there is one."""
    skip = fbuf.new_label()
    if op == fold.ADD:
        fbuf.branch(OP_BCC, skip)
        if target == REGISTERS:
            reg.step_x(reg.OP_INX)
        else:
            reg.modify(reg.OP_INC, target, k)
    else:
        fbuf.branch(OP_BCS, skip)
        if target == REGISTERS:
            reg.step_x(reg.OP_DEX)
        else:
            reg.modify(reg.OP_DEC, target, k)
    reg.label(skip)


def combine(op, count, first, second, target):
    """`+ - & | ^` byte by byte, low byte first. With the registers as target, the low byte
    waits in Y while the high byte is worked out in A."""
    chained = False
    for k in range(0, count):
        fixed = reg.is_const_byte(second, k)
        value = reg.const_byte(second, k)
        if fixed and leaves(op, value, chained):
            move(first, k, target)
        elif fixed and op == fold.BAND and value == 0:
            zero(k, target)
        elif fixed and chained and value == 0 and k == 1 and in_place(first, target):
            ripple(op, k, target)
        else:
            reg.claim(reg.A)            # what must be stored first is stored before the CLC
            if not chained and op == fold.ADD:
                reg.implied(reg.OP_CLC)
            elif not chained and op == fold.SUB:
                reg.implied(reg.OP_SEC)
            chained = True
            if k == 1 and target == REGISTERS:
                reg.transfer(reg.A, reg.Y)
            reg.load(reg.A, first, k)
            reg.alu(alu_opcode(op), second, k)
            if target != REGISTERS:
                reg.store(reg.A, target, k)
            elif k == 1:
                reg.transfer(reg.A, reg.X)
                reg.transfer(reg.Y, reg.A)


def step(op, count, target):
    """Add 1 to or subtract 1 from memory operand `target`, where it is."""
    if count == 1 and op == fold.ADD:
        reg.modify(reg.OP_INC, target, 0)
    elif count == 1:
        reg.modify(reg.OP_DEC, target, 0)
    elif op == fold.ADD:
        skip = fbuf.new_label()
        reg.modify(reg.OP_INC, target, 0)
        fbuf.branch(OP_BNE, skip)
        reg.modify(reg.OP_INC, target, 1)
        reg.label(skip)
    else:
        skip = fbuf.new_label()
        reg.load(reg.A, target, 0)
        reg.test(reg.A)
        fbuf.branch(OP_BNE, skip)
        reg.modify(reg.OP_DEC, target, 1)
        reg.label(skip)
        reg.modify(reg.OP_DEC, target, 0)


def shift_memory(op, signed, target, count):
    """Shift memory operand `target`, of `count` bytes, by one place."""
    if op == fold.SHL:
        reg.modify(reg.OP_ASL, target, 0)
        if count == 2:
            reg.modify(reg.OP_ROL, target, 1)
        return
    if signed:
        reg.load(reg.A, target, count - 1)
        reg.accumulator(reg.OP_ASL)     # the sign into the carry flag, to be shifted back in
        reg.modify(reg.OP_ROR, target, count - 1)
    else:
        reg.modify(reg.OP_LSR, target, count - 1)
    if count == 2:
        reg.modify(reg.OP_ROR, target, 0)


def shift_copy(op, signed, first, target):
    """Copy the word `first` to memory operand `target`, shifting it by one place on the way."""
    if op == fold.SHL:
        reg.load(reg.A, first, 0)
        reg.accumulator(reg.OP_ASL)
        reg.store(reg.A, target, 0)
        reg.load(reg.A, first, 1)
        reg.accumulator(reg.OP_ROL)
        reg.store(reg.A, target, 1)
        return
    if reg.in_registers(first):
        reg.spill(first)                # the high byte goes first, and would take A
    reg.load(reg.A, first, 1)
    shift_a(op, signed)
    reg.store(reg.A, target, 1)
    reg.load(reg.A, first, 0)
    reg.accumulator(reg.OP_ROR)
    reg.store(reg.A, target, 0)


def shift(op, t, first, amount, target):
    """Shift `first` by the constant `amount`: in memory if that is where the result goes,
    otherwise a byte in A and a word on its way to the target."""
    signed = op == fold.SHR and typetab.is_signed(t)
    count = typetab.size(t)
    if target == REGISTERS or (count == 1 and not reg.same_place(first, target)):
        reg.load(reg.A, first, 0)
        for n in range(0, amount):
            shift_a(op, signed)
        if target != REGISTERS:
            reg.store(reg.A, target, 0)
        return
    if not reg.same_place(first, target):
        shift_copy(op, signed, first, target)
        amount -= 1
    for n in range(0, amount):
        shift_memory(op, signed, target, count)


def operate(op, t, first, second, target):
    """Generate `first op second` in type `t`. `target` is the memory operand the result goes
    to, or REGISTERS."""
    reg.release(first)
    reg.release(second)
    if is_shift(op):
        shift(op, t, first, reg.op_value[second], target)
    elif (op == fold.ADD or op == fold.SUB) and target != REGISTERS and reg.same_place(first, target) \
            and reg.op_kind[second] == reg.O_CONST and reg.op_value[second] == 1:
        step(op, typetab.size(t), target)
    else:
        combine(op, typetab.size(t), first, second, target)


# ---- Stores ------------------------------------------------------------------------------

def copy_value():
    """Store the newest operand in the memory operand under it. Both are used up."""
    target = reg.depth - 2
    source = reg.depth - 1
    reg.assignable(source, reg.op_type[target])
    reg.release(source)
    if not reg.same_place(source, target):
        for k in range(0, typetab.size(reg.op_type[target])):
            reg.put(source, k, target, k)
    reg.pop()
    reg.pop()


def store():
    """Store the value on top of the stack, which may be the pending operation, in the memory
    operand under it: an assignment, or an argument on its way to a parameter."""
    global pend_op
    if pend_op == 0:
        cond.value()
        copy_value()
        return
    op = pend_op
    pend_op = 0
    target = reg.depth - 3
    if not reg.accepts(pend_type, reg.op_type[target]):
        err.fatal(err.E_TYPE)
    operate(op, pend_type, target + 1, target + 2, target)
    for k in range(typetab.size(pend_type), typetab.size(reg.op_type[target])):
        reg.put_const(0, target, k)
    reg.pop()
    reg.pop()
    reg.pop()


def assign(op):
    """`target op= value`: the value is on top of the stack and the target under it."""
    settle()
    reg.duplicate(reg.depth - 2)
    reg.swap()
    binary(op)
    store()


def store_arrow():
    """`f() -> v`: the value a call left is under the newest operand, the variable `v`. Store
    it there and leave the status, which is still in the carry flag, as a Condition."""
    reg.swap()
    copy_value()
    cond.push(OP_BCS)


def store_pair():
    """`v, ok = f()`: `v`, `ok` and the value the call left are the three newest operands."""
    source = reg.depth - 1
    target = reg.depth - 3
    reg.assignable(source, reg.op_type[target])
    reg.release(source)
    for k in range(0, typetab.size(reg.op_type[target])):
        reg.put(source, k, target, k)           # STA and STX leave the carry flag alone
    reg.pop()
    cond.push(OP_BCS)
    store()
    reg.pop()


# ---- Conversions -------------------------------------------------------------------------

def sign_extend(i):
    """Make the signed byte operand `i` a two-byte value in A and X."""
    reg.release(i)
    reg.load_const(reg.X, 0)
    reg.load(reg.A, i, 0)
    reg.test(reg.A)
    plus = fbuf.new_label()
    fbuf.branch(OP_BPL, plus)
    reg.step_x(reg.OP_DEX)
    reg.label(plus)
    t = reg.op_type[i]
    reg.become(i, reg.O_AX, t)


def convert(t):
    """`t(value)`: the newest operand is given type `t`. Narrowing keeps the low byte; a
    signed byte made wider keeps its sign; `bool(x)` is `x != 0`."""
    global pend_type
    if pend_op != 0 and pend_op != fold.SHR and typetab.is_number(t) \
            and typetab.size(t) <= typetab.size(pend_type):
        pend_type = t           # the low byte of these needs only the low bytes
        return
    settle()
    i = reg.depth - 1
    source = reg.op_type[i]
    if t == typetab.BOOL_TYPE:
        if source != typetab.BOOL_TYPE:
            reg.push(reg.O_CONST, typetab.NUMBER_TYPE, 0)
            cond.compare(fold.NE)
        return
    cond.value()
    if not typetab.is_number(source) and not typetab.is_untyped(source) and source != typetab.BOOL_TYPE:
        err.fatal(err.E_TYPE)
    if reg.op_kind[i] == reg.O_CONST:
        reg.op_value[i] = typetab.narrow(reg.op_value[i], t)
        reg.op_size[i] = typetab.size(t)
    elif typetab.size(t) == 1:
        if reg.op_kind[i] == reg.O_AX:
            reg.op_kind[i] = reg.O_A
        reg.op_size[i] = 1
    elif source == typetab.SBYTE_TYPE:
        sign_extend(i)                  # an unsigned byte made wider has a high byte of 0
    reg.op_type[i] = t


def part(k):
    """`lo(x)` (k is 0) or `hi(x)` (k is 1) of the newest operand: a byte. Of a variable it
    is a variable, and can be assigned to."""
    settle()
    i = reg.depth - 1
    if not typetab.is_number(reg.op_type[i]) and not typetab.is_untyped(reg.op_type[i]):
        err.fatal(err.E_TYPE)
    if reg.is_const_byte(i, k):
        value = reg.const_byte(i, k)
        reg.pop()
        reg.push(reg.O_CONST, typetab.BYTE_TYPE, value)
        return
    if reg.op_kind[i] == reg.O_VAR:
        reg.op_value[i] = (reg.op_value[i] + k) & 0xFFFF
    elif reg.op_kind[i] == reg.O_AX:
        reg.release(i)
        reg.load(reg.A, i, k)
        reg.become(i, reg.O_A, typetab.BYTE_TYPE)
    reg.op_type[i] = typetab.BYTE_TYPE
    reg.op_size[i] = 1


def size_of(t):
    constant(typetab.NUMBER_TYPE, typetab.size(t))


# ---- Calls -------------------------------------------------------------------------------

def accept(t):
    """Check that the newest operand can be given to something of type `t`."""
    settle()
    reg.assignable(reg.depth - 1, t)


def hold():
    """The newest operand is an argument for a register and another argument follows. It
    may wait in A, or A and X, until one of those is needed, but not in the flags."""
    settle()
    cond.value()


def load_registers(f, first):
    """Put the arguments of `extern` or `asm` function `f`, the operands from `first` on, where its
    parameters are: the carry flag first, because finding it can take A, then Y, X and A.
    An argument that is still in A can go from there to where it belongs."""
    members = kernel.sym_members[f]
    count = kernel.sym_params[f]
    settle()
    if count == 0:
        return
    if kernel.member_value[members + count - 1] != REG_C:
        cond.value()
    for i in range(0, count):
        if kernel.member_value[members + i] == REG_C:
            cond.carry(first + i)
    held = reg.owner
    if held != reg.NONE and held >= first:
        if reg.op_kind[held] == reg.O_AX and kernel.member_value[members + held - first] != REG_AX:
            reg.spill(held)
        reg.release(held)
    for r in range(reg.Y, reg.A - 1, -1):
        for i in range(0, count):
            k = REGISTER_BYTES[kernel.member_value[members + i] * 3 + r]
            if k != NO_BYTE:
                reg.load(r, first + i, k)


def result(f):
    """Push what a call of `f` left: its value, now in A or in A and X, or else its status as
    a Condition. Nothing if it has no results."""
    if kernel.sym_results[f] == 0:
        return
    m = kernel.sym_members[f] + kernel.sym_params[f]
    where = kernel.member_value[m]
    if where == REG_C:
        cond.push(OP_BCS)
        return
    if where == REG_XY or where == REG_X:
        fbuf.op(OP_TXA)
    if where == REG_Y:
        fbuf.op(OP_TYA)
    if where == REG_AY or where == REG_XY:
        fbuf.op(OP_PHA)                 # the high byte goes from Y to X by way of A
        fbuf.op(OP_TYA)
        fbuf.op(OP_TAX)
        fbuf.op(OP_PLA)
    reg.push_register(kernel.member_type[m])


def by_registers(f):
    """True if function `f` takes its arguments in registers: an `extern` or `asm` function."""
    return kernel.sym_flags[f] & (kernel.SF_EXTERN | kernel.SF_ASM) != 0


def call(f, first, wanted):
    """Call function `f`. The arguments of an `extern` or `asm` function are the operands from
    `first` on; those of any other are in its frame already. Pushes result(f) if it is
    `wanted`. An `extern` function is at a fixed address; any other is reached through its
    symbol, with a CALL record."""
    if by_registers(f):
        load_registers(f, first)
        while reg.depth > first:
            reg.pop()
    reg.clobber()
    if kernel.sym_flags[f] & kernel.SF_EXTERN != 0:
        fbuf.op_word(fbuf.OP_JSR, kernel.sym_value[f])
    else:
        callee = object_symbol(f)
        fbuf.op_fix(fbuf.OP_JSR, fbuf.FIX_ADDRESS, callee, fbuf.NO_SLOT, 0)
        out.call(callee, 0, outer)
    reg.forget()
    if wanted:
        result(f)


def mark():
    """A number that changes with every instruction generated."""
    return fbuf.used


# ---- Conditions ---------------------------------------------------------------------------

def compare(op):
    """A comparison of the two newest operands."""
    resolve(op == fold.LT or op == fold.GE)     # these have the right side as CMP's operand
    cond.compare(op)


def as_value():
    """The newest operand is complete and another will be worked out before it is used: a
    Condition cannot wait in the flags."""
    settle()
    cond.value()


def test_left(wanted):
    """The left side of `and` (`wanted` True) or `or` (False) is complete."""
    settle()
    cond.left(wanted)


def test_right():
    settle()
    cond.right()


def invert():
    settle()
    cond.invert()


# ---- Statements --------------------------------------------------------------------------

def jump_false():
    """Use up the newest operand as the test of a statement. Returns the label gone to when
    it is false."""
    settle()
    return cond.jump_false()


def carry_wanted():
    """The expression about to be parsed is a status: carry() will follow."""
    cond.wanted_in_carry(True)


def carry():
    """Use up the newest operand, a `bool`, by putting it in the carry flag."""
    cond.wanted_in_carry(False)
    settle()
    cond.carry(reg.depth - 1)
    reg.pop()


def load_result():
    """Use up the newest operand by loading it into A, or A and X. The carry flag is left
    alone, so a status can be there already."""
    i = reg.depth - 1
    reg.release(i)
    if typetab.size(reg.op_type[i]) == 2:
        reg.load(reg.X, i, 1)
    reg.load(reg.A, i, 0)
    reg.pop()


def ret():
    """Return from the function. A call just made returns for it instead."""
    if not fbuf.tail_call():
        fbuf.op(OP_RTS)


def loop_begin():
    reg.loop_depth += 1


def loop_end():
    reg.loop_depth -= 1


# ---- Functions ---------------------------------------------------------------------------

def function_begin(symbol):
    """Start generating the function whose object-file symbol is `symbol`."""
    global pend_op, outer
    fbuf.begin()
    reg.begin(symbol)
    pend_op = 0
    outer = out.NO_OUTER


def slots(first, count):
    for n in range(first, first + count):
        out.slot(reg.slot_size[n], reg.slot_class[n], reg.slot_weight[n], reg.slot_kind[n],
                 reg.slot_name[n])


def function_end(flags):
    """End the function and write it to the object file: its parameters and locals, then its
    temporaries, then its code."""
    if fbuf.runs_on():
        ret()
    fbuf.finish(reg.own, reg.local_count)
    out.function_begin(reg.own, flags)
    slots(0, reg.local_count)
    slots(fbuf.FIRST_TEMP, reg.temp_count)
    out.function_end()


# ---- Initial values ----------------------------------------------------------------------

def initial(s, value):
    """Variable `s` starts with the constant `value`."""
    global init_count
    if init_count == MAX_INITS:
        err.fatal(err.E_INITS_FULL)
    init_symbol[init_count] = kernel.sym_obj[s]
    init_address[init_count] = 0
    if kernel.sym_flags[s] & kernel.SF_AT != 0:
        init_address[init_count] = kernel.sym_value[s]
    init_flags[init_count] = zp_flag(s)
    init_type[init_count] = kernel.sym_type[s]
    init_value[init_count] = value
    init_count += 1


def init_function(symbol):
    """Write the function `symbol` that sets the initial values listed so far, after calling
    the function that sets those written out before. The register memory loads each value
    once for the variables that follow each other with the same one."""
    global init_count, init_part
    function_begin(symbol)
    if init_part != kernel.NO_OBJ:
        fbuf.op_fix(fbuf.OP_JSR, fbuf.FIX_ADDRESS, init_part, fbuf.NO_SLOT, 0)
        out.call(init_part, 0, out.NO_OUTER)
    for n in range(0, init_count):
        reg.push_memory(init_type[n], init_symbol[n], fbuf.NO_SLOT, init_address[n], init_flags[n],
                        kernel.NO_SYM)
        reg.push(reg.O_CONST, init_type[n], init_value[n])
        store()
    init_count = 0
    init_part = symbol
    function_end(0)
