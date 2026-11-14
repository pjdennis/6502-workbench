"""REG: operands, the frame and the registers (the lowest of GEN's three files).

Owns
- the operand stack. Parsing an operand gives a description of it, not code: a constant, a
  variable, a value now in A or in A and X, a condition now in the flags (docs/codegen.md,
  "Operands"). The descriptions are columns indexed by the operand's place on the stack;
- the frame of the function being compiled: its parameters and locals, numbered from 0, and
  its temporaries, numbered from fbuf.FIRST_TEMP until FBUF moves them behind the locals;
- which operand owns A (or A and X). Whatever is about to change a register first calls
  claim(), which stores the owner in a temporary (docs/codegen.md, "Owning a register"). An
  operation frees its own operands with release() before it starts;
- what A, X and Y are known to hold, and whether the N and Z flags show a register's value,
  so that a load or a compare which would change nothing is left out (docs/codegen.md,
  "Remembering register contents");
- the instructions that move one byte between an operand and a register, which is where
  zero page forms, weights and the register memory are dealt with once for all of GEN.

An instruction that takes memory is known here by its opcode in the absolute form. The zero
page form is ZERO_PAGE_FORM less; the immediate form and the accumulator form are
IMMEDIATE_FORM less.
"""
import err
import fbuf
import kernel
import typetab

# ---- Operands ----------------------------------------------------------------------------

MAX_OPERANDS = 16
NONE = 0xFFFF           # no operand; no label

# Operand kinds, and what the columns hold for each
O_CONST = 1             # op_value: the constant, sign-extended to 16 bits if its type is signed
O_FUNC = 2              # op_var: the function's symbol in the kernel's table
O_VAR = 3               # memory. op_symbol, op_slot, op_value: the fix-up that reaches its first
#                         byte; or op_symbol is kernel.NO_OBJ and op_value is a fixed address
O_A = 4                 # a one-byte value that is in A
O_AX = 5                # a two-byte value in A (low) and X (high)
O_COND = 6              # a bool in the flags. op_value: the opcode of the branch taken when it
#                         is true; op_true, op_false: labels that parts of it already branch to
O_ADDR = 7              # an address: op_symbol, op_slot and op_value as for O_VAR. Byte k is
#                         an immediate with a fix-up for its low or high byte

# How a memory operand (O_VAR) is reached: its mode, and its index, which is the description
# at entry i + INDEX (a constant or a byte variable in memory). Byte k of an operand is at
# op_value + k * op_stride: an element of an array stored by column has its bytes N apart.
M_DIRECT = 0            # absolute, or zero page when known
M_INDEXED = 1           # an array element: the index in X (in Y for LDX), then absolute,X
M_POINTER = 2           # what a pointer points at: op_symbol and op_slot are the pointer, in zero
#                         page; Y is the index plus op_value + k * op_stride, then (zp),Y

F_TEMP = 1              # the memory is a temporary, free again when the operand is popped
F_ZP = 2                # the memory is known to be in zero page
F_DATA = 8              # constant data: it cannot be assigned to (4 is cond.F_COMPARED)

INDEX = MAX_OPERANDS + 1                # entry i + INDEX describes the index of operand i
ENTRIES = 2 * INDEX                     # one more than the stack, for swap(), and their indexes
op_kind = [0] * ENTRIES
op_type = [0] * ENTRIES
op_size = [0] * ENTRIES                 # bytes it really has: a byte widened to a word has 1,
#                                         and the bytes above read as 0
op_value = [0] * ENTRIES
op_symbol = [0] * ENTRIES
op_slot = [0] * ENTRIES
op_flags = [0] * ENTRIES
op_var = [0] * ENTRIES                  # the kernel symbol whose weight a use adds to, or NO_SYM
op_true = [0] * ENTRIES
op_false = [0] * ENTRIES
op_mode = [0] * ENTRIES
op_stride = [0] * ENTRIES
depth = 0               # operands on the stack; the newest is depth - 1
owner = NONE            # the operand that is O_A or O_AX, if there is one

# ---- The frame ---------------------------------------------------------------------------

MAX_TEMPS = 64
SLOTS = 256             # slot numbers are one byte
WEIGHTS = b"\x01\x04\x10\x40"           # what one use adds, by how many loops it is inside

CLASS_ZP = 0            # slot and variable classes (docs/object-format.md)
CLASS_EITHER = 1
CLASS_NOT_ZP = 2
SLOT_PARAMETER = 0      # slot kinds
SLOT_LOCAL = 1
SLOT_TEMPORARY = 2

