"""FBUF: the function buffer.

Owns the instructions of the function being compiled, from begin() to finish(). They are held
with their operands still symbolic, because two things are not known until the function ends:
how far each forward branch has to go, and so which branches need the long form.

finish() settles the branches and leaves, for OUT to write, the function's code in the
written layout of docs/object-format.md and its fix-ups in order of offset:
- an operand that is an address to be filled in is written as zero bytes with a fix-up; an
  instruction that may later shrink to its zero page form is written in its absolute form;
- a branch is written with its final displacement, or, if its target is too far, as the
  opposite branch round a JMP;
- a label is the function's own symbol plus the label's offset, so a JMP inside the function
  is a fix-up like any other.

The buffer is a run of entries, each a kind byte and the fields that kind has. It is this
compact because it is the largest thing the compiler keeps in memory on the target.
"""
import err

BUFFER_SIZE = 8192          # bytes of entries
MAX_CODE = 4096            # bytes of code in one function
MAX_LABELS = 256            # a label's number is stored in one byte
MAX_FIXUPS = 1024

# Fix-up kinds (docs/object-format.md)
FIX_ADDRESS = 1             # two bytes
FIX_LOW = 2                 # one byte: the low byte of the address
FIX_HIGH = 3                # one byte: the high byte
FIX_ZERO_PAGE = 4           # one byte: an address known to be in zero page
NO_SLOT = 0xFF              # in a fix-up's slot field: the symbol itself, not one of its slots

# Entry kinds, and the fields after the kind byte
I_PLAIN = 0                 # opcode
I_BYTE = 1                  # opcode, operand
I_WORD = 2                  # opcode, operand (2)
I_BRANCH = 3                # opcode, label: a branch taken to reach, until shown otherwise
I_FAR = 4                   # opcode, label: a branch that does not reach
I_JUMP = 5                  # label: a JMP to a label
I_LABEL = 6                 # label: the label is here
I_FIX = 8                   # I_FIX + fix-up kind: opcode, symbol (2), slot, addend (2)

OP_RTI = 0x40
OP_JMP = 0x4C
OP_RTS = 0x60
OP_JMP_INDIRECT = 0x6C
OP_BRA = 0x80               # 65C02: the one branch with no opposite
OPPOSITE = 0x20             # the bit that differs between a branch and its opposite
UNPLACED = 0xFFFF

buffer = bytearray(BUFFER_SIZE)
used = 0
newest = 0                              # the entry added last, if used is not 0
label_offset = [0] * MAX_LABELS         # where each label is in the written layout
label_count = 0

code = bytearray(MAX_CODE)
code_length = 0
fix_offset = [0] * MAX_FIXUPS
fix_kind = [0] * MAX_FIXUPS
fix_symbol = [0] * MAX_FIXUPS
fix_slot = [0] * MAX_FIXUPS
fix_addend = [0] * MAX_FIXUPS
fix_count = 0


def begin():
    """Start a function with no instructions and no labels."""
    global used, label_count, code_length, fix_count
    used = 0
    label_count = 0
    code_length = 0
    fix_count = 0


# ---- Adding instructions -----------------------------------------------------------------

def add(value):
    """Add one byte to the entry being made."""
    global used
    if used == BUFFER_SIZE:
        err.fatal(err.E_FUNC_BIG)
    buffer[used] = value
    used += 1


def add_word(value):
    add(value & 0xFF)
    add((value >> 8) & 0xFF)


def add_entry(kind):
    """Begin an entry. Its fields follow with add()."""
    global newest
    newest = used
    add(kind)


def op(opcode):
    """An instruction with no operand."""
    add_entry(I_PLAIN)
    add(opcode)


def op_byte(opcode, operand):
    """An instruction with a one-byte operand that is already known."""
    add_entry(I_BYTE)
    add(opcode)
    add(operand)


def op_word(opcode, operand):
    """An instruction with a two-byte operand that is already known."""
    add_entry(I_WORD)
    add(opcode)
    add_word(operand)


def op_fix(opcode, kind, symbol, slot, addend):
    """An instruction whose operand the linker fills in: the address of `symbol`, or of its
    slot `slot` unless that is NO_SLOT, plus `addend`. `kind` says which part of the address.
    With FIX_ADDRESS, `opcode` is the absolute form, whatever the address turns out to be."""
    add_entry(I_FIX + kind)
    add(opcode)
    add_word(symbol)
    add(slot)
    add_word(addend)


def new_label():
    """A label of this function, to be put somewhere with place()."""
    global label_count
    if label_count == MAX_LABELS:
        err.fatal(err.E_LABELS_FULL)
    label_offset[label_count] = UNPLACED
    label_count += 1
    return label_count - 1


def place(label):
    """Put `label` here, before the next instruction."""
    add_entry(I_LABEL)
    add(label)


def branch(opcode, label):
    """A conditional branch (or BRA) to `label`, which may be placed before or after it."""
    add_entry(I_BRANCH)
    add(opcode)
    add(label)


