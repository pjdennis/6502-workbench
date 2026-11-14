"""FBUF: the function buffer.

Owns the instructions of the function being compiled, from begin() to finish(). They are held
with their operands still symbolic, because two things are not known until the function ends:
how far each forward branch has to go, and so which branches need the long form.

finish() settles the branches and counts the code and the fix-ups. The code is not kept: OUT
walks the buffer twice (walk_begin(), walk_next()), once for the fix-ups and once for the code,
and writes each instruction as it is made. That gives the function's code in the written layout
of docs/object-format.md and its fix-ups in order of offset:
- an operand that is an address to be filled in is written as zero bytes with a fix-up; an
  instruction that may later shrink to its zero page form is written in its absolute form;
- a branch is written with its final displacement, or, if its target is too far, as the
  opposite branch round a JMP;
- a label is the function's own symbol plus the label's offset, so a JMP inside the function
  is a fix-up like any other;
- the function's temporaries, which are numbered from FIRST_TEMP while it is compiled, get the
  slot numbers that follow its parameters and locals;
- a two-byte address whose instruction has a zero page form is a fix-up of kind 5, which the
  linker shrinks if the address lands in zero page; any other two-byte address is kind 1;
- each use, by such an instruction, of a slot of another function or a parameter of a class
  adds to a weight in a small table (weight_*) that OUT writes as a WGT record: its own module
  counts the uses of a slot only in the function it belongs to. A use adds 1, 4, 16 or 64 by
  how many loops it is inside, as REG counts (docs/codegen.md, "Weights"); a loop here is the
  code from a label back to the last branch or jump that goes back to it. The weights are
  counted by finish(), so they are known when the records are written.

Small improvements are made as the instructions arrive, because each needs only the newest
entries: a branch round nothing but a JMP becomes one branch and a branch round nothing is
dropped (tidy()), a JSR that a return follows becomes a JMP (tail_call()), and an
instruction that cannot be reached is left out (add_entry()). Two labels can be made one
place (join()).

The buffer is a run of entries, each a kind byte and the fields that kind has. It is this
compact because it is the largest thing the compiler keeps in memory on the target.
"""
import err

BUFFER_SIZE = 4096          # bytes of entries
MAX_CODE = 4096            # bytes of code in one function
MAX_LABELS = 192            # a label's number is stored in one byte
MAX_FIXUPS = 512            # fix-ups of one function
PIECE_SIZE = 5              # bytes of code one entry can become: a branch round a JMP
MAX_WEIGHTS = 64            # slots of other functions one function uses; more are not counted
LOOP_WEIGHTS = b"\x01\x04\x10\x40"     # what one use adds, by how many loops it is inside

# Fix-up kinds (docs/object-format.md)
FIX_ADDRESS = 1             # two bytes
FIX_LOW = 2                 # one byte: the low byte of the address
FIX_HIGH = 3                # one byte: the high byte
FIX_ZERO_PAGE = 4           # one byte: an address known to be in zero page
FIX_SHRINKS = 5             # two bytes, of an instruction that has a zero page form
NO_SLOT = 0xFF              # in a fix-up's slot field: the symbol itself, not one of its slots
FIRST_TEMP = 0x80           # slot numbers from here to NO_SLOT - 1 are the function's temporaries

# Entry kinds, and the fields after the kind byte
I_PLAIN = 0                 # opcode
I_BYTE = 1                  # opcode, operand
I_WORD = 2                  # opcode, operand (2)
I_BRANCH = 3                # opcode, label: a branch taken to reach, until shown otherwise
I_FAR = 4                   # opcode, label: a branch that does not reach
I_JUMP = 5                  # label: a JMP to a label
I_LABEL = 6                 # label: the label is here
I_KEPT_JUMP = 7             # label: a JMP an `asm` block wrote, kept as it is
I_CALL = 8                  # label: a JSR to a label
I_FIX = 9                   # I_FIX + fix-up kind: opcode, symbol (2), slot, addend (2)

OP_JSR = 0x20
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
older = 0                               # the entry before it, if it is below `newest`
unreached = False                       # True while the entry being made is being left out
kept = UNPLACED                         # an entry an `asm` block wrote last: never a tail call
written = False                         # True while an `asm` block is written: kept as it is
label_offset = [0] * MAX_LABELS         # where each label is in the written layout
label_alias = bytearray(MAX_LABELS)          # the label this one was joined to, or itself
label_uses = [0] * MAX_LABELS           # how many branches and jumps go to it
label_note = bytearray(MAX_LABELS)      # kept for REG: what it knows of the ways to it
label_count = 0
temp_base = 0                           # the slot number the first temporary gets