slot_size = [0] * SLOTS
slot_class = [0] * SLOTS
slot_weight = [0] * SLOTS
slot_kind = [0] * SLOTS
slot_name = [0] * SLOTS
slot_busy = [False] * SLOTS             # a temporary: in use
local_count = 0         # parameters and locals
temp_count = 0
own = 0                 # the object-file symbol of the function being compiled
loop_depth = 0          # how many loops the code being generated is inside

# ---- Registers ---------------------------------------------------------------------------

A = 0
X = 1
Y = 2
NO_REG = 3
IN_MEMORY = 4                   # as `flags`: the flags show a byte of memory, not a register

COPY_COUNT = 2                      # how many bytes of memory a register is remembered to equal:
#                                 after `x = y`, A is a copy of both

reg_known = [False] * 3         # the register holds the constant reg_const
reg_const = [0] * 3
reg_copy = [False] * (3 * COPY_COUNT)       # entry r * COPY_COUNT + n: register r holds a copy of the
reg_symbol = [0] * (3 * COPY_COUNT)         # byte of memory that the fix-up reg_symbol, reg_slot,
reg_slot = [0] * (3 * COPY_COUNT)           # reg_offset reaches. The newest of a register's
reg_offset = [0] * (3 * COPY_COUNT)         # entries is its first
flags = NO_REG                  # the register whose value the N and Z flags show, or
flags_symbol = 0                # IN_MEMORY for the byte that the fix-up flags_symbol,
flags_slot = 0                  # flags_slot, flags_offset reaches: the one an INC, DEC or
flags_offset = 0                # shift has just changed

ZERO_PAGE_FORM = 8
IMMEDIATE_FORM = 4
OP_ORA = 0x0D
OP_ASL = 0x0E
OP_AND = 0x2D
OP_ROL = 0x2E
OP_EOR = 0x4D
OP_LSR = 0x4E
OP_ADC = 0x6D
OP_ROR = 0x6E
OP_CMP = 0xCD
OP_DEC = 0xCE
OP_SBC = 0xED
OP_INC = 0xEE
OP_CLC = 0x18
OP_SEC = 0x38
OP_DEX = 0xCA
OP_INX = 0xE8
OP_INY = 0xC8
OP_LDX = 0xAE
INDEXED_FORM = 0x10             # absolute,X (absolute,Y for LDX) is the absolute form + this
POINTER_FORM = 4                # (zp),Y is the absolute form + this
LOAD_ABSOLUTE = b"\xAD\xAE\xAC"                  # LDA, LDX, LDY
LOAD_IMMEDIATE = b"\xA9\xA2\xA0"
STORE_ABSOLUTE = b"\x8D\x8E\x8C"                 # STA, STX, STY
COMPARE_IMMEDIATE = b"\xC9\xE0\xC0"     # CMP, CPX, CPY
TRANSFERS = b"\x00\xAA\xA8\x8A\x00\x00\x98\x00\x00"     # from A, X, Y to A, X, Y: TAX TAY TXA TYA
C_DOLLAR = 0x24
C_ZERO = 0x30
C_T = 0x74


def begin(symbol):
    """Start the function whose object-file symbol is `symbol`: no operands, an empty frame,
    nothing known about the registers."""
    global depth, owner, local_count, temp_count, own, loop_depth
    depth = 0
    owner = NONE
    local_count = 0
    temp_count = 0
    own = symbol
    loop_depth = 0
    forget()


# ---- The operand stack -------------------------------------------------------------------

def push(kind, t, value):
    """Add an operand to the stack. The columns not given start empty."""
    global depth
    if depth == MAX_OPERANDS:
        err.fatal(err.E_OPERANDS_FULL)
    describe(depth, kind, t)
    op_value[depth] = value
    depth += 1


def describe(i, kind, t):
    """Make entry `i` an operand of this kind and type, with every other column empty."""
    op_kind[i] = kind
    op_type[i] = t
    op_size[i] = typetab.size(t)
    if kind == O_A:
        op_size[i] = 1
    elif kind == O_AX:
        op_size[i] = 2
    op_value[i] = 0
    op_symbol[i] = kernel.NO_OBJ
    op_slot[i] = fbuf.NO_SLOT
    op_flags[i] = 0
    op_var[i] = kernel.NO_SYM
    op_true[i] = NONE
    op_false[i] = NONE
    op_mode[i] = M_DIRECT
    op_stride[i] = 1
    op_kind[i + INDEX] = 0


