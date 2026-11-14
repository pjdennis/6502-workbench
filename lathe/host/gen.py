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
import lex
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
OP_LDA = 0xAD
OP_STA = 0x8D
OP_STY = 0x8C
C_SPACE = 0x20
C_DOLLAR = 0x24
C_ZERO = 0x30

MAX_INITS = 32
INIT_FLUSH = 32         # DECL writes the list out between declarations when it is this long
MAX_STUBS = 16          # pointers called through in one function
MAX_ARGUMENTS = 32      # arguments of saving calls waiting in temporaries
MAX_HELD = 16           # arguments waiting as operands for registers, with more to follow
FRAME_MODULE = b"rt_frame"      # the run-time module that keeps the frames of recursive functions
PUSH_NAME = b"push"             # push(v: byte in a)
POP_NAME = b"pop_y"             # pop_y(): byte in y, which leaves A, X and the carry flag alone
MATH_MODULE = b"rt_math"        # the run-time module of `*`, `/`, `mod` and word shifts by a variable
# Its functions that operators call, each name ended by a space, and for each the types of its
# two parameters and its result (docs/code-model.md, "Run-time arithmetic").
MATH_NAMES = b"mul8 mul8x8 mul16 div8 mod8 sdiv8 smod8 div16 mod16 sdiv16 smod16 shl16 shr16 sar16 "
MATH_TYPES = (b"\x01\x01\x01" b"\x01\x01\x03" b"\x03\x03\x03" b"\x01\x01\x01" b"\x01\x01\x01"
              b"\x02\x02\x02" b"\x02\x02\x02" b"\x03\x03\x03" b"\x03\x03\x03" b"\x04\x04\x04"
              b"\x04\x04\x04" b"\x03\x01\x03" b"\x03\x01\x03" b"\x04\x01\x04")
M_MUL8 = 0
M_MUL8X8 = 1
M_MUL16 = 2
M_DIV8 = 3              # then mod8, sdiv8, smod8, and the same four on words
M_SHL16 = 11            # then shr16, sar16
MATH_COUNT = 14
MATH_SCOPE = 0xFD       # the scope of rt_math's functions when the module does not import it

cpu = 0                 # 0 6502, 1 65C02; from the environment description, when that is read
pend_op = 0             # the pending operation (a fold.ADD to fold.SHR), or 0
pend_type = 0           # the type of its result
outer = out.NO_OUTER    # the function whose arguments are being stored, as CALL records name it
leave = reg.NONE        # in an interrupt function: the label of its exit code

init_symbol = [0] * MAX_INITS       # the variables with initial values: as for reg.push_memory
init_address = [0] * MAX_INITS
init_flags = [0] * MAX_INITS
init_type = [0] * MAX_INITS
init_value = [0] * MAX_INITS
init_source = [0] * MAX_INITS       # NO_OBJ for a number; else the symbol of an address, or of
init_slot = [0] * MAX_INITS         # the data an array is copied from
init_count = 0
data_count = 0                      # how many symbols of anonymous constant data there are
init_part = kernel.NO_OBJ           # the function that sets the values written out earlier

stub_label = [0] * MAX_STUBS        # for each pointer called through: the label of its
stub_symbol = [0] * MAX_STUBS       # JMP (pointer) at the end of the function, and the pointer
stub_slot = [0] * MAX_STUBS         # as for reg.push_memory
stub_value = [0] * MAX_STUBS
stub_count = 0
saves_frame = False                 # the function being compiled is `recursive`
argument_slot = [0] * MAX_ARGUMENTS # the temporaries the arguments of saving calls wait in
argument_count = 0
held_operand = [0] * MAX_HELD       # the operands of those arguments, oldest first
held_count = 0
saved_slot = bytearray(reg.SLOTS)       # the slots a saving call pushes, in order
saved_count = 0
frame_push = kernel.NO_OBJ          # the symbols of rt_frame.push and rt_frame.pop_y, once used
frame_pop = kernel.NO_OBJ
math_obj = [0] * MATH_COUNT         # the object-file symbols of rt_math's functions, once used
math_member = [0] * MATH_COUNT      # and their parameters and result as members
math_used = False                   # the IMP record of rt_math is written


def init():
    global cpu, init_count, init_part, data_count, frame_push, frame_pop, math_used
    cpu = 0
    math_used = False
    for n in range(0, MATH_COUNT):
        math_obj[n] = kernel.NO_OBJ
    init_count = 0
    data_count = 0
    init_part = kernel.NO_OBJ
    frame_push = kernel.NO_OBJ
    frame_pop = kernel.NO_OBJ


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
    if typetab.size(pend_type) == 2 and (in_memory or is_shift(op) or reg.op_mode[first] == reg.M_POINTER
                                         or reg.op_mode[first + 1] == reg.M_POINTER):
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


def function_address():
    """`@f`: the newest operand, the function `f` it names, becomes its address. That has no
    type until it is given to something of a function type, which must have f's signature
    (reg.fit_function), or converted to a number. That of an `extern` function is the number
    its `at` gives."""
    settle()
    i = reg.depth - 1
    f = reg.op_var[i]
    if kernel.sym_flags[f] & kernel.SF_EXTERN != 0:
        reg.describe(i, reg.O_CONST, typetab.NUMBER_TYPE)
        reg.op_value[i] = kernel.sym_value[f]
        return
    reg.describe(i, reg.O_ADDR, typetab.NO_TYPE)
    reg.op_symbol[i] = object_symbol(f)
    reg.op_var[i] = f


def object_symbol(s):
    """The object-file number of function or variable `s`, or of the pointer class of function
    type `s`, which gets its SYM record when it is first used."""
    if kernel.sym_kind[s] == kernel.K_TYPE:
        return reg.class_symbol(s)
    if kernel.sym_obj[s] == kernel.NO_OBJ:
        kind = out.SYM_FUNCTION
        if kernel.sym_kind[s] == kernel.K_VAR:
            kind = out.SYM_VARIABLE
        elif kernel.sym_kind[s] == kernel.K_CONST:
            kind = out.SYM_DATA
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


def table(s):
    """Push the constant table `s`: constant data, which can be read but not assigned to."""
    settle()
    reg.push_memory(kernel.sym_type[s], object_symbol(s), fbuf.NO_SLOT, 0, reg.F_DATA, kernel.NO_SYM)


def zp_flag(s):
    if kernel.sym_flags[s] & kernel.SF_ZP != 0:
        return reg.F_ZP
    return 0


def local(t, slot):
    """Push a parameter or local of the function being compiled."""
    settle()
    reg.push_slot(t, slot)