own = 0                                 # the object-file symbol of the function being finished
code_length = 0                         # bytes of code it has, and fix-ups
fix_count = 0
counting = False                        # True while finish() counts: weights are counted then
walk_entry = 0                          # the entry walk_next() makes the piece of next
offset_now = 0                          # the offset in the code of the next byte of the piece
piece = bytearray(PIECE_SIZE)           # the code of one instruction, and its one fix-up
piece_length = 0
piece_fixed = False
fix_offset = 0
fix_kind = 0
fix_symbol = 0
fix_slot = 0
fix_addend = 0
weight_symbol = [0] * MAX_WEIGHTS       # the uses of other functions' slots, by slot
weight_slot = bytearray(MAX_WEIGHTS)
weight_value = bytearray(MAX_WEIGHTS)
weight_count = 0


def begin():
    """Start a function with no instructions and no labels."""
    global used, newest, older, unreached, kept, written, label_count, code_length, fix_count
    unreached = False
    kept = UNPLACED
    written = False
    used = 0
    newest = 0
    older = 0
    label_count = 0
    code_length = 0
    fix_count = 0


# ---- Adding instructions -----------------------------------------------------------------

def add(value):
    """Add one byte to the entry being made."""
    global used
    if unreached:
        return
    if used == BUFFER_SIZE:
        err.fatal(err.E_FUNC_BIG)
    buffer[used] = value
    used += 1


def add_word(value):
    add(value & 0xFF)
    add((value >> 8) & 0xFF)


def add_entry(kind):
    """Begin an entry. Its fields follow with add(). An instruction that the processor
    cannot reach, because it follows a jump or a return with no label between, is left out."""
    global newest, older, unreached
    unreached = kind != I_LABEL and not written and not runs_on()
    if unreached:
        return
    older = newest
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
    label_alias[label_count] = label_count
    label_uses[label_count] = 0
    label_note[label_count] = 0
    label_count += 1
    return label_count - 1


def same(label):
    """The label that stands for `label` after every join()."""
    while label_alias[label] != label:
        label = label_alias[label]
    return label


def join(label, other):
    """Make `other`, which has not been placed, the same place as `label`."""
    label = same(label)
    other = same(other)
    if other != label:
        label_alias[other] = label
        label_uses[label] += label_uses[other]


def is_used(label):
    """True if a branch or jump added so far goes to `label`."""
    return label_uses[same(label)] != 0


def skips_jump(label):
    """True if the two newest entries are a branch to `label` and a JMP."""
    if older >= newest or newest >= used:
        return False
    return buffer[newest] == I_JUMP and buffer[older] == I_BRANCH and buffer[older + 1] != OP_BRA \
        and same(buffer[older + 2]) == same(label)


def skips_nothing(label):
    """True if the newest entry is a branch or a JMP to `label`, and the entry before it is
    known."""
    if older >= newest or newest >= used:
        return False
    if buffer[newest] == I_BRANCH:
        return same(buffer[newest + 2]) == same(label)
    return buffer[newest] == I_JUMP and same(buffer[newest + 1]) == same(label)


def tidy(label):
    """`label` is about to be put here. A branch to here round nothing but a JMP becomes the
    opposite branch to where the JMP went, and a branch to here round nothing at all is
    taken out; so are both if the JMP comes here too."""
    global used, newest
    if written:
        return
    if skips_jump(label) and same(buffer[newest + 1]) == same(label):
        label_uses[same(label)] -= 2
        used = older
        newest = used                   # the entry before them is not known: see runs_on()
    elif skips_jump(label):
        buffer[older + 1] = buffer[older + 1] ^ OPPOSITE
        buffer[older + 2] = buffer[newest + 1]
        label_uses[same(label)] -= 1
        used = newest
        newest = older
    elif skips_nothing(label):
        label_uses[same(label)] -= 1
        used = newest
        newest = older


def place(label):
    """Put `label` here, before the next instruction."""
    tidy(label)
    add_entry(I_LABEL)
    add(label)


def arrive(label):
    """Put `label` here if any instruction goes to it; none may be added that does. Returns
    whether one does. A label that is left out cannot stand between two instructions that
    place() could make one."""
    tidy(label)
    if not is_used(label):
        return False
    add_entry(I_LABEL)
    add(label)
    return True


def branch(opcode, label):
    """A conditional branch (or BRA) to `label`, which may be placed before or after it."""
    label_uses[same(label)] += 1
    add_entry(I_BRANCH)
    add(opcode)
    add(label)