def push_memory(t, symbol, slot, value, more, variable):
    """Add the memory operand that the fix-up `symbol`, `slot`, `value` reaches (or, with
    kernel.NO_OBJ for the symbol, the one at address `value`). `more` is F_ZP or 0, and
    `variable` the kernel symbol that counts its uses, or kernel.NO_SYM."""
    push(O_VAR, t, value)
    op_symbol[depth - 1] = symbol
    op_slot[depth - 1] = slot
    op_flags[depth - 1] = more
    op_var[depth - 1] = variable


def push_slot(t, slot):
    """Add an operand for a slot of the function being compiled."""
    more = 0
    if slot_class[slot] == CLASS_ZP:
        more = F_ZP
    push_memory(t, own, slot, 0, more, kernel.NO_SYM)


def push_register(t):
    """Add an operand for a value of type `t` that is now in A, or in A and X."""
    global owner
    if typetab.size(t) == 2:
        push(O_AX, t, 0)
    else:
        push(O_A, t, 0)
    owner = depth - 1


def pop():
    """Take the newest operand off the stack. Its temporaries, if it has any, are free again."""
    global depth, owner
    depth -= 1
    if owner == depth:
        owner = NONE
    free(depth)


def free(i):
    """The temporaries of operand `i`, its own and its index's, are free again."""
    if op_flags[i] & F_TEMP != 0:
        slot_busy[op_slot[i]] = False
    if op_kind[i + INDEX] == O_VAR and op_flags[i + INDEX] & F_TEMP != 0:
        slot_busy[op_slot[i + INDEX]] = False


def become(i, kind, t):
    """Operand `i` is from now on of this kind and type: its value has been moved."""
    global owner
    free(i)
    if owner == i:
        owner = NONE
    describe(i, kind, t)
    if kind == O_A or kind == O_AX:
        owner = i


def copy(source, target):
    """Entry `target` describes what entry `source` does, index and all."""
    copy_entry(source, target)
    copy_entry(source + INDEX, target + INDEX)


def copy_entry(source, target):
    op_kind[target] = op_kind[source]
    op_type[target] = op_type[source]
    op_size[target] = op_size[source]
    op_value[target] = op_value[source]
    op_symbol[target] = op_symbol[source]
    op_slot[target] = op_slot[source]
    op_flags[target] = op_flags[source]
    op_var[target] = op_var[source]
    op_true[target] = op_true[source]
    op_false[target] = op_false[source]
    op_mode[target] = op_mode[source]
    op_stride[target] = op_stride[source]


def swap():
    """Exchange the two newest operands."""
    global owner
    copy(depth - 1, MAX_OPERANDS)
    copy(depth - 2, depth - 1)
    copy(MAX_OPERANDS, depth - 2)
    if owner == depth - 1:
        owner = depth - 2
    elif owner == depth - 2:
        owner = depth - 1


def squeeze():
    """Remove the operand under the newest one, which holds nothing to give back."""
    global depth, owner
    copy(depth - 1, depth - 2)
    if owner == depth - 1:
        owner = depth - 2
    depth -= 1


def duplicate(i):
    """Add a second description of the memory operand `i`."""
    global depth
    if depth == MAX_OPERANDS:
        err.fatal(err.E_OPERANDS_FULL)
    copy(i, depth)
    op_flags[depth] = op_flags[depth] & ~F_TEMP
    op_flags[depth + INDEX] = op_flags[depth + INDEX] & ~F_TEMP
    depth += 1


def keep(i):
    """Add the operand described at entry `i`, which is at or above the top of the stack, or
    is an index (whose temporary, if it has one, the new operand takes over)."""
    global depth
    if depth == MAX_OPERANDS:
        err.fatal(err.E_OPERANDS_FULL)
    copy_entry(i, depth)
    op_kind[depth + INDEX] = 0
    if i >= INDEX:
        op_kind[i] = 0
    depth += 1


def take_index(i):
    """The newest operand, a constant or a byte in memory, becomes the index of operand `i`
    and leaves the stack."""
    global depth
    depth -= 1
    copy_entry(depth, i + INDEX)


def offset(i, k):
    """The offset of byte `k` of memory operand `i` from its fix-up or address; for one reached
    through a pointer, the offset added to the index in Y."""
    return (op_value[i] + k * op_stride[i]) & 0xFFFF


def in_registers(i):
    return op_kind[i] == O_A or op_kind[i] == O_AX


def is_const_byte(i, k):
    """True if byte `k` of operand `i` is known now: a constant, or above a widened byte."""
    return op_kind[i] == O_CONST or k >= op_size[i]


