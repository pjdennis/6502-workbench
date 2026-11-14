"""GEN: instruction selection and register tracking.

Owns
- the operand stack. Parsing an operand gives a description of it, not code: a constant, a
  variable, a value now in A, a condition now in the flags (docs/code-model.md, "Generating
  the code"). EXPR pushes and pops the descriptions; GEN reads them when an operation needs
  its operands somewhere, and only then are instructions chosen. The stack lives here and not
  in EXPR because GEN must read it and EXPR must call GEN, and modules cannot import each
  other;
- what A, X and Y are known to hold, so that a load which would change nothing is left out.
  The knowledge is dropped at every call and label.

Instructions go to FBUF. A finished function goes to OUT.
"""
import err
import fbuf
import kernel
import out

# ---- Operands ----------------------------------------------------------------------------

MAX_OPERANDS = 16

# Operand kinds, and what op_value holds for each
O_CONST = 1             # the constant
O_FUNC = 2              # a function by name: its symbol in the kernel's table
O_VAR = 3               # not used yet: a module-level variable
O_SLOT = 4              # not used yet: a slot of the function being compiled
O_A = 5                 # not used yet: a one-byte value that is in A
O_AX = 6                # not used yet: a two-byte value in A (low) and X (high)
O_FLAGS = 7             # not used yet: a bool that is a condition in the flags
O_INDEXED = 8           # not used yet: an element of an array or of what a pointer points to

op_kind = [0] * MAX_OPERANDS
op_type = [0] * MAX_OPERANDS
op_value = [0] * MAX_OPERANDS
depth = 0               # operands on the stack; the newest is depth - 1

# ---- Registers ---------------------------------------------------------------------------

# Where a parameter or result of an `extern` or `asm` function is. Pairs are low byte first.
REG_NONE = 0
REG_A = 1
REG_X = 2
REG_Y = 3
REG_AX = 4
REG_AY = 5
REG_XY = 6
REG_C = 7               # a bool in the carry flag

# The registers whose contents are tracked
A = 0
X = 1
Y = 2
HOLDS_UNKNOWN = 0
HOLDS_CONST = 1         # reg_value is the constant

reg_holds = [0] * 3
reg_value = [0] * 3

OP_LOAD_IMMEDIATE = b"\xA9\xA2\xA0"     # LDA, LDX, LDY #
OP_CLC = 0x18
OP_JSR = 0x20
OP_SEC = 0x38
OP_RTS = 0x60

cpu = 0                 # 0 6502, 1 65C02; from the environment description, when that is read


def init():
    global cpu
    cpu = 0


# ---- The operand stack -------------------------------------------------------------------

def push(kind, t, value):
    """Add an operand to the stack."""
    global depth
    if depth == MAX_OPERANDS:
        err.fatal(err.E_OPERANDS_FULL)
    op_kind[depth] = kind
    op_type[depth] = t
    op_value[depth] = value
    depth += 1


def pop():
    """Take the newest operand off the stack."""
    global depth
    depth -= 1


# ---- Registers ---------------------------------------------------------------------------

def forget():
    """Nothing is known about the registers: after a call, and wherever a branch can arrive."""
    for r in range(0, 3):
        reg_holds[r] = HOLDS_UNKNOWN


def load_const(r, value):
    """Make register `r` (A, X or Y) hold the one-byte constant `value`."""
    if reg_holds[r] == HOLDS_CONST and reg_value[r] == value:
        return
    fbuf.op_byte(OP_LOAD_IMMEDIATE[r], value)
    reg_holds[r] = HOLDS_CONST
    reg_value[r] = value


def set_carry(on):
    if on:
        fbuf.op(OP_SEC)
    else:
        fbuf.op(OP_CLC)


def low_register(register):
    """The tracked register that holds the low byte of pair `register`."""
    if register == REG_XY:
        return X
    return A


def high_register(register):
    if register == REG_AX:
        return X
    return Y


def load_register(register, operand):
    """Put operand number `operand` where an `extern` parameter bound to `register` must be."""
    if op_kind[operand] != O_CONST:
        err.fatal(err.E_UNSUPPORTED)
    value = op_value[operand]
    if register == REG_C:
        set_carry(value != 0)
    elif register <= REG_Y:
        load_const(register - REG_A, value & 0xFF)
    else:
        load_const(low_register(register), value & 0xFF)
        load_const(high_register(register), (value >> 8) & 0xFF)


# ---- Calls and functions -----------------------------------------------------------------

def object_symbol(s):
    """The object-file number of function `s`, which gets its SYM record on first use."""
    if kernel.sym_obj[s] == kernel.NO_OBJ:
        kernel.sym_obj[s] = out.symbol(out.SYM_FUNCTION, kernel.module_name[kernel.sym_scope[s]],
                                       kernel.sym_name[s])
    return kernel.sym_obj[s]


def call_address(address):
    """Call the routine at a fixed address. The linker has no part in it."""
    fbuf.op_word(OP_JSR, address)
    forget()


def call_function(s):
    """Call Lathe function `s`, and tell the linker of the call."""
    callee = object_symbol(s)
    fbuf.op_fix(OP_JSR, fbuf.FIX_ADDRESS, callee, fbuf.NO_SLOT, 0)
    out.call(callee, 0, out.NO_OUTER)
    forget()


def ret():
    """Return from the function."""
    fbuf.op(OP_RTS)


def function_begin():
    """Start generating a function."""
    global depth
    fbuf.begin()
    forget()
    depth = 0


def function_end(symbol, flags):
    """End the function whose object-file symbol is `symbol` and write it to the object file."""
    if fbuf.runs_on():
        ret()
    fbuf.finish(symbol)
    out.function_begin(symbol, flags)
    out.function_end()