def parameter(f, i):
    """Push parameter `i` of function `f`, for an argument to be stored in. After the first
    one stored, an argument is waiting in `f`'s frame while the next is worked out. The arguments
    of a saving call wait in temporaries of the caller instead (saving())."""
    global outer, argument_count
    settle()
    t = kernel.member_type[kernel.sym_members[f] + i]
    if saving(f):
        if argument_count == MAX_ARGUMENTS:
            err.fatal(err.E_OPERANDS_FULL)
        argument_slot[argument_count] = reg.temp(typetab.size(t))
        reg.push_memory(t, reg.own, argument_slot[argument_count], 0, 0, kernel.NO_SYM)
        argument_count += 1
        return
    reg.push_memory(kernel.member_type[kernel.sym_members[f] + i], object_symbol(f), i, 0, 0,
                    kernel.NO_SYM)
    if i > 0 and not in_register(f, i - 1):
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
        t = pointer_type(op)
        if t == typetab.NO_TYPE:
            t = reg.unify(first, second)
    if not typetab.is_number(t) and not typetab.is_untyped(t) and not typetab.is_pointer(t):
        err.fatal(err.E_TYPE)
    return t


def pointer_type(op):
    """If an operand of `op` is a pointer, the type of the result: a pointer plus or minus a
    number is a pointer, and the difference of two pointers of one type a word. The other
    operand is then added as a word. typetab.NO_TYPE if neither is a pointer."""
    first = reg.depth - 2
    second = reg.depth - 1
    pointer = first
    other = second
    if typetab.is_pointer(reg.op_type[second]):
        pointer = second
        other = first
    t = reg.op_type[pointer]
    if not typetab.is_pointer(t):
        return typetab.NO_TYPE
    if op == fold.SUB and reg.op_type[other] == t:
        reg.op_type[pointer] = typetab.WORD_TYPE
        reg.op_type[other] = typetab.WORD_TYPE
        return typetab.WORD_TYPE
    if op != fold.ADD and (op != fold.SUB or pointer == second):
        err.fatal(err.E_TYPE)
    if reg.op_type[other] == typetab.NEGATIVE_TYPE:
        reg.fit(other, typetab.INT_TYPE)
    elif typetab.is_untyped(reg.op_type[other]):
        reg.fit(other, typetab.WORD_TYPE)
    if reg.op_type[other] != typetab.INT_TYPE:
        reg.assignable(other, typetab.WORD_TYPE)
    return t


def fold_constants(op, t):
    """Replace the two newest operands, both constants, by what `op` gives for them. A result
    without a type keeps the mark of a number made by `~` or unary `-` (reg.F_WRAPS) unless
    `op` is one whose low bits depend on the high bits of its operands: `/`, `mod`, `>>`."""
    first = reg.depth - 2
    second = reg.depth - 1
    wrapped = (reg.op_flags[first] | reg.op_flags[second]) & reg.F_WRAPS
    if op == fold.DIV or op == fold.REM or op == fold.SHR:
        wrapped = 0
    if typetab.is_untyped(t):
        value, negative = fold.exact(op, reg.op_value[first], reg.op_type[first] == typetab.NEGATIVE_TYPE,
                                     reg.op_value[second], reg.op_type[second] == typetab.NEGATIVE_TYPE)
        t = typetab.NUMBER_TYPE
        if negative:
            t = typetab.NEGATIVE_TYPE
    else:
        value = fold.typed(op, t, reg.op_value[first], reg.op_value[second])
        wrapped = 0
    reg.pop()
    reg.pop()
    reg.push(reg.O_CONST, t, value)
    reg.op_flags[reg.depth - 1] = wrapped


def exponent(value):
    """n if `value` is 2 to the power n, or reg.NONE."""
    for n in range(0, 16):
        if value == 1 << n:
            return n
    return reg.NONE


def reduce(op, t):
    """Turn `*`, `/` or `mod` by a constant power of two into a shift or a mask, by changing
    the constant. Returns the operator to use, or 0 if a call of the run-time library has
    replaced the operands by the result. A divisor known to be 0 is a call too: only a constant
    divided by the constant 0 is an error (FOLD)."""
    if op == fold.MUL and reg.op_kind[reg.depth - 2] == reg.O_CONST:
        reg.swap()
    second = reg.depth - 1
    n = reg.NONE
    if reg.op_kind[second] == reg.O_CONST:
        n = exponent(reg.op_value[second])
        if op == fold.MUL and reg.op_value[second] == 0:
            return fold.BAND            # x * 0 is x & 0
    if n == reg.NONE and op == fold.MUL and typetab.size(t) == 1 and reg.op_kind[second] == reg.O_CONST \
            and short_multiply(t):
        return 0
    if n == reg.NONE or (op != fold.MUL and typetab.is_signed(t)):
        arithmetic(op, t)               # a shift rounds a negative number the wrong way
        return 0
    if op == fold.REM:
        reg.op_value[second] -= 1
        return fold.BAND
    reg.op_value[second] = n
    reg.op_type[second] = typetab.BYTE_TYPE
    if op == fold.MUL:
        return fold.SHL
    return fold.SHR


def short_multiply(t):
    """A byte variable times 3, the constant on top of the stack: `LDA x` / `ASL A` / `CLC` /
    `ADC x`, never larger than the call (`LDA x` / `LDX #3` / `JSR`), smaller in zero page,
    about 130 cycles quicker, and without the library (docs/codegen.md, "Bytes"). True if done.
    Any other constant, and a byte that is not a plain variable (one in A, an element, one
    that may be a device, at a fixed address or through a pointer), is a call."""
    second = reg.depth - 1
    i = second - 1
    if reg.op_value[second] != 3 or reg.op_kind[i] != reg.O_VAR or reg.op_mode[i] != reg.M_DIRECT \
            or reg.op_symbol[i] == kernel.NO_OBJ:
        return False
    reg.pop()
    reg.release(i)
    reg.load(reg.A, i, 0)
    reg.accumulator(reg.OP_ASL)
    reg.implied(reg.OP_CLC)
    reg.alu(reg.OP_ADC, i, 0)
    reg.pop()
    reg.push_register(t)
    return True


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
        if op == 0:
            return
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
    """A value shifted by a count that is not a constant: for a byte, a loop counted in X; for
    a word, a call of rt_math."""
    first = reg.depth - 2
    second = reg.depth - 1
    if typetab.size(t) != 1:
        n = M_SHL16
        if op == fold.SHR:
            n = M_SHL16 + 1
            if typetab.is_signed(t):
                n = M_SHL16 + 2
        library(n, t)
        return
    reg.take(first)                     # an element would need X, which counts
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
    reg.branch(OP_BEQ, done)
    reg.loop_label(again)
    shift_a(op, op == fold.SHR and typetab.is_signed(t))
    reg.step_x(reg.OP_DEX)
    reg.branch(OP_BNE, again)
    reg.label(done)
    reg.pop()
    reg.pop()
    reg.push_register(t)