def const_byte(i, k):
    if op_kind[i] == O_CONST:
        return (op_value[i] >> (8 * k)) & 0xFF
    return 0


def same_place(i, j):
    """True if operands `i` and `j` are the same memory."""
    return same_entry(i, j) and op_mode[i] == op_mode[j] and op_stride[i] == op_stride[j] \
        and (op_mode[i] == M_DIRECT or same_entry(i + INDEX, j + INDEX))


def same_entry(i, j):
    """True if entries `i` and `j` are the same memory, or the same constant."""
    if op_kind[i] == O_CONST:
        return op_kind[j] == O_CONST and op_value[i] == op_value[j]
    return op_kind[i] == O_VAR and op_kind[j] == O_VAR and op_symbol[i] == op_symbol[j] \
        and op_slot[i] == op_slot[j] and op_value[i] == op_value[j]


def is_direct(i):
    """True unless operand `i` is memory reached through an index register."""
    return op_kind[i] != O_VAR or op_mode[i] == M_DIRECT


# ---- The frame ---------------------------------------------------------------------------

def new_slot(size, zp_class, kind, name):
    """Add a parameter or local to the frame. Returns its slot number."""
    global local_count
    if local_count == fbuf.FIRST_TEMP:
        err.fatal(err.E_SLOTS_FULL)
    set_slot(local_count, size, zp_class, kind, name)
    local_count += 1
    return local_count - 1


def set_slot(n, size, zp_class, kind, name):
    slot_size[n] = size
    slot_class[n] = zp_class
    slot_weight[n] = 0
    slot_kind[n] = kind
    slot_name[n] = name
    slot_busy[n] = True


