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

F_TEMP = 1              # the memory is a temporary, free again when the operand is popped
F_ZP = 2                # the memory is known to be in zero page

op_kind = [0] * (MAX_OPERANDS + 1)      # one more than the stack: swap() needs a spare
op_type = [0] * (MAX_OPERANDS + 1)
op_size = [0] * (MAX_OPERANDS + 1)      # bytes it really has: a byte widened to a word has 1,
#                                         and the bytes above read as 0
op_value = [0] * (MAX_OPERANDS + 1)
op_symbol = [0] * (MAX_OPERANDS + 1)
op_slot = [0] * (MAX_OPERANDS + 1)
op_flags = [0] * (MAX_OPERANDS + 1)
op_var = [0] * (MAX_OPERANDS + 1)       # the kernel symbol whose weight a use adds to, or NO_SYM
op_true = [0] * (MAX_OPERANDS + 1)
op_false = [0] * (MAX_OPERANDS + 1)
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
    """Take the newest operand off the stack. Its temporary, if it has one, is free again."""
    global depth, owner
    depth -= 1
    if owner == depth:
        owner = NONE
    if op_flags[depth] & F_TEMP != 0:
        slot_busy[op_slot[depth]] = False


def become(i, kind, t):
    """Operand `i` is from now on of this kind and type: its value has been moved."""
    global owner
    if op_flags[i] & F_TEMP != 0:
        slot_busy[op_slot[i]] = False
    if owner == i:
        owner = NONE
    describe(i, kind, t)
    if kind == O_A or kind == O_AX:
        owner = i


def copy(source, target):
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
    op_flags[depth] = op_flags[depth] & F_ZP
    depth += 1


def keep(i):
    """Add the operand described at entry `i`, which is at or above the top of the stack."""
    global depth
    copy(i, depth)
    depth += 1


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
    return op_kind[i] == O_VAR and op_kind[j] == O_VAR and op_symbol[i] == op_symbol[j] \
        and op_slot[i] == op_slot[j] and op_value[i] == op_value[j]


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
    store(A, i, 0)
    if high:
        store(X, i, 1)


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
    """True if entry `n` of the copies says its register holds byte `k` of memory operand `i`."""
    return reg_copy[n] and reg_symbol[n] == op_symbol[i] and reg_slot[n] == op_slot[i] \
        and reg_offset[n] == (op_value[i] + k) & 0xFFFF


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
    return copies(r, i, k)


def holder(i, k):
    """A register that holds byte `k` of operand `i`, or NO_REG."""
    for r in range(0, 3):
        if holds(r, i, k):
            return r
    return NO_REG


def remember(r, i, k):
    """Register `r` now holds a copy of byte `k` of memory operand `i`. A fixed address is
    never remembered: it may be a device."""
    if op_symbol[i] != kernel.NO_OBJ and not copies(r, i, k):
        n = r * COPY_COUNT
        for older in range(n + COPY_COUNT - 1, n, -1):
            copy_knowledge(older - 1, older)
        reg_copy[n] = True
        reg_symbol[n] = op_symbol[i]
        reg_slot[n] = op_slot[i]
        reg_offset[n] = (op_value[i] + k) & 0xFFFF


def copy_knowledge(source, target):
    """Entry `target` of the copies says what entry `source` does."""
    reg_copy[target] = reg_copy[source]
    reg_symbol[target] = reg_symbol[source]
    reg_slot[target] = reg_slot[source]
    reg_offset[target] = reg_offset[source]


def changed(i, k, keeper):
    """Byte `k` of memory operand `i` has changed: no register holds a copy of it now, except
    `keeper` if that is the register it was stored from, and the flags do not show it."""
    global flags
    for n in range(0, 3 * COPY_COUNT):
        if is_copy(n, i, k) and n // COPY_COUNT != keeper:
            reg_copy[n] = False
    if shows_memory(i, k):
        flags = NO_REG


def shows_memory(i, k):
    """True if the flags show byte `k` of memory operand `i` because it was just changed."""
    return flags == IN_MEMORY and op_kind[i] == O_VAR and flags_symbol == op_symbol[i] \
        and flags_slot == op_slot[i] and flags_offset == (op_value[i] + k) & 0xFFFF


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
    """The instruction `opcode` (absolute form) on byte `k` of memory operand `i`."""
    use(i)
    offset = (op_value[i] + k) & 0xFFFF
    if op_symbol[i] == kernel.NO_OBJ:
        if offset < 0x100:
            fbuf.op_byte(opcode - ZERO_PAGE_FORM, offset)    # the linker shrinks only fix-ups
        else:
            fbuf.op_word(opcode, offset)
    elif op_flags[i] & F_ZP != 0:
        fbuf.op_fix(opcode - ZERO_PAGE_FORM, fbuf.FIX_ZERO_PAGE, op_symbol[i], op_slot[i], offset)
    else:
        fbuf.op_fix(opcode, fbuf.FIX_ADDRESS, op_symbol[i], op_slot[i], offset)


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
    """Make register `r` hold byte `k` of operand `i`."""
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
    if op_kind[i] != O_VAR:
        err.fatal(err.E_INTERNAL)
    claim(r)
    memory(LOAD_ABSOLUTE[r], i, k)
    forget_register(r)
    remember(r, i, k)
    flags = r


def store(r, i, k):
    """Store register `r` in byte `k` of memory operand `i`."""
    memory(STORE_ABSOLUTE[r], i, k)
    changed(i, k, r)
    remember(r, i, k)


def put(i, k, target, target_k):
    """Store byte `k` of operand `i` in byte `target_k` of memory operand `target`, from
    whichever register holds it already, or else through A."""
    r = holder(i, k)
    if r == NO_REG:
        load(A, i, k)
        r = A
    store(r, target, target_k)


def put_const(value, target, target_k):
    """Store a constant byte in byte `target_k` of memory operand `target`."""
    r = A
    for other in range(0, 3):
        if reg_known[other] and reg_const[other] == value:
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
    that byte, unless it is at a fixed address, which may be a device."""
    global flags, flags_symbol, flags_slot, flags_offset
    memory(opcode, i, k)
    changed(i, k, NO_REG)
    flags = NO_REG
    if op_symbol[i] != kernel.NO_OBJ:
        flags = IN_MEMORY
        flags_symbol = op_symbol[i]
        flags_slot = op_slot[i]
        flags_offset = (op_value[i] + k) & 0xFFFF


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
    same type, or a `byte` where a `word` is wanted."""
    return actual == t or (actual == typetab.BYTE_TYPE and t == typetab.WORD_TYPE)


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
    """Check that operand `i` can be given to something of type `t`, and give it that type."""
    if typetab.is_untyped(op_type[i]):
        fit(i, t)
    elif not accepts(op_type[i], t):
        err.fatal(err.E_TYPE)
    op_type[i] = t


def unify(left, right):
    """The type in which an operator works on operands `left` and `right`, which both take
    it. typetab.NUMBER_TYPE if neither has a type: they are then constants."""
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