def small(i):
    """True if operand `i` is below 256: a constant, or a widened byte."""
    return reg.is_const_byte(i, 1) and reg.const_byte(i, 1) == 0


def arithmetic(op, t):
    """`*`, `/` or `mod` in type `t` on the two newest operands by the run-time library. A
    multiply of two numbers below 256 into a word is mul8x8; mul16 is quicker with the smaller
    operand second."""
    first = reg.depth - 2
    n = M_DIV8 + op - fold.DIV
    if typetab.is_signed(t):
        n += 2
    if typetab.size(t) == 2:
        n += 4
    if op == fold.MUL:
        n = M_MUL8
        if typetab.size(t) == 2 and small(first) and small(first + 1):
            n = M_MUL8X8
        elif typetab.size(t) == 2:
            n = M_MUL16
            if small(first):
                reg.swap()
    library(n, t)


def library(n, t):
    """The two newest operands are the arguments of function `n` of rt_math, the left one for
    its first parameter: call it, as any call is made (call()): an argument for a parameter
    passed in a register stays on the stack, and one for a parameter in the frame is stored
    there first. The result, of type `t`, replaces them in A, or A and X."""
    saved = outer
    f = math_function(n)
    first = reg.depth - 2
    as_parameter(f, 0, first)
    as_parameter(f, 1, first + 1)
    if not in_register(f, 1):
        parameter(f, 1)
        reg.swap()
        store()
    arguments_end(saved)
    call(f, first, True)
    reg.op_type[reg.depth - 1] = t


def as_parameter(f, p, i):
    """Operand `i` is taken as a value of the type of parameter `p` of `f`, which has its size."""
    t = kernel.member_type[kernel.sym_members[f] + p]
    if typetab.size(t) == 1:
        reg.op_size[i] = 1              # a widened byte as the byte it is
    reg.op_type[i] = t


def math_function(n):
    """The symbol of function `n` of rt_math, as rt_math declares it. Unless the module imports
    rt_math, the symbol is made in a scope of its own, again in each function that uses it
    (the function's symbols go when it ends), and the first one used writes the IMP record of
    rt_math, which the build finds the module from."""
    global math_used
    module_name = fixed_name(MATH_MODULE)
    kernel.name_begin()
    i = 0
    for k in range(0, n):
        while MATH_NAMES[i] != C_SPACE:
            i += 1
        i += 1
    while MATH_NAMES[i] != C_SPACE:
        kernel.name_add(MATH_NAMES[i])
        i += 1
    name = kernel.name_end()
    for scope in range(1, kernel.module_count):
        if kernel.module_name[scope] == module_name:
            s, _ = kernel.sym_find(scope, name)
            return s
    s, found = kernel.sym_find(MATH_SCOPE, name)
    if found:
        return s
    s = kernel.sym_add(MATH_SCOPE, name, kernel.K_FUNC)
    if math_obj[n] == kernel.NO_OBJ:
        if not math_used:
            out.imported(module_name)
            math_used = True
        math_obj[n] = out.symbol(out.SYM_FUNCTION, module_name, 0, name)
        math_member[n] = kernel.member_count
        for k in range(0, 3):
            where = REG_NONE
            if k == 2 and typetab.size(MATH_TYPES[3 * n + k]) == 1:
                where = REG_A
            elif k == 2:
                where = REG_AX
            kernel.member_add(MATH_TYPES[3 * n + k], where)
    kernel.sym_obj[s] = math_obj[n]
    kernel.sym_members[s] = math_member[n]
    kernel.sym_params[s] = 2
    kernel.sym_results[s] = 1
    return s


def negate():
    """Unary `-` of the newest operand: 0 minus it."""
    settle()
    t = reg.op_type[reg.depth - 1]
    if typetab.is_untyped(t):
        t = typetab.NUMBER_TYPE
    reg.push(reg.O_CONST, t, 0)
    reg.swap()
    binary(fold.SUB)
    wraps(t)


def wraps(t):
    """The newest operand is what `~` or unary `-` made of an operand of type `t`: if that was a
    number without a type, the result fits an unsigned type by its bits (reg.fit)."""
    if typetab.is_untyped(t):
        reg.op_flags[reg.depth - 1] = reg.F_WRAPS


def complement():
    """Unary `~` of the newest operand: it exclusive-or all ones."""
    settle()
    t = reg.op_type[reg.depth - 1]
    if typetab.is_untyped(t):
        reg.push(reg.O_CONST, typetab.NEGATIVE_TYPE, 0xFFFF)
    else:
        reg.push(reg.O_CONST, t, typetab.narrow(0xFFFF, t))
    binary(fold.BXOR)
    wraps(t)


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
        reg.branch(OP_BCC, skip)
        if target == REGISTERS:
            reg.step_x(reg.OP_INX)
        else:
            reg.modify(reg.OP_INC, target, k)
    else:
        reg.branch(OP_BCS, skip)
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
            # An element on the right is loaded first, which can take its index from A.
            turned = not chained and target != REGISTERS and commutes(op) and reg.op_kind[first] == reg.O_VAR \
                and reg.is_direct(first) and not reg.is_direct(second)
            if turned:
                reg.load(reg.A, second, k)
            if not chained and op == fold.ADD:
                reg.implied(reg.OP_CLC)
            elif not chained and op == fold.SUB:
                reg.implied(reg.OP_SEC)
            chained = True
            if k == 1 and target == REGISTERS:
                reg.transfer(reg.A, reg.Y)
            if turned:
                reg.alu(alu_opcode(op), first, k)
            else:
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
        if reg.op_mode[target] == reg.M_POINTER:
            reg.test(reg.A)             # finding the index again in Y changed the flags
        reg.branch(OP_BNE, skip)
        reg.modify(reg.OP_INC, target, 1)
        reg.label(skip)
    else:
        skip = fbuf.new_label()
        reg.load(reg.A, target, 0)
        reg.test(reg.A)
        reg.branch(OP_BNE, skip)
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
    if count == 2 and amount >= 8 and amount < 16 and not signed:
        shift_bytes(op, first, amount - 8, target)
        return
    if not reg.same_place(first, target):
        shift_copy(op, signed, first, target)
        amount -= 1
    for n in range(0, amount):
        shift_memory(op, signed, target, count)


def shift_bytes(op, first, amount, target):
    """A word shifted by 8 and then `amount` more places, to memory operand `target`: the byte
    that stays moves to the other, shifted on the way, and the byte it leaves is 0."""
    k = 0
    if op == fold.SHR:
        k = 1
    reg.load(reg.A, first, k)
    for n in range(0, amount):
        shift_a(op, False)
    reg.store(reg.A, target, 1 - k)
    reg.put_const(0, target, k)