def temp_name(number):
    """The name of temporary `number`: `$t` and the number, which no source name can be."""
    kernel.name_begin()
    kernel.name_add(C_DOLLAR)
    kernel.name_add(C_T)
    if number >= 10:
        kernel.name_add(C_ZERO + number // 10)
    kernel.name_add(C_ZERO + number % 10)
    return kernel.name_end()


def temp(size):
    """A temporary of `size` bytes: one that is free again, or a new one. Returns its slot."""
    global temp_count
    for n in range(fbuf.FIRST_TEMP, fbuf.FIRST_TEMP + temp_count):
        if not slot_busy[n] and slot_size[n] == size:
            slot_busy[n] = True
            return n
    if temp_count == MAX_TEMPS:
        err.fatal(err.E_SLOTS_FULL)
    temp_count += 1
    n = fbuf.FIRST_TEMP + temp_count - 1
    set_slot(n, size, CLASS_EITHER, SLOT_TEMPORARY, temp_name(temp_count))
    return n


def describe_temp(i, t):
    """Make entry `i` a new temporary for a value of type `t`."""
    describe(i, O_VAR, t)
    op_symbol[i] = own
    op_slot[i] = temp(op_size[i])
    op_flags[i] = F_TEMP


def use(i):
    """An instruction uses memory operand `i`: add to the weight of its slot or variable."""
    if op_symbol[i] == own and op_slot[i] != fbuf.NO_SLOT:
        use_slot(op_slot[i])
    elif op_var[i] != kernel.NO_SYM:
        use_variable(op_var[i])


def use_weight():
    """What one use adds here, by how many loops it is inside."""
    if loop_depth < 3:
        return WEIGHTS[loop_depth]
    return WEIGHTS[3]


def use_slot(n):
    """An instruction uses slot `n` of the function being compiled."""
    slot_weight[n] = heavier(slot_weight[n], use_weight())


def use_variable(s):
    """An instruction uses the variable that is kernel symbol `s`."""
    kernel.sym_weight[s] = heavier(kernel.sym_weight[s], use_weight())


def heavier(weight, amount):
    if weight + amount > 255:
        return 255
    return weight + amount


# ---- Owning a register -------------------------------------------------------------------

def release(i):
    """Operand `i` is being used up: the registers it is in are free to change."""
    global owner
    if owner == i:
        owner = NONE


def claim(r):
    """Register `r` is about to change: if an operand is in it, store that in a temporary."""
    if owner != NONE and (r == A or (r == X and op_kind[owner] == O_AX)):
        spill(owner)


def spill(i):
    """Store operand `i`, which is in the registers, in a temporary. It becomes a variable."""
    high = op_kind[i] == O_AX
    t = op_type[i]
    size = op_size[i]
    become(i, O_VAR, t)
    op_size[i] = size
    op_symbol[i] = own
    op_slot[i] = temp(size)
    op_flags[i] = F_TEMP
    store_direct(A, i, 0)
    if high:
        store_direct(X, i, 1)


def take(i):
    """If operand `i` is in an element or where a pointer points, load it into A, or A and X.
    The index of an element is in X, so its high byte is loaded last, by Y."""
    if is_direct(i):
        return
    release(i)
    kind = O_A
    if op_size[i] == 2:
        kind = O_AX
    if kind == O_AX and op_mode[i] == M_POINTER:
        load(X, i, 1)
    load(A, i, 0)
    if kind == O_AX and op_mode[i] == M_INDEXED:
        load(X, i, 1)
    become(i, kind, op_type[i])


def into_memory(i):
    """Make the byte operand `i`, which is not a constant, a variable that needs no index."""
    take(i)
    if in_registers(i):
        spill(i)


def apart(i, j):
    """Operand `i` is used with operand `j`: if `i` is in A and X and `j` an element, whose
    index needs X, store `i` in a temporary first."""
    if op_kind[i] == O_AX and op_kind[j] == O_VAR and op_mode[j] == M_INDEXED:
        spill(i)


def zero_page(i):
    """Operand `i` is a temporary or a slot of this function, which must be in zero page."""
    slot_class[op_slot[i]] = CLASS_ZP
    op_flags[i] = op_flags[i] | F_ZP


def dereferenced(i):
    """Operand `i`, a pointer, is to be used through (zp),Y. True if it can be as it is: a
    variable of this module or a slot of this function, which becomes "must be in zero page"
    unless it was declared `nozp`, or another module's variable declared `zp`."""
    if op_kind[i] != O_VAR or op_mode[i] != M_DIRECT or op_value[i] != 0 \
            or op_symbol[i] == kernel.NO_OBJ:
        return False
    if op_flags[i] & F_ZP != 0:
        return True
    s = op_var[i]
    if op_symbol[i] == own and op_slot[i] != fbuf.NO_SLOT:
        if slot_class[op_slot[i]] == CLASS_NOT_ZP:
            return False
        zero_page(i)
        return True
    if s == kernel.NO_SYM or kernel.sym_flags[s] & kernel.SF_NOZP != 0 \
            or (kernel.sym_scope[s] != kernel.SCOPE_MODULE and kernel.sym_scope[s] != kernel.SCOPE_LOCAL):
        return False
    kernel.sym_flags[s] = kernel.sym_flags[s] | kernel.SF_ZP
    op_flags[i] = op_flags[i] | F_ZP
    return True


def clobber():
    """A call is about to change every register."""
    claim(A)
    claim(X)


# ---- What the registers hold -------------------------------------------------------------

def forget_register(r):
    global flags
    reg_known[r] = False
    for n in range(r * COPY_COUNT, r * COPY_COUNT + COPY_COUNT):
        reg_copy[n] = False
    if flags == r:
        flags = NO_REG


def forget():
    """Nothing is known about the registers or the flags: after a call, and wherever a branch
    can arrive."""
    global flags
    for r in range(0, 3):
        forget_register(r)
    flags = NO_REG


def is_copy(n, i, k):
    """True if entry `n` of the copies says its register holds byte `k` of memory operand `i`,
    or for an element, a byte of the same array, and for what a pointer points at, anything."""
    if not reg_copy[n] or op_mode[i] == M_POINTER:
        return reg_copy[n]
    return reg_symbol[n] == op_symbol[i] and reg_slot[n] == op_slot[i] \
        and (reg_offset[n] == offset(i, k) or op_mode[i] == M_INDEXED)


def copies(r, i, k):
    """True if register `r` is known to hold a copy of byte `k` of memory operand `i`."""
    for n in range(r * COPY_COUNT, r * COPY_COUNT + COPY_COUNT):
        if is_copy(n, i, k):
            return True
    return False


def holds(r, i, k):
    """True if register `r` holds byte `k` of operand `i`."""
    if is_const_byte(i, k):
        return reg_known[r] and reg_const[r] == const_byte(i, k)
    if in_registers(i):
        return (k == 0 and r == A) or (k == 1 and r == X)
    return op_kind[i] == O_VAR and op_mode[i] == M_DIRECT and copies(r, i, k)


def holder(i, k):
    """A register that holds byte `k` of operand `i`, or NO_REG."""
    for r in range(0, 3):
        if holds(r, i, k):
            return r
    return NO_REG


def remember(r, i, k):
    """Register `r` now holds a copy of byte `k` of memory operand `i`. A fixed address is
    never remembered: it may be a device. Nor is an element or what a pointer points at."""
    if op_symbol[i] != kernel.NO_OBJ and op_mode[i] == M_DIRECT and not copies(r, i, k):
        n = r * COPY_COUNT
        for older in range(n + COPY_COUNT - 1, n, -1):
            copy_knowledge(older - 1, older)
        reg_copy[n] = True
        reg_symbol[n] = op_symbol[i]
        reg_slot[n] = op_slot[i]
        reg_offset[n] = offset(i, k)


def copy_knowledge(source, target):
    """Entry `target` of the copies says what entry `source` does."""
    reg_copy[target] = reg_copy[source]
    reg_symbol[target] = reg_symbol[source]
    reg_slot[target] = reg_slot[source]
    reg_offset[target] = reg_offset[source]


def changed(i, k, keeper):
    """Byte `k` of memory operand `i` has changed: no register holds a copy of it now, except
    `keeper` if that is the register it was stored from, and the flags do not show it. An
    element may be any of its array, and what a pointer points at anything but a constant."""
    global flags
    if op_mode[i] != M_DIRECT:
        keeper = NO_REG
        if flags == IN_MEMORY:
            flags = NO_REG
    for n in range(0, 3 * COPY_COUNT):
        if is_copy(n, i, k) and n // COPY_COUNT != keeper:
            reg_copy[n] = False
    if shows_memory(i, k):
        flags = NO_REG


def shows_memory(i, k):
    """True if the flags show byte `k` of memory operand `i` because it was just changed."""
    return flags == IN_MEMORY and op_kind[i] == O_VAR and op_mode[i] == M_DIRECT \
        and flags_symbol == op_symbol[i] and flags_slot == op_slot[i] and flags_offset == offset(i, k)


def shows(i, k):
    """True if the N and Z flags show the value of byte `k` of operand `i`."""
    if flags == IN_MEMORY:
        return shows_memory(i, k)
    return flags != NO_REG and holds(flags, i, k)


# ---- Instructions ------------------------------------------------------------------------

def implied(opcode):
    """An instruction without an operand that changes no register: CLC, SEC."""
    fbuf.op(opcode)


def memory(opcode, i, k):
    """The instruction `opcode` (absolute form) on byte `k` of operand `i`: memory, reached as
    its mode says, or an address, as an immediate. An element's index goes to X (to Y for
    LDX), and the index of what a pointer points at to Y."""
    if op_kind[i] == O_ADDR:
        fbuf.op_fix(opcode - IMMEDIATE_FORM, fbuf.FIX_LOW + k, op_symbol[i], op_slot[i], op_value[i])
        return
    if op_mode[i] == M_POINTER:
        point(i, k)
        use(i)
        fbuf.op_fix(opcode + POINTER_FORM, fbuf.FIX_ZERO_PAGE, op_symbol[i], op_slot[i], 0)
        return
    if op_mode[i] == M_INDEXED:
        r = X
        if opcode == OP_LDX:
            r = Y
        load_direct(r, i + INDEX, 0)
        opcode += INDEXED_FORM
    direct(opcode, i, k)


def point(i, k):
    """Make Y the index of byte `k` of what a pointer points at: its index plus its offset."""
    global flags
    n = offset(i, k)
    if op_kind[i + INDEX] == O_CONST:
        load_const(Y, (op_value[i + INDEX] + n) & 0xFF)
        return
    load_direct(Y, i + INDEX, 0)
    for m in range(0, n):
        fbuf.op(OP_INY)
        forget_register(Y)
        flags = Y


def direct(opcode, i, k):
    """The instruction `opcode` (absolute form, or absolute indexed) on byte `k` of memory
    operand `i`, with the operand's address."""
    use(i)
    place = offset(i, k)
    if op_symbol[i] == kernel.NO_OBJ:
        if place < 0x100:
            fbuf.op_byte(opcode - ZERO_PAGE_FORM, place)    # the linker shrinks only fix-ups
        else:
            fbuf.op_word(opcode, place)
    elif op_flags[i] & F_ZP != 0:
        fbuf.op_fix(opcode - ZERO_PAGE_FORM, fbuf.FIX_ZERO_PAGE, op_symbol[i], op_slot[i], place)
    else:
        fbuf.op_fix(opcode, fbuf.FIX_ADDRESS, op_symbol[i], op_slot[i], place)


def transfer(source, target):
    """Copy register `source` to register `target`. One of them is A."""
    global flags
    if source == target:
        return
    if TRANSFERS[source * 3 + target] == 0:
        err.fatal(err.E_INTERNAL)
    claim(target)
    fbuf.op(TRANSFERS[source * 3 + target])
    reg_known[target] = reg_known[source]
    reg_const[target] = reg_const[source]
    for n in range(0, COPY_COUNT):
        copy_knowledge(source * COPY_COUNT + n, target * COPY_COUNT + n)
    flags = A


def from_other(r, source):
    """True if `source` is a register that `r` can be loaded from."""
    return source != NO_REG and (source == A or r == A)


def force(r, value):
    """Load register `r` with a constant, whatever is known."""
    global flags
    claim(r)
    fbuf.op_byte(LOAD_IMMEDIATE[r], value)
    forget_register(r)
    reg_known[r] = True
    reg_const[r] = value
    flags = r


def load_const(r, value):
    """Make register `r` hold the one-byte constant `value`."""
    if reg_known[r] and reg_const[r] == value:
        return
    for source in range(0, 3):
        if reg_known[source] and reg_const[source] == value and from_other(r, source):
            transfer(source, r)
            return
    force(r, value)


def load(r, i, k):
    """Make register `r` hold byte `k` of operand `i`. What a pointer points at can only be
    loaded into A, and goes on from there."""
    global flags
    if is_direct(i) or is_const_byte(i, k):
        load_direct(r, i, k)
        return
    wanted = r
    if op_mode[i] == M_POINTER:
        r = A
    claim(r)
    memory(LOAD_ABSOLUTE[r], i, k)
    forget_register(r)
    flags = r
    transfer(r, wanted)


def load_direct(r, i, k):
    """load() of an operand that needs no index register."""
    global flags
    if is_const_byte(i, k):
        load_const(r, const_byte(i, k))
        return
    if holds(r, i, k):
        return
    source = holder(i, k)
    if from_other(r, source):
        transfer(source, r)
        return
    claim(r)
    if op_kind[i] == O_ADDR:
        fbuf.op_fix(LOAD_IMMEDIATE[r], fbuf.FIX_LOW + k, op_symbol[i], op_slot[i], op_value[i])
        forget_register(r)
    elif op_kind[i] == O_VAR:
        direct(LOAD_ABSOLUTE[r], i, k)
        forget_register(r)
        remember(r, i, k)
    else:
        err.fatal(err.E_INTERNAL)
    flags = r


def store(r, i, k):
    """Store register `r` in byte `k` of memory operand `i`. Only A is stored in an element
    or through a pointer."""
    if not is_direct(i) and r != A:
        transfer(r, A)
        r = A
    memory(STORE_ABSOLUTE[r], i, k)
    changed(i, k, r)
    remember(r, i, k)


def store_direct(r, i, k):
    """store() in a temporary, which needs no index."""
    direct(STORE_ABSOLUTE[r], i, k)
    changed(i, k, r)
    remember(r, i, k)


def put(i, k, target, target_k):
    """Store byte `k` of operand `i` in byte `target_k` of memory operand `target`, from
    whichever register holds it already, or else through A. A value in A and X is stored in
    a temporary first if the target is an element, whose index needs X."""
    if op_kind[i] == O_AX and op_mode[target] == M_INDEXED:
        spill(i)
    r = holder(i, k)
    if r == NO_REG or not is_direct(target):
        load(A, i, k)
        r = A
    store(r, target, target_k)


def put_const(value, target, target_k):
    """Store a constant byte in byte `target_k` of memory operand `target`."""
    r = A
    for other in range(0, 3):
        if reg_known[other] and reg_const[other] == value and is_direct(target):
            r = other
    load_const(r, value)
    store(r, target, target_k)


def immediate(opcode, value):
    """ORA, AND, EOR, ADC or SBC of A with a constant."""
    global flags
    claim(A)
    fbuf.op_byte(opcode - IMMEDIATE_FORM, value)
    forget_register(A)
    flags = A


def alu(opcode, i, k):
    """ORA, AND, EOR, ADC or SBC of A with byte `k` of operand `i`, which is a constant or
    memory."""
    global flags
    if is_const_byte(i, k):
        immediate(opcode, const_byte(i, k))
        return
    claim(A)
    memory(opcode, i, k)
    forget_register(A)
    flags = A


def compare_const(value):
    """CMP of A with a constant."""
    global flags
    fbuf.op_byte(OP_CMP - IMMEDIATE_FORM, value)
    flags = NO_REG


def compare(i, k):
    """CMP of A with byte `k` of operand `i`."""
    global flags
    if is_const_byte(i, k):
        compare_const(const_byte(i, k))
        return
    memory(OP_CMP, i, k)
    flags = NO_REG


def accumulator(opcode):
    """ASL, LSR, ROL or ROR of A."""
    global flags
    claim(A)
    fbuf.op(opcode - IMMEDIATE_FORM)
    forget_register(A)
    flags = A


def modify(opcode, i, k):
    """INC, DEC, ASL, LSR, ROL or ROR of byte `k` of memory operand `i`. The flags then show
    that byte, unless it is at a fixed address, which may be a device, or an element. What a
    pointer points at is changed in A, which has no INC: there that is an ADC, which changes
    the carry flag too."""
    global flags, flags_symbol, flags_slot, flags_offset
    if op_mode[i] == M_POINTER:
        load(A, i, k)
        if opcode == OP_INC:
            implied(OP_CLC)
            immediate(OP_ADC, 1)
        elif opcode == OP_DEC:
            implied(OP_SEC)
            immediate(OP_SBC, 1)
        else:
            accumulator(opcode)
        store(A, i, k)
        return
    memory(opcode, i, k)
    changed(i, k, NO_REG)
    flags = NO_REG
    if op_symbol[i] != kernel.NO_OBJ and op_mode[i] == M_DIRECT:
        flags = IN_MEMORY
        flags_symbol = op_symbol[i]
        flags_slot = op_slot[i]
        flags_offset = offset(i, k)


def step_x(opcode):
    """INX or DEX."""
    fbuf.op(opcode)
    forget_register(X)


def test(r):
    """Make the N and Z flags show the value of register `r`."""
    global flags
    if flags != r:
        fbuf.op_byte(COMPARE_IMMEDIATE[r], 0)
        flags = r


def test_byte(i, k):
    """Make the N and Z flags show byte `k` of operand `i`: nothing if they do already,
    otherwise through A."""
    if not shows(i, k):
        load(A, i, k)
        test(A)


def label(target):
    """Put a label that only earlier instructions go to here. What the registers hold is
    still known if none does, unless the code before it could not be reached: what that
    seemed to leave in the registers was never there."""
    unreached = not fbuf.runs_on()
    if fbuf.arrive(target) or unreached:
        forget()


def loop_label(target):
    """Put a label here that later instructions will go to."""
    fbuf.place(target)
    forget()


# ---- Types of operands -------------------------------------------------------------------

def accepts(actual, t):
    """True if a value of type `actual` can be given to something of type `t` as it is: the
    same type, a `byte` where a `word` is wanted, or `nil` where a pointer is."""
    return actual == t or (actual == typetab.BYTE_TYPE and t == typetab.WORD_TYPE) \
        or (actual == typetab.NIL_TYPE and typetab.is_pointer(t))


def fit(i, t):
    """Operand `i`, a number without a type, takes type `t`, which it must fit."""
    if not typetab.is_number(t):
        err.fatal(err.E_TYPE)
    if not typetab.number_fits(op_value[i], op_type[i] == typetab.NEGATIVE_TYPE, t):
        err.fatal(err.E_RANGE)
    op_type[i] = t
    op_size[i] = typetab.size(t)
    op_value[i] = typetab.narrow(op_value[i], t)


def assignable(i, t):
    """Check that operand `i` can be given to something of type `t`, and give it that type.
    An array cannot: it is not a value."""
    if typetab.is_array(t) or typetab.is_array(op_type[i]):
        err.fatal(err.E_ARRAY_VALUE)
    if typetab.is_untyped(op_type[i]):
        fit(i, t)
    elif not accepts(op_type[i], t):
        err.fatal(err.E_TYPE)
    op_type[i] = t


def unify(left, right):
    """The type in which an operator works on operands `left` and `right`, which both take
    it. typetab.NUMBER_TYPE if neither has a type: they are then constants."""
    if typetab.is_array(op_type[left]) or typetab.is_array(op_type[right]):
        err.fatal(err.E_ARRAY_VALUE)
    if typetab.is_untyped(op_type[left]):
        if typetab.is_untyped(op_type[right]):
            return typetab.NUMBER_TYPE
        fit(left, op_type[right])
    elif typetab.is_untyped(op_type[right]):
        fit(right, op_type[left])
    elif accepts(op_type[left], op_type[right]):
        op_type[left] = op_type[right]
    elif accepts(op_type[right], op_type[left]):
        op_type[right] = op_type[left]
    else:
        err.fatal(err.E_TYPE)
    return op_type[left]