def jump(label):
    """A JMP to `label`."""
    label_uses[same(label)] += 1
    if written:
        add_entry(I_KEPT_JUMP)
    else:
        add_entry(I_JUMP)
    add(label)


def call_label(label):
    """A JSR to `label`: a call through a pointer goes to a JMP (pointer) of this function."""
    label_uses[same(label)] += 1
    add_entry(I_CALL)
    add(label)


def as_written(on):
    """From now on, if `on`, the instructions are those of an `asm` block, which are kept as
    they are written: none is left out as unreached, and no branch is fused or taken out."""
    global written
    written = on


def keep_as_written():
    """The newest instruction is the last one an `asm` block wrote: tail_call() leaves it as
    it is, because the routine it calls may read its return address."""
    global kept
    kept = UNPLACED
    if used != 0:
        kept = newest


def tail_call():
    """If the newest instruction is a JSR, make it a JMP: the routine called then returns for
    this function. Returns whether it was one."""
    if used == 0 or newest == kept:
        return False
    kind = buffer[newest]
    if kind == I_CALL:
        buffer[newest] = I_JUMP
        return True
    if (kind != I_WORD and kind != I_FIX + FIX_ADDRESS) or buffer[newest + 1] != OP_JSR:
        return False
    buffer[newest + 1] = OP_JMP
    return True


def runs_on():
    """True if the processor can run on from the newest instruction into whatever is added
    next. False after a return or a jump, until a label gives another way in. If the newest
    entry is not known, a branch has just been taken out, which could be reached."""
    if used == 0 or newest >= used or buffer[newest] == I_LABEL or buffer[newest] == I_CALL:
        return True
    if buffer[newest] == I_JUMP or buffer[newest] == I_KEPT_JUMP:
        return False
    opcode = buffer[newest + 1]
    return opcode != OP_RTS and opcode != OP_JMP and opcode != OP_BRA and opcode != OP_RTI \
        and opcode != OP_JMP_INDIRECT


# ---- Settling the layout -----------------------------------------------------------------

def thread():
    """A JMP to an RTS becomes an RTS, which is shorter. A JMP an `asm` block wrote is left as
    it is. label_offset holds where in the buffer each label is until layout() is first run."""
    entry = 0
    while entry < used:
        if buffer[entry] == I_LABEL:
            label_offset[buffer[entry + 1]] = entry
        entry += entry_size(buffer[entry])
    entry = 0
    while entry < used:
        if buffer[entry] == I_JUMP:
            goal = label_offset[same(buffer[entry + 1])]
            while goal < used and buffer[goal] == I_LABEL:
                goal += 2
            if goal < used and buffer[goal] == I_PLAIN and buffer[goal + 1] == OP_RTS:
                buffer[entry] = I_PLAIN
                buffer[entry + 1] = OP_RTS
        entry += entry_size(buffer[entry])


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
    label = same(label)
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

def has_zero_page_form(opcode):
    """True if an instruction with a two-byte address has a form with a one-byte address:
    the absolute and absolute,X instructions but JMP, JSR and (on the 65C02) JMP (abs,X) and
    the NOPs, and LDX abs,Y (docs/object-format.md, "The size of an instruction")."""
    low = opcode & 0x0F
    if low == 0x0D or low == 0x0E:
        return True
    if low != 0x0C:
        return False
    high = opcode >> 4
    return high != 0x04 and high != 0x05 and high != 0x06 and high != 0x07 and high != 0x0D \
        and high != 0x0F


def find_loops():
    """The end of every loop: for each label that a branch or jump goes back to, the offset
    after the last such branch, in label_uses, which are not needed once the layout is settled;
    0 for a label that no branch goes back to."""
    for label in range(0, label_count):
        label_uses[label] = 0
    entry = 0
    offset = 0
    while entry < used:
        kind = buffer[entry]
        size = code_size(entry)
        label = UNPLACED
        if kind == I_BRANCH or kind == I_FAR:
            label = same(buffer[entry + 2])
        elif kind == I_JUMP or kind == I_KEPT_JUMP:
            label = same(buffer[entry + 1])
        if label != UNPLACED and label_offset[label] <= offset:
            label_uses[label] = offset + size
        offset += size
        entry += entry_size(kind)


def use_weight(offset):
    """What a use by the instruction at `offset` adds, by how many loops it is inside."""
    depth = 0
    for label in range(0, label_count):
        if label_offset[label] <= offset and offset < label_uses[label]:
            depth += 1
    if depth > 3:
        depth = 3
    return LOOP_WEIGHTS[depth]