def operate(op, t, first, second, target):
    """Generate `first op second` in type `t`. `target` is the memory operand the result goes
    to, or REGISTERS."""
    reg.apart(first, second)
    if target != REGISTERS:
        reg.apart(first, target)
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
    reg.unaliased(source, target, True)
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
    reg.unaliased(target + 1, target, False)
    reg.unaliased(target + 2, target, False)
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
    reg.take(i)
    reg.release(i)
    reg.load_const(reg.X, 0)
    reg.load(reg.A, i, 0)
    reg.test(reg.A)
    plus = fbuf.new_label()
    reg.branch(OP_BPL, plus)
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
    if typetab.is_record(source) or typetab.is_record(t) or typetab.is_func(t):
        err.fatal(err.E_TYPE)       # a function type's value comes from @f, which joins its class
    if t == typetab.BOOL_TYPE:
        if source != typetab.BOOL_TYPE:
            reg.push(reg.O_CONST, typetab.NUMBER_TYPE, 0)
            cond.compare(fold.NE)
        return
    cond.value()
    if typetab.is_array(source):
        err.fatal(err.E_ARRAY_VALUE)
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
    t = reg.op_type[i]
    if not typetab.is_number(t) and not typetab.is_untyped(t) and not typetab.is_pointer(t):
        err.fatal(err.E_TYPE)
    if reg.op_kind[i] == reg.O_ADDR:
        reg.release(i)
        reg.load(reg.X, i, 1)
        reg.load(reg.A, i, 0)
        reg.become(i, reg.O_AX, t)
    if reg.is_const_byte(i, k):
        value = reg.const_byte(i, k)
        reg.pop()
        reg.push(reg.O_CONST, typetab.BYTE_TYPE, value)
        return
    if reg.op_kind[i] == reg.O_VAR:
        reg.op_value[i] = reg.offset(i, k)
    elif reg.op_kind[i] == reg.O_AX:
        reg.release(i)
        reg.load(reg.A, i, k)
        reg.become(i, reg.O_A, typetab.BYTE_TYPE)
    reg.op_type[i] = typetab.BYTE_TYPE
    reg.op_size[i] = 1


def size_of(t):
    constant(typetab.NUMBER_TYPE, typetab.size(t))


def length():
    """`len(a)`: the newest operand, an array, is replaced by how many elements it has."""
    settle()
    t = reg.op_type[reg.depth - 1]
    if not typetab.is_array(t):
        err.fatal(err.E_TYPE)
    reg.pop()
    reg.push(reg.O_CONST, typetab.NUMBER_TYPE, typetab.length(t))


# ---- Elements, pointers and addresses -----------------------------------------------------