def jump(label):
    """A JMP to `label`."""
    add_entry(I_JUMP)
    add(label)


def runs_on():
    """True if the processor can run on from the newest instruction into whatever is added
    next. False after a return or a jump, until a label gives another way in."""
    if used == 0 or buffer[newest] == I_LABEL:
        return True
    if buffer[newest] == I_JUMP:
        return False
    opcode = buffer[newest + 1]
    return opcode != OP_RTS and opcode != OP_JMP and opcode != OP_BRA and opcode != OP_RTI \
        and opcode != OP_JMP_INDIRECT


# ---- Settling the layout -----------------------------------------------------------------

def entry_size(kind):
    """Bytes of buffer an entry of this kind takes."""
    if kind >= I_FIX:
        return 7
    if kind == I_WORD:
        return 4
    if kind == I_BYTE or kind == I_BRANCH or kind == I_FAR:
        return 3
    return 2


def code_size(entry):
    """Bytes of code the entry that starts at buffer[entry] becomes."""
    kind = buffer[entry]
    if kind == I_LABEL:
        return 0
    if kind == I_PLAIN:
        return 1
    if kind == I_BYTE or kind == I_BRANCH:
        return 2
    if kind == I_FAR and buffer[entry + 1] != OP_BRA:
        return 5
    if kind > I_FIX and kind != I_FIX + FIX_ADDRESS:
        return 2
    return 3


def layout():
    """Find where every label is, with the branches as long as they now are. Returns the
    length of the code."""
    entry = 0
    offset = 0
    while entry < used:
        if buffer[entry] == I_LABEL:
            label_offset[buffer[entry + 1]] = offset
        offset += code_size(entry)
        entry += entry_size(buffer[entry])
    return offset


def target(label):
    """The offset of a label that a branch or jump goes to."""
    if label_offset[label] == UNPLACED:
        err.fatal(err.E_INTERNAL)
    return label_offset[label]


def reaches(after, goal):
    """True if a branch whose next instruction is at offset `after` can go to offset `goal`."""
    if goal >= after:
        return goal - after <= 127
    return after - goal <= 128


def widen():
    """Make long each short branch that does not reach in the layout just found. Returns True
    if there was one: the layout has then changed and other branches may no longer reach."""
    changed = False
    entry = 0
    offset = 0
    while entry < used:
        size = code_size(entry)
        if buffer[entry] == I_BRANCH and not reaches(offset + 2, target(buffer[entry + 2])):
            buffer[entry] = I_FAR
            changed = True
        offset += size
        entry += entry_size(buffer[entry])
    return changed


# ---- Writing the code --------------------------------------------------------------------

def emit(value):
    global code_length
    code[code_length] = value
    code_length += 1


def fix(kind, symbol, slot, addend):
    """Note a fix-up for the operand about to be emitted."""
    global fix_count
    if fix_count == MAX_FIXUPS:
        err.fatal(err.E_FIXUPS_FULL)
    fix_offset[fix_count] = code_length
    fix_kind[fix_count] = kind
    fix_symbol[fix_count] = symbol
    fix_slot[fix_count] = slot
    fix_addend[fix_count] = addend
    fix_count += 1


def emit_jump(own, goal):
    """JMP to offset `goal` of this function, whose symbol is `own`."""
    emit(OP_JMP)
    fix(FIX_ADDRESS, own, NO_SLOT, goal)
    emit(0)
    emit(0)


def emit_entry(entry, own):
    """The code of the entry that starts at buffer[entry]."""
    kind = buffer[entry]
    if kind == I_LABEL:
        return
    if kind == I_JUMP:
        emit_jump(own, target(buffer[entry + 1]))
        return
    opcode = buffer[entry + 1]
    if kind == I_FAR:
        if opcode != OP_BRA:
            emit(opcode ^ OPPOSITE)
            emit(3)
        emit_jump(own, target(buffer[entry + 2]))
        return
    emit(opcode)
    if kind == I_BYTE:
        emit(buffer[entry + 2])
    elif kind == I_WORD:
        emit(buffer[entry + 2])
        emit(buffer[entry + 3])
    elif kind == I_BRANCH:
        emit((target(buffer[entry + 2]) - (code_length + 1)) & 0xFF)
    elif kind > I_FIX:
        fix(kind - I_FIX, buffer[entry + 2] | (buffer[entry + 3] << 8), buffer[entry + 4],
            buffer[entry + 5] | (buffer[entry + 6] << 8))
        emit(0)
        if kind == I_FIX + FIX_ADDRESS:
            emit(0)


def finish(own):
    """End the function, whose object-file symbol is `own`: settle its branches and build
    `code` and the fix-ups."""
    global code_length, fix_count
    while True:
        size = layout()
        if not widen():
            break
    if size > MAX_CODE:
        err.fatal(err.E_FUNC_BIG)
    code_length = 0
    fix_count = 0
    entry = 0
    while entry < used:
        emit_entry(entry, own)
        entry += entry_size(buffer[entry])