def count_use(symbol, slot, offset):
    """The instruction at `offset` uses slot `slot` of another function or class `symbol`."""
    global weight_count
    amount = use_weight(offset)
    for i in range(0, weight_count):
        if weight_symbol[i] == symbol and weight_slot[i] == slot:
            if weight_value[i] + amount > 255:
                weight_value[i] = 255
            else:
                weight_value[i] += amount
            return
    if weight_count == MAX_WEIGHTS:
        return
    weight_symbol[weight_count] = symbol
    weight_slot[weight_count] = slot
    weight_value[weight_count] = amount
    weight_count += 1


def emit(value):
    """A byte of the piece being made."""
    global piece_length, offset_now
    piece[piece_length] = value
    piece_length += 1
    offset_now += 1


def fix(kind, symbol, slot, addend):
    """Note a fix-up for the operand about to be emitted: the piece's one fix-up."""
    global piece_fixed, fix_offset, fix_kind, fix_symbol, fix_slot, fix_addend
    piece_fixed = True
    fix_offset = offset_now
    fix_kind = kind
    fix_symbol = symbol
    fix_slot = slot
    fix_addend = addend


def emit_jump(goal):
    """JMP to offset `goal` of this function."""
    emit_to(OP_JMP, goal)


def emit_to(opcode, goal):
    """JMP or JSR to offset `goal` of this function, whose symbol is `own`."""
    emit(opcode)
    fix(FIX_ADDRESS, own, NO_SLOT, goal)
    emit(0)
    emit(0)


def emit_entry(entry):
    """The code of the entry that starts at buffer[entry], as the piece."""
    kind = buffer[entry]
    if kind == I_LABEL:
        return
    if kind == I_JUMP or kind == I_KEPT_JUMP:
        emit_jump(target(buffer[entry + 1]))
        return
    if kind == I_CALL:
        emit_to(OP_JSR, target(buffer[entry + 1]))
        return
    opcode = buffer[entry + 1]
    if kind == I_FAR:
        if opcode != OP_BRA:
            emit(opcode ^ OPPOSITE)
            emit(3)
        emit_jump(target(buffer[entry + 2]))
        return
    emit(opcode)
    if kind == I_BYTE:
        emit(buffer[entry + 2])
    elif kind == I_WORD:
        emit(buffer[entry + 2])
        emit(buffer[entry + 3])
    elif kind == I_BRANCH:
        emit((target(buffer[entry + 2]) - (offset_now + 1)) & 0xFF)
    elif kind > I_FIX:
        symbol = buffer[entry + 2] | (buffer[entry + 3] << 8)
        slot = buffer[entry + 4]
        if symbol == own and slot >= FIRST_TEMP and slot != NO_SLOT:
            slot = slot - FIRST_TEMP + temp_base
        part = kind - I_FIX
        if part == FIX_ADDRESS and has_zero_page_form(opcode):
            part = FIX_SHRINKS
            if counting and symbol != own and slot != NO_SLOT:
                count_use(symbol, slot, offset_now - 1)
        fix(part, symbol, slot, buffer[entry + 5] | (buffer[entry + 6] << 8))
        emit(0)
        if kind == I_FIX + FIX_ADDRESS:
            emit(0)


def walk_begin():
    """Go back to the first instruction of the finished function."""
    global walk_entry, offset_now
    walk_entry = 0
    offset_now = 0


def walk_next():
    """Make the code of the next instruction the piece: piece_length bytes of `piece`, and if
    piece_fixed, its fix-up (fix_offset, fix_kind, fix_symbol, fix_slot, fix_addend). False when
    no instruction is left."""
    global walk_entry, piece_length, piece_fixed
    while walk_entry < used:
        piece_length = 0
        piece_fixed = False
        emit_entry(walk_entry)
        walk_entry += entry_size(buffer[walk_entry])
        if piece_length != 0:
            return True
    return False


def finish(symbol, base):
    """End the function, whose object-file symbol is `symbol`: settle its branches, and count
    its code, its fix-ups and the weights it gives other functions' slots. OUT then walks it
    (walk_begin(), walk_next()) for the fix-ups and again for the code. Its temporaries get the
    slot numbers from `base` on."""
    global code_length, fix_count, temp_base, weight_count, own, counting
    own = symbol
    temp_base = base
    thread()
    while True:
        size = layout()
        if not widen():
            break
    if size > MAX_CODE:
        err.fatal(err.E_FUNC_BIG)
    find_loops()
    code_length = size
    fix_count = 0
    weight_count = 0
    counting = True
    walk_begin()
    while walk_next():
        if piece_fixed:
            if fix_count == MAX_FIXUPS:
                err.fatal(err.E_FIXUPS_FULL)
            fix_count += 1
    counting = False