def index():
    """`a[i]` or `p[i]`: the newest operand is the index and the one under it is indexed, an
    array in memory or a pointer. They become one operand: the element (docs/codegen.md,
    "Operands")."""
    base = reg.depth - 2
    if pend_op != 0:
        base = reg.depth - 3            # the index is an operation still to be done
    t = reg.op_type[base]
    if typetab.is_array(t):
        array_index(base, t)
        return
    if not typetab.is_pointer(t):
        err.fatal(err.E_NOT_INDEXED)
    e = typetab.base(t)
    size = typetab.size(e)
    shift = exponent(size)
    i = index_value(False)
    if shift > 3 and (reg.op_kind[i] != reg.O_CONST or reg.op_value[i] != 0):
        err.fatal(err.E_ELEMENT_SIZE)
    if reg.op_kind[i] == reg.O_CONST:
        if reg.op_value[i] != 0 and (size > 256 or reg.op_value[i] > (256 - size) // size):
            err.fatal(err.E_RANGE)
        reg.op_value[i] = reg.op_value[i] * size
    else:
        if shift > 0:
            constant(typetab.BYTE_TYPE, shift)
            binary(fold.SHL)
            settle()
        reg.into_memory(i)
    if not reg.dereferenced(base):
        to_zero_page(base)
    pointed(base, e)


def index_value(big):
    """The newest operand is an index: settle it, and check that it is a `byte`, or if `big`
    a `word`. Returns where it is."""
    settle()
    cond.value()
    i = reg.depth - 1
    t = reg.op_type[i]
    if big:
        if typetab.is_untyped(t):
            reg.fit(i, typetab.WORD_TYPE)
        reg.assignable(i, typetab.WORD_TYPE)
    elif typetab.is_untyped(t):
        reg.fit(i, typetab.BYTE_TYPE)
    elif t == typetab.WORD_TYPE or t == typetab.INT_TYPE:
        err.fatal(err.E_BYTE_INDEX)
    elif t != typetab.BYTE_TYPE:
        err.fatal(err.E_TYPE)
    return i


def array_index(base, t):
    """An element of the array `base`. A constant index is added to its address; a variable
    one is in X; a big array is reached through a pointer worked out in zero page. `a[i + c]`
    and `a[i - c]` add the constant to the address too."""
    global pend_op
    n = typetab.length(t)
    e = typetab.base(t)
    size = typetab.size(e)
    step = reg.op_stride[base]          # from one element to the next
    if typetab.is_rows(t):
        step = size * step
    big = n > 256 or (typetab.is_rows(t) and size > 1)
    top = reg.depth - 1
    if (pend_op == fold.ADD or pend_op == fold.SUB) and (pend_type == typetab.BYTE_TYPE or big) \
            and (step == 1 or big) and reg.op_mode[base] == reg.M_DIRECT and reg.op_kind[top] == reg.O_CONST \
            and reg.op_kind[top - 1] == reg.O_VAR and reg.is_direct(top - 1):
        folded = reg.op_value[top] * step
        if pend_op == fold.SUB:
            folded = 0 - folded
        reg.op_value[base] = (reg.op_value[base] + folded) & 0xFFFF
        pend_op = 0
        reg.pop()
    i = index_value(big)
    mode = reg.op_mode[base]
    if reg.op_kind[i] == reg.O_CONST:
        if reg.op_value[i] >= n:
            err.fatal(err.E_RANGE)
        reg.op_value[base] = (reg.op_value[base] + reg.op_value[i] * step) & 0xFFFF
        reg.pop()
    elif big and mode == reg.M_DIRECT:
        element_pointer(base, e)
    elif step != 1 or big or mode == reg.M_INDEXED or (mode == reg.M_POINTER and reg.op_kind[base + reg.INDEX] != reg.O_CONST):
        err.fatal(err.E_TWO_INDEXES)
    else:
        if mode == reg.M_POINTER:       # Y is the index plus where the array is: `p.marks[i]`
            constant(typetab.BYTE_TYPE, (reg.offset(base, 0) + reg.op_value[base + reg.INDEX]) & 0xFF)
            binary(fold.ADD)
            settle()
            reg.op_value[base] = 0
        reg.into_memory(i)              # in X, or in Y after what a pointer points at
        reg.take_index(base)
        if mode == reg.M_DIRECT:
            reg.op_mode[base] = reg.M_INDEXED
    reg.op_type[base] = e
    reg.op_size[base] = size
    if typetab.is_column(t):
        reg.op_stride[base] = n * reg.op_stride[base]


def element_pointer(base, e):
    """The newest operand, a word, is the index of an element of the array `base` that the
    index registers cannot reach. The index is shifted by the element size; the pointer, a
    zero page temporary, is the array's address plus 256 times the high byte of that, and the
    low byte is the index in Y, which (zp),Y adds with its carry. A word's second byte is then
    an INY away (the low byte is even). Elements of more than two bytes, whose fields are
    reached by Y, have the whole index added to the pointer and Y = 0."""
    size = typetab.size(e)
    shift = exponent(size)
    if shift > 15:
        err.fatal(err.E_ELEMENT_SIZE)
    if shift > 0:
        constant(typetab.BYTE_TYPE, shift)
        binary(fold.SHL)
    settle()
    i = reg.depth - 1
    reg.into_memory(i)
    whole = shift > 1 or typetab.is_array(e)       # Y reaches the parts: all of i is added
    reg.duplicate(base)
    a = reg.depth - 1
    reg.op_kind[a] = reg.O_ADDR
    if reg.op_symbol[a] == kernel.NO_OBJ:
        reg.op_kind[a] = reg.O_CONST
    reg.describe_temp(a + 1, typetab.pointer_to(e))
    reg.zero_page(a + 1)
    reg.implied(reg.OP_CLC)
    if whole:
        reg.load(reg.A, i, 0)
        reg.alu(reg.OP_ADC, a, 0)
        reg.store(reg.A, a + 1, 0)
    reg.load(reg.A, i, 1)
    reg.alu(reg.OP_ADC, a, 1)
    reg.store(reg.A, a + 1, 1)
    if not whole:
        reg.load(reg.A, a, 0)
        reg.store(reg.A, a + 1, 0)
    reg.pop()
    reg.copy(a + 1, base)
    reg.op_size[i] = 1
    if whole:
        reg.become(i, reg.O_CONST, typetab.BYTE_TYPE)
    pointed(base, e)


def pointed(base, e):
    """Operand `base`, a pointer in zero page, becomes the `e` it points at, at the index that
    is the newest operand, which leaves the stack."""
    reg.take_index(base)
    reg.op_mode[base] = reg.M_POINTER
    reg.op_type[base] = e
    reg.op_size[base] = typetab.size(e)
    reg.op_value[base] = 0
    reg.op_stride[base] = 1


def record_of():
    """A field of the newest operand is wanted: if it is a pointer to a record, it becomes
    the record it points at (p[0]). Returns the record's type."""
    settle()
    i = reg.depth - 1
    t = reg.op_type[i]
    if typetab.is_pointer(t) and typetab.is_record(typetab.base(t)):
        constant(typetab.BYTE_TYPE, 0)
        index()
    if reg.op_kind[i] != reg.O_VAR or not typetab.is_record(reg.op_type[i]):
        err.fatal(err.E_NOT_RECORD)
    return reg.op_type[i]


def field(place, t):
    """The newest operand, a record, becomes its field of type `t` that is `place` bytes into
    it: as for a constant index, byte k of the field is byte `place` + k of the record. Through
    a pointer, every byte must be within reach of Y."""
    i = reg.depth - 1
    reg.op_value[i] = reg.offset(i, place)
    reg.op_type[i] = t
    reg.op_size[i] = typetab.size(t)
    if reg.op_mode[i] == reg.M_POINTER and reg.op_value[i] + typetab.size(t) > 256:
        err.fatal(err.E_RANGE)


def to_zero_page(i):
    """Operand `i`, a pointer that cannot be used through (zp),Y as it is, is copied to a zero
    page temporary, which it becomes."""
    to_temporary(i, True)


def to_temporary(i, in_zero_page):
    """Operand `i` is copied to a temporary, in zero page if `in_zero_page`, which it becomes."""
    t = reg.op_type[i]
    j = reg.depth
    reg.describe_temp(j, t)
    if in_zero_page:
        reg.zero_page(j)
    reg.release(i)
    for k in range(0, typetab.size(t)):
        reg.put(i, k, j, k)
    reg.become(i, reg.O_VAR, t)
    reg.copy(j, i)


def address():
    """`@x`: the newest operand, a variable or an element of an array, is replaced by its
    address. That of an array is a pointer to its first element. An array stored by column
    has no such pointer, and its elements have no address."""
    settle()
    i = reg.depth - 1
    t = reg.op_type[i]
    mode = reg.op_mode[i]
    if reg.op_kind[i] != reg.O_VAR or (reg.op_flags[i] & reg.F_TEMP != 0 and mode != reg.M_POINTER) \
            or (typetab.size(t) > 1 and reg.op_stride[i] > 1) or typetab.is_column(t):
        err.fatal(err.E_NO_ADDRESS)
    if typetab.is_array(t):
        t = typetab.base(t)
    disp = 0
    if mode == reg.M_POINTER:
        disp = reg.op_value[i]          # the pointer itself, and what is added to it
        reg.op_value[i] = 0
    elif reg.op_symbol[i] == kernel.NO_OBJ:
        reg.op_kind[i] = reg.O_CONST
    else:
        reg.op_kind[i] = reg.O_ADDR
    reg.op_mode[i] = reg.M_DIRECT
    reg.op_type[i] = typetab.pointer_to(t)
    reg.op_size[i] = 2
    reg.op_stride[i] = 1
    if mode != reg.M_DIRECT:
        reg.keep(i + reg.INDEX)
        binary(fold.ADD)
    if disp != 0:
        constant(typetab.NUMBER_TYPE, disp)
        binary(fold.ADD)


def anonymous():
    """A new symbol of constant data with no name of its own: `module.$1`, `module.$2`, ..."""
    global data_count
    data_count += 1
    kernel.name_begin()
    kernel.name_add(C_DOLLAR)
    place = 10000
    started = False
    while place > 0:
        digit = (data_count // place) % 10
        if digit != 0 or started or place == 1:
            kernel.name_add(C_ZERO + digit)
            started = True
        place = place // 10
    return out.symbol(out.SYM_DATA, kernel.module_name[0], 0, kernel.name_end())


def string():
    """The string LEX has just read, used as a value: a `^byte` to constant data that holds
    it, with a zero after it."""
    settle()
    symbol = anonymous()
    out.data(symbol, lex.string_length + 1)
    for i in range(0, lex.string_length):
        out.data_byte(lex.string[i])
    out.data_byte(0)
    reg.push(reg.O_ADDR, typetab.pointer_to(typetab.BYTE_TYPE), 0)
    reg.op_symbol[reg.depth - 1] = symbol


def table_element(where, step):
    """The newest operand, a constant or an address, is an element of the constant table
    being made: its byte k goes to byte `where` + k * `step` of the table."""
    i = reg.depth - 1
    for k in range(0, typetab.size(reg.op_type[i])):
        if reg.op_kind[i] == reg.O_ADDR:
            out.table_fix(where + k * step, fbuf.FIX_LOW + k, reg.op_symbol[i], reg.op_slot[i], reg.op_value[i])
        else:
            out.table[where + k * step] = reg.const_byte(i, k)
    reg.pop()


def copy_array(symbol, size):
    """Copy `size` bytes of the constant data `symbol` to the newest operand, an array: a page
    at a time with X counting up, then what is left with X counting down to 1."""
    target = reg.depth - 1
    reg.push_memory(typetab.BYTE_TYPE, symbol, fbuf.NO_SLOT, 0, 0, kernel.NO_SYM)
    source = reg.depth - 1
    start = reg.op_value[target]
    reg.op_flags[target] = reg.op_flags[target] & ~reg.F_ZP     # an address below it may be out of zero page
    pages = size >> 8
    if pages > 0:
        reg.load_const(reg.X, 0)
    for part_number in range(0, 2):
        count = pages
        first = 0
        if part_number == 1:
            count = 1
            first = (pages << 8) - 1
            if size & 0xFF == 0:
                count = 0
            else:
                reg.load_const(reg.X, size & 0xFF)
        if count > 0:
            top = fbuf.new_label()
            reg.loop_label(top)
            for p in range(0, count):
                reg.op_value[source] = (first + (p << 8)) & 0xFFFF
                reg.op_value[target] = (start + first + (p << 8)) & 0xFFFF
                reg.direct(OP_LDA + reg.INDEXED_FORM, source, 0)
                reg.direct(OP_STA + reg.INDEXED_FORM, target, 0)
            if part_number == 0:
                reg.step_x(reg.OP_INX)
            else:
                reg.step_x(reg.OP_DEX)
            reg.branch(OP_BNE, top)
    reg.op_value[target] = start
    reg.forget()
    reg.pop()


# ---- Calls -------------------------------------------------------------------------------

def accept(t):
    """Check that the newest operand can be given to something of type `t`."""
    settle()
    reg.assignable(reg.depth - 1, t)


def hold():
    """The newest operand is an argument for a register and another argument follows. It
    may wait in A, or A and X, until one of those is needed, but not in the flags."""
    global held_count
    settle()
    cond.value()
    if held_count == MAX_HELD:
        err.fatal(err.E_OPERANDS_FULL)
    held_operand[held_count] = reg.depth - 1
    held_count += 1


def protect():
    """A call is about to be made, or an expansion that may change variables to begin: each
    argument waiting for a register that is memory such code could change is copied to a
    temporary, so that arguments are still taken from left to right."""
    for n in range(0, held_count):
        i = held_operand[n]
        if reg.op_kind[i] == reg.O_VAR and (reg.op_mode[i] != reg.M_DIRECT
                                            or reg.op_flags[i] & (reg.F_TEMP | reg.F_DATA) == 0):
            to_temporary(i, False)


def register_of(f, i):
    """Where parameter `i` of function or function type `f` is passed (docs/code-model.md,
    "Convention"): its binding, for an `extern` or `asm` function; otherwise A, X, Y for the
    first three if they are bytes, or A and X for a first word and Y for a byte after it."""
    m = kernel.sym_members[f]
    if by_registers(f):
        return kernel.member_value[m + i]
    wide = typetab.size(kernel.member_type[m]) == 2
    if i == 0 and wide:
        return REG_AX
    if i > 2 or (wide and i > 1):
        return REG_NONE
    for j in range(1, i + 1):
        if typetab.size(kernel.member_type[m + j]) != 1:
            return REG_NONE
    if wide:
        return REG_Y
    return REG_A + i


def in_register(f, i):
    """True if the argument for parameter `i` of `f` waits as an operand to be loaded into
    registers at the call: always so for `extern` and `asm` functions, never for a saving call."""
    return by_registers(f) or (not saving(f) and register_of(f, i) != REG_NONE)


def register_count(f):
    """How many of `f`'s parameters, from the first, are passed in registers."""
    n = 0
    while n < kernel.sym_params[f] and register_of(f, n) != REG_NONE:
        n += 1
    return n


def load_registers(f, first, count):
    """Put the arguments of `f` for its first `count` parameters, the operands from `first`
    on, where those parameters are: the carry flag first, because finding it can take A,
    then Y, X and A. An argument that is still in A can go from there to where it belongs."""
    settle()
    if count == 0:
        return
    if register_of(f, count - 1) != REG_C:
        cond.value()
    for i in range(first, first + count):
        where = register_of(f, i - first)
        if reg.is_direct(i) or (count == 1 and where != REG_AX and where != REG_AY and where != REG_XY):
            continue
        if count == 1 and where == REG_AX:
            reg.take(i)                 # the low byte first: an element's index is in X
        else:
            reg.into_memory(i)          # its index register could be another's
    for i in range(0, count):
        if register_of(f, i) == REG_C:
            cond.carry(first + i)
    held = reg.owner
    if held != reg.NONE and held >= first:
        if reg.op_kind[held] == reg.O_AX and register_of(f, held - first) != REG_AX:
            reg.spill(held)
        reg.release(held)
    for r in range(reg.Y, reg.A - 1, -1):
        for i in range(0, count):
            k = REGISTER_BYTES[register_of(f, i) * 3 + r]
            if k != NO_BYTE:
                reg.load(r, first + i, k)


def receive(f):
    """The entry of ordinary function `f`: store the parameters passed in registers in their
    slots, which then hold them as any variable does. The registers still hold copies."""
    for i in range(0, register_count(f)):
        where = register_of(f, i)
        reg.push_slot(kernel.member_type[kernel.sym_members[f] + i], i)
        if where == REG_AX:
            reg.store(reg.A, reg.depth - 1, 0)
            reg.store(reg.X, reg.depth - 1, 1)
        else:
            reg.store(where - REG_A, reg.depth - 1, 0)
        reg.pop()


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


def through_pointer():
    """The newest operand, a value of a function type, is to be called through. It becomes the
    callee, as an O_FUNC whose op_var is the symbol that declares the type, and stays under
    the arguments until the call, which is a JSR to a JMP (pointer). The pointer must be a
    two-byte variable, which the linker keeps from lying across a page boundary, where the
    NMOS 6502 would read the JMP's address wrongly: anything else (an element, a field, what a
    pointer points at) is copied to a temporary first."""
    settle()
    i = reg.depth - 1
    t = reg.op_type[i]
    s = reg.op_var[i]
    whole = reg.op_symbol[i] == kernel.NO_OBJ or (reg.op_value[i] == 0 and (
        reg.op_flags[i] & reg.F_TEMP != 0 or (reg.op_symbol[i] == reg.own and reg.slot_size[reg.op_slot[i]] == 2)
        or (s != kernel.NO_SYM and typetab.size(kernel.sym_type[s]) == 2)))
    if reg.op_kind[i] != reg.O_VAR or reg.op_mode[i] != reg.M_DIRECT or not whole:
        to_temporary(i, False)
    reg.use(i)
    reg.op_kind[i] = reg.O_FUNC
    reg.op_var[i] = typetab.base(t)


def through(f):
    """True if `f` is a function type: a call of it is through a pointer."""
    return kernel.sym_kind[f] == kernel.K_TYPE


def stub(i):
    """The label of the JMP (pointer) for the callee operand `i`, a call through a pointer:
    one per pointer in each function, written after its code (function_end())."""
    global stub_count
    for n in range(0, stub_count):
        if stub_symbol[n] == reg.op_symbol[i] and stub_slot[n] == reg.op_slot[i] \
                and stub_value[n] == reg.op_value[i]:
            return stub_label[n]
    if stub_count == MAX_STUBS:
        err.fatal(err.E_CALLS_FULL)
    stub_label[stub_count] = fbuf.new_label()
    stub_symbol[stub_count] = reg.op_symbol[i]
    stub_slot[stub_count] = reg.op_slot[i]
    stub_value[stub_count] = reg.op_value[i]
    stub_count += 1
    return stub_label[stub_count - 1]


def saving(f):
    """True if a call of `f` saves the caller's frame (docs/code-model.md, "Recursion"): the
    caller is `recursive`, and so is `f`, a function, or the function type `f`."""
    if not saves_frame:
        return False
    if through(f):
        return typetab.is_recursive(kernel.sym_type[f])
    return kernel.sym_flags[f] & kernel.SF_RECURSIVE != 0


def frame_routines():
    """The symbols of rt_frame.push and rt_frame.pop_y, and the IMP record of rt_frame, which
    the first saving call of the module writes: the build finds the module from it. A module
    that imports rt_frame itself has the symbols already."""
    global frame_push, frame_pop
    if frame_push != kernel.NO_OBJ:
        return
    module_name = fixed_name(FRAME_MODULE)
    for scope in range(1, kernel.module_count):
        if kernel.module_name[scope] == module_name:
            s, _ = kernel.sym_find(scope, fixed_name(PUSH_NAME))
            frame_push = object_symbol(s)
            s, _ = kernel.sym_find(scope, fixed_name(POP_NAME))
            frame_pop = object_symbol(s)
            return
    out.imported(module_name)
    frame_push = out.symbol(out.SYM_FUNCTION, module_name, 0, fixed_name(PUSH_NAME))
    frame_pop = out.symbol(out.SYM_FUNCTION, module_name, 0, fixed_name(POP_NAME))


def fixed_name(text):
    kernel.name_begin()
    for i in range(0, len(text)):
        kernel.name_add(text[i])
    return kernel.name_end()


def slot_byte(opcode, symbol, slot, k):
    """The instruction `opcode` (absolute form) on byte `k` of slot `slot` of function `symbol`."""
    j = reg.depth
    reg.describe(j, reg.O_VAR, typetab.BYTE_TYPE)
    reg.op_symbol[j] = symbol
    reg.op_slot[j] = slot
    reg.op_value[j] = k
    if symbol == reg.own and reg.slot_class[slot] == reg.CLASS_ZP:
        reg.op_flags[j] = reg.F_ZP
    reg.direct(opcode, j, 0)


def is_argument(n, first):
    for a in range(first, argument_count):
        if argument_slot[a] == n:
            return True
    return False


def save_frame(f, first):
    """A saving call of `f` is next; its arguments wait in temporaries. Push every byte of the
    frame that can be live: the parameters and locals, and the temporaries in use but for
    those arguments and the copy of the pointer called through, if there is one. Then move
    the arguments to `f`'s parameters, which can be the caller's own."""
    global saved_count, argument_count
    frame_routines()
    skip = fbuf.NO_SLOT
    if through(f) and reg.op_flags[first - 1] & reg.F_TEMP != 0:
        skip = reg.op_slot[first - 1]
    base = argument_count - kernel.sym_params[f]
    saved_count = 0
    for n in range(0, fbuf.FIRST_TEMP + reg.temp_count):
        if n < reg.local_count or (n >= fbuf.FIRST_TEMP and reg.slot_busy[n] and n != skip
                                   and not is_argument(n, base)):
            saved_slot[saved_count] = n
            saved_count += 1
            for k in range(0, reg.slot_size[n]):
                slot_byte(OP_LDA, reg.own, n, k)
                fbuf.op_fix(fbuf.OP_JSR, fbuf.FIX_ADDRESS, frame_push, fbuf.NO_SLOT, 0)
    if saved_count > 0:
        out.call(frame_push, 0, outer)
    count = register_count(f)
    for p in range(count, kernel.sym_params[f]):
        n = argument_slot[base + p]
        for k in range(0, reg.slot_size[n]):
            slot_byte(OP_LDA, reg.own, n, k)
            slot_byte(OP_STA, object_symbol(f), p, k)
    for r in range(reg.Y, reg.A - 1, -1):      # the registers last: nothing may change them
        for p in range(0, count):
            k = REGISTER_BYTES[register_of(f, p) * 3 + r]
            if k != NO_BYTE:
                slot_byte(reg.LOAD_ABSOLUTE[r], reg.own, argument_slot[base + p], k)
    for p in range(0, kernel.sym_params[f]):
        reg.slot_busy[argument_slot[base + p]] = False
    argument_count = base


def restore_frame():
    """After a saving call: pop what save_frame() pushed, last byte first, through Y."""
    if saved_count > 0:
        out.call(frame_pop, 0, outer)
    for i in range(saved_count - 1, -1, -1):
        n = saved_slot[i]
        for k in range(reg.slot_size[n] - 1, -1, -1):
            fbuf.op_fix(fbuf.OP_JSR, fbuf.FIX_ADDRESS, frame_pop, fbuf.NO_SLOT, 0)
            slot_byte(OP_STY, reg.own, n, k)


def call(f, first, wanted):
    """Call function `f`. The arguments passed in registers (all of an `extern` or `asm`
    function's) are the operands from `first` on; the others are in its frame already. Those of
    a saving call are all in temporaries. Pushes result(f) if it is `wanted`. An `extern` function is at a fixed
    address; any other is reached through its symbol, with a CALL record. A call through a
    pointer (`f` a function type) has the pointer under the arguments, as through_pointer()
    left it."""
    global held_count
    settle()
    while held_count > 0 and held_operand[held_count - 1] >= first:
        held_count -= 1
    if reg.owner != reg.NONE and reg.owner < first:
        reg.spill(reg.owner)            # before the arguments are loaded over it
    if kernel.sym_params[f] > 0 and in_register(f, 0):
        load_registers(f, first, reg.depth - first)
        while reg.depth > first:
            reg.pop()
    reg.clobber()
    flags = 0
    if saving(f):
        save_frame(f, first)
        flags = out.CALL_SAVES
    if kernel.sym_flags[f] & kernel.SF_EXTERN != 0:
        fbuf.op_word(fbuf.OP_JSR, kernel.sym_value[f])
    elif through(f):
        fbuf.call_label(stub(first - 1))
        out.call(object_symbol(f), flags | out.CALL_POINTER, outer)
    else:
        callee = object_symbol(f)
        fbuf.op_fix(fbuf.OP_JSR, fbuf.FIX_ADDRESS, callee, fbuf.NO_SLOT, 0)
        out.call(callee, flags, outer)
    if flags != 0:
        restore_frame()
    reg.forget()
    if through(f):
        reg.pop()
    if wanted:
        result(f)


def code_address(s):
    """`@f`, where the newest operand is function `s`, an interrupt function: its address, a
    `^byte`."""
    reg.pop()
    reg.push(reg.O_ADDR, typetab.pointer_to(typetab.BYTE_TYPE), 0)
    reg.op_symbol[reg.depth - 1] = object_symbol(s)


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
    reg.take(i)
    reg.release(i)
    if typetab.size(reg.op_type[i]) == 2:
        reg.load(reg.X, i, 1)
    reg.load(reg.A, i, 0)
    reg.pop()


def ret():
    """Return from the function. A call just made returns for it instead. An interrupt
    function goes to its exit code."""
    if leave != reg.NONE:
        reg.jump(leave)
    elif not fbuf.tail_call():
        fbuf.op(OP_RTS)


# What an interrupt function does on entry and on exit (docs/code-model.md, "Interrupts"): save
# A, X and Y on the stack, and clear the decimal flag, which an NMOS 6502 does not clear on an
# interrupt; restore them, and RTI. The 65C02 pushes X and Y without A, and clears the flag itself.
ENTRY_6502 = b"\x48\x8A\x48\x98\x48\xD8"       # PHA TXA PHA TYA PHA CLD
EXIT_6502 = b"\x68\xA8\x68\xAA\x68\x40"        # PLA TAY PLA TAX PLA RTI
ENTRY_65C02 = b"\x48\xDA\x5A"                    # PHA PHX PHY
EXIT_65C02 = b"\x7A\xFA\x68\x40"                # PLY PLX PLA RTI


def interrupt_entry():
    """The function being compiled is an interrupt function: its entry code, here."""
    global leave
    leave = fbuf.new_label()
    if cpu == 0:
        for i in range(0, len(ENTRY_6502)):
            fbuf.op(ENTRY_6502[i])
    else:
        for i in range(0, len(ENTRY_65C02)):
            fbuf.op(ENTRY_65C02[i])


def interrupt_exit():
    """The exit code of an interrupt function, where its body ends and every `return` goes."""
    global leave
    reg.label(leave)
    leave = reg.NONE
    if cpu == 0:
        for i in range(0, len(EXIT_6502)):
            fbuf.op(EXIT_6502[i])
    else:
        for i in range(0, len(EXIT_65C02)):
            fbuf.op(EXIT_65C02[i])


def loop_begin():
    reg.loop_depth += 1


def loop_end():
    reg.loop_depth -= 1


# ---- Functions ---------------------------------------------------------------------------

def function_begin(symbol):
    """Start generating the function whose object-file symbol is `symbol`."""
    global pend_op, outer, leave, stub_count, saves_frame, argument_count, held_count
    fbuf.begin()
    reg.begin(symbol)
    pend_op = 0
    outer = out.NO_OUTER
    leave = reg.NONE
    stub_count = 0
    saves_frame = False
    argument_count = 0
    held_count = 0


def slots(first, count):
    for n in range(first, first + count):
        out.slot(reg.slot_size[n], reg.slot_class[n], reg.slot_weight[n], reg.slot_kind[n],
                 reg.slot_name[n])


def function_end(flags):
    """End the function and write it to the object file: its parameters and locals, then its
    temporaries, then its code."""
    if leave != reg.NONE:
        interrupt_exit()
    elif fbuf.runs_on():
        ret()
    for n in range(0, stub_count):
        reg.label(stub_label[n])        # reached only by the JSRs of pointer calls: nothing is known
        if stub_symbol[n] == kernel.NO_OBJ:
            fbuf.op_word(fbuf.OP_JMP_INDIRECT, stub_value[n])
        else:
            fbuf.op_fix(fbuf.OP_JMP_INDIRECT, fbuf.FIX_ADDRESS, stub_symbol[n], stub_slot[n], stub_value[n])
    fbuf.finish(reg.own, reg.local_count)
    out.function_begin(reg.own, flags)
    slots(0, reg.local_count)
    slots(fbuf.FIRST_TEMP, reg.temp_count)
    out.function_end()


# ---- Initial values ----------------------------------------------------------------------

def initial(s, source, slot, value):
    """Variable `s` starts with the constant `value`, or if `source` is not kernel.NO_OBJ, the
    address `value` after the symbol `source` (and its slot `slot`); an array is copied from
    the constant data `source`."""
    global init_count
    if init_count == MAX_INITS:
        err.fatal(err.E_INITS_FULL)
    init_source[init_count] = source
    init_slot[init_count] = slot
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
        t = init_type[n]
        reg.push_memory(t, init_symbol[n], fbuf.NO_SLOT, init_address[n], init_flags[n], kernel.NO_SYM)
        if typetab.is_array(t):
            copy_array(init_source[n], typetab.size(t))
            reg.pop()
        else:
            if init_source[n] == kernel.NO_OBJ:
                reg.push(reg.O_CONST, t, init_value[n])
            else:
                reg.push(reg.O_ADDR, t, init_value[n])
                reg.op_symbol[reg.depth - 1] = init_source[n]
                reg.op_slot[reg.depth - 1] = init_slot[n]
            store()
    init_count = 0
    init_part = symbol
    function_end(0)
