"""ASM: the embedded assembler, for `asm` blocks and `asm` functions.

Owns
- the instruction table of the NMOS 6502;
- the line mode of an `asm` block: LEX hands over at the end of the line that opens the block,
  ASM reads the source a line at a time until a line whose first word is `end`, and hands
  that `end` back to LEX (docs/language.md, "Inline assembly");
- the block's local labels;
- the meaning of a Lathe name used as an operand, in name_operand(), the one place that has
  to learn each new kind of name.

Instructions go to FBUF like those GEN chooses, so a branch that does not reach is widened
like any other, and the sizes follow docs/object-format.md: a numeric address below $100 takes
the zero page form, a variable or slot is written in the absolute form with a two-byte fix-up
for the linker to shrink, and the indirect modes, which exist only in zero page, take a
one-byte fix-up and require the variable or slot to be in zero page.

The table. Every instruction belongs to a class, and the instructions of a class differ only in
a base opcode: the opcode for an addressing mode is the base plus the class's offset for that
mode. So the table is the mnemonics (three letters each), a base and a class for each, and an
offset for every class and mode: 462 bytes for the 56 instructions and 151 opcodes. The 65C02's
instructions are to go after the NMOS ones, with classes of their own and, for the modes it
adds to old instructions, offsets of its own, all used only when gen.cpu is 1.
"""
import err
import fbuf
import gen
import kernel
import lex
import out
import reg
import src

# ---- The instruction table ---------------------------------------------------------------

# Addressing modes. The absolute form of a zero page mode is that mode + ZP_TO_ABS.
M_IMP = 0           # implied
M_ACC = 1           # accumulator: ASL A, or ASL
M_IMM = 2           # #value
M_ZP = 3
M_ZPX = 4
M_ZPY = 5
M_ABS = 6
M_ABSX = 7
M_ABSY = 8
M_INDX = 9          # (zp,X)
M_INDY = 10         # (zp),Y
M_IND = 11          # (abs), for JMP
M_REL = 12          # a branch
MODES = 13
ZP_TO_ABS = 3
NO_MODE = 0xFF

MNEMONICS = (
    b"adcandaslbccbcsbeqbitbmibnebplbrkbvcbvsclccldcliclvcmpcpxcpydecdexdeyeorinc"
    b"inxinyjmpjsrldaldxldylsrnoporaphaphpplaplprolrorrtirtssbcsecsedseistastxsty"
    b"taxtaytsxtxatxstya"
)
NMOS_COUNT = 56

# For each mnemonic, in the order of MNEMONICS: the base opcode, and the class.
BASE = (
    b"\x61\x21\x02\x90\xb0\xf0\x20\x30\xd0\x10\x00\x50\x70\x18\xd8\x58\xb8\xc1\xe0\xc0"
    b"\xc2\xca\x88\x41\xe2\xe8\xc8\x4c\x20\xa1\xa2\xa0\x42\xea\x01\x48\x08\x68\x28\x22"
    b"\x62\x40\x60\xe1\x38\xf8\x78\x81\x82\x80\xaa\xa8\xba\x8a\x9a\x98"
)
CLASS = (
    b"\x02\x02\x04\x01\x01\x01\x0b\x01\x01\x01\x00\x01\x01\x00\x00\x00\x00\x02\x0a\x0a"
    b"\x05\x00\x00\x02\x05\x00\x00\x0c\x0d\x02\x06\x08\x04\x00\x02\x00\x00\x00\x00\x04"
    b"\x04\x00\x00\x02\x00\x00\x00\x03\x07\x09\x00\x00\x00\x00\x00\x00"
)

# For each class, the offset from the base for each mode, or NO_MODE.
#    IMP ACC IMM ZP  ZPX ZPY ABS ABX ABY INX INY IND REL
MODE_OFFSET = (
    b"\x00\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff"     # 0 implied
    b"\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\x00"     # 1 branches
    b"\xff\xff\x08\x04\x14\xff\x0c\x1c\x18\x00\x10\xff\xff"     # 2 ADC AND CMP EOR LDA ORA SBC
    b"\xff\xff\xff\x04\x14\xff\x0c\x1c\x18\x00\x10\xff\xff"     # 3 STA
    b"\xff\x08\xff\x04\x14\xff\x0c\x1c\xff\xff\xff\xff\xff"     # 4 ASL LSR ROL ROR
    b"\xff\xff\xff\x04\x14\xff\x0c\x1c\xff\xff\xff\xff\xff"     # 5 DEC INC
    b"\xff\xff\x00\x04\xff\x14\x0c\xff\x1c\xff\xff\xff\xff"     # 6 LDX
    b"\xff\xff\xff\x04\xff\x14\x0c\xff\xff\xff\xff\xff\xff"     # 7 STX
    b"\xff\xff\x00\x04\x14\xff\x0c\x1c\xff\xff\xff\xff\xff"     # 8 LDY
    b"\xff\xff\xff\x04\x14\xff\x0c\xff\xff\xff\xff\xff\xff"     # 9 STY
    b"\xff\xff\x00\x04\xff\xff\x0c\xff\xff\xff\xff\xff\xff"     # 10 CPX CPY
    b"\xff\xff\xff\x04\xff\xff\x0c\xff\xff\xff\xff\xff\xff"     # 11 BIT
    b"\xff\xff\xff\xff\xff\xff\x00\xff\xff\xff\xff\x20\xff"     # 12 JMP
    b"\xff\xff\xff\xff\xff\xff\x00\xff\xff\xff\xff\xff\xff"     # 13 JSR
)

OP_JMP = 0x4C
OP_JSR = 0x20


def instruction_count():
    """How many instructions the CPU being compiled for has."""
    return NMOS_COUNT


def opcode(m, mode):
    """The opcode of instruction `m` in addressing mode `mode`, and whether it has that mode."""
    offset = MODE_OFFSET[CLASS[m] * MODES + mode]
    if offset == NO_MODE:
        return 0, False
    return (BASE[m] + offset) & 0xFF, True


def has_mode(m, mode):
    _, ok = opcode(m, mode)
    return ok


# ---- Characters and words ----------------------------------------------------------------

C_TAB = 0x09
C_LF = 0x0A
C_CR = 0x0D
C_SPACE = 0x20
C_HASH = 0x23
C_DOLLAR = 0x24
C_PERCENT = 0x25
C_QUOTE = 0x27
C_LPAREN = 0x28
C_RPAREN = 0x29
C_PLUS = 0x2B
C_COMMA = 0x2C
C_MINUS = 0x2D
C_DOT = 0x2E
C_COLON = 0x3A
C_SEMICOLON = 0x3B
C_LESS = 0x3C
C_GREATER = 0x3E
C_UNDERSCORE = 0x5F
C_A = 0x61
C_X = 0x78
C_Y = 0x79
END_WORD = b"end"

MAX_SPELLING = 31
spelling = bytearray(MAX_SPELLING)     # the word just read, in lower case
spelling_length = 0


def at_line_end():
    """True at the end of the line: its line feed, a comment, or the end of the source."""
    return src.eof or src.ch == C_LF or src.ch == C_SEMICOLON


def skip_blanks():
    while not src.eof and (src.ch == C_SPACE or src.ch == C_TAB or src.ch == C_CR):
        src.advance()


def skip_line():
    """Pass over the rest of the line and its line feed."""
    while not src.eof and src.ch != C_LF:
        src.advance()
    src.advance()


def is_word_char(c):
    return lex.is_letter(c) or lex.is_digit(c) or c == C_UNDERSCORE


def read_word():
    """Read the letters, digits and underscores here into `spelling`. There may be none."""
    global spelling_length
    spelling_length = 0
    while not src.eof and is_word_char(src.ch):
        if spelling_length < MAX_SPELLING:
            spelling[spelling_length] = lex.fold(src.ch)
            spelling_length += 1
        src.advance()


def word_is_letter(letter):
    """True if the word just read is the one letter `letter` (in lower case)."""
    return spelling_length == 1 and spelling[0] == letter


def word_name():
    """The word just read, as a name in the kernel's heap."""
    kernel.name_begin()
    for i in range(0, spelling_length):
        kernel.name_add(spelling[i])
    return kernel.name_end()


def find_mnemonic():
    """The instruction the word just read names, and whether it names one."""
    if spelling_length != 3:
        return 0, False
    for m in range(0, instruction_count()):
        if MNEMONICS[3 * m] == spelling[0] and MNEMONICS[3 * m + 1] == spelling[1] \
                and MNEMONICS[3 * m + 2] == spelling[2]:
            return m, True
    return 0, False


def is_end_word():
    if spelling_length != len(END_WORD):
        return False
    for i in range(0, len(END_WORD)):
        if spelling[i] != END_WORD[i]:
            return False
    return True


def fail_at(at_line, at_col, number):
    err.position(at_line, at_col)
    err.fatal(number)


# ---- Local labels ------------------------------------------------------------------------

MAX_BLOCK_LABELS = 64

label_name = [0] * MAX_BLOCK_LABELS        # the name, without its dot
label_number = [0] * MAX_BLOCK_LABELS      # the FBUF label
label_defined = [False] * MAX_BLOCK_LABELS
label_line = [0] * MAX_BLOCK_LABELS        # where it was first used, for the error if never defined
label_col = [0] * MAX_BLOCK_LABELS
label_count = 0


def label_find(name, at_line, at_col):
    """The block's label called `name`, made if it is new."""
    global label_count
    for i in range(0, label_count):
        if label_name[i] == name:
            return i
    if label_count == MAX_BLOCK_LABELS:
        err.fatal(err.E_LABELS_FULL)
    label_name[label_count] = name
    label_number[label_count] = fbuf.new_label()
    label_defined[label_count] = False
    label_line[label_count] = at_line
    label_col[label_count] = at_col
    label_count += 1
    return label_count - 1


def label_define(name, at_line, at_col):
    """The label called `name` is here."""
    i = label_find(name, at_line, at_col)
    if label_defined[i]:
        fail_at(at_line, at_col, err.E_DUPLICATE)
    label_defined[i] = True
    fbuf.place(label_number[i])


def labels_check():
    """Every label the block used must be defined in it."""
    for i in range(0, label_count):
        if not label_defined[i]:
            fail_at(label_line[i], label_col[i], err.E_ASM_NO_LABEL)


# ---- Lathe names -------------------------------------------------------------------------

# What a name, or an expression, is
X_NUMBER = 1        # x_value
X_LABEL = 2         # x_value: the block's label
X_ADDRESS = 3       # an address the linker fills in: x_symbol, x_slot, and x_value the addend

NO_STORAGE = 0xFFFF
VARIABLE_STORAGE = reg.SLOTS    # a storage number below this is a slot; from it on, a variable

# Set by name_operand()
found_value = 0         # X_NUMBER: the number
found_symbol = 0        # X_ADDRESS: the object-file symbol
found_slot = 0          # X_ADDRESS: the slot of that function, or fbuf.NO_SLOT
found_storage = 0       # X_ADDRESS: the variable or slot, for storage_used(), or NO_STORAGE
found_function = False  # X_ADDRESS: the address is a function's entry, so JSR and JMP are calls


def name_operand(name, member):
    """What the Lathe name `name`, or `name.member` if `member` is not 0, means as an operand.
    Returns X_NUMBER or X_ADDRESS, with the found_ variables set; an undefined name is an error
    at the current position.

    - A constant is its value; an `extern` function, and a variable at a fixed address, its
      address.
    - A function of this or another module is its entry, through a fix-up.
    - A variable that lives for the whole program (of this module, a `static` one of the
      function, or one of another module) is its address: found_symbol is its symbol,
      found_slot NO_SLOT, found_storage VARIABLE_STORAGE + its kernel symbol.
    - A parameter or local of the function being compiled is a slot: found_symbol is the
      function's symbol, and found_slot and found_storage the slot's number. The parameters
      of an `asm` function are in registers and have no names here."""
    global found_value, found_symbol, found_slot, found_storage, found_function
    s, found = kernel.sym_lookup(name)
    if not found:
        err.fatal(err.E_UNDEFINED)
    if kernel.sym_kind[s] == kernel.K_MODULE:
        if member == 0:
            err.fatal(err.E_DOT_EXPECTED)
        s, found = kernel.sym_find(kernel.sym_value[s], member)
        if not found:
            err.fatal(err.E_UNDEFINED)
    elif member != 0:
        err.fatal(err.E_SYNTAX)
    found_storage = NO_STORAGE
    found_function = False
    found_slot = fbuf.NO_SLOT
    kind = kernel.sym_kind[s]
    if kind == kernel.K_CONST:
        found_value = kernel.sym_value[s] & 0xFFFF
        return X_NUMBER
    if kind == kernel.K_LOCAL:
        found_symbol = reg.own
        found_slot = kernel.sym_value[s]
        found_storage = found_slot
        return X_ADDRESS
    if kind == kernel.K_VAR:
        if kernel.sym_flags[s] & kernel.SF_AT != 0:
            found_value = kernel.sym_value[s]
            return X_NUMBER
        found_symbol = gen.object_symbol(s)
        found_storage = VARIABLE_STORAGE + s
        return X_ADDRESS
    if kind != kernel.K_FUNC:
        err.fatal(err.E_TYPE)
    if kernel.sym_flags[s] & kernel.SF_EXTERN != 0:
        found_value = kernel.sym_value[s]
        return X_NUMBER
    found_symbol = gen.object_symbol(s)
    found_function = True
    return X_ADDRESS


def storage_used(storage, zero_page):
    """An instruction uses variable or slot `storage` (found by name_operand): add to its
    weight as a use by compiled code adds (docs/codegen.md, "Weights"), and if `zero_page`
    make its class 0, "must be in zero page". Only an `asm` block can do that. A variable or
    slot declared `nozp` cannot be made so, nor can a variable of another module, whose class
    its own module wrote: that one must have been declared `zp`."""
    if storage < VARIABLE_STORAGE:
        reg.use_slot(storage)
        if zero_page:
            if reg.slot_class[storage] == reg.CLASS_NOT_ZP:
                err.fatal(err.E_ASM_NOT_ZP)
            reg.slot_class[storage] = reg.CLASS_ZP
        return
    s = storage - VARIABLE_STORAGE
    reg.use_variable(s)
    if not zero_page or kernel.sym_flags[s] & kernel.SF_ZP != 0:
        return
    if kernel.sym_flags[s] & kernel.SF_NOZP != 0:
        err.fatal(err.E_ASM_NOT_ZP)
    if kernel.sym_scope[s] != kernel.SCOPE_MODULE and kernel.sym_scope[s] != kernel.SCOPE_LOCAL:
        err.fatal(err.E_ASM_NOT_ZP)
    kernel.sym_flags[s] = kernel.sym_flags[s] | kernel.SF_ZP


# ---- Expressions -------------------------------------------------------------------------

x_kind = 0
x_value = 0
x_symbol = 0
x_slot = 0
x_storage = 0
x_function = False
x_line = 0          # where the expression starts
x_col = 0


def number_term():
    """A number: $hex, %binary, decimal or a character. Returns its value."""
    err.position(src.line, src.col)
    if src.ch == C_DOLLAR:
        src.advance()
        return lex.number(16)
    if src.ch == C_PERCENT:
        src.advance()
        return lex.number(2)
    if src.ch == C_QUOTE:
        src.advance()
        return lex.character()
    if lex.is_digit(src.ch):
        return lex.number(10)
    err.fatal(err.E_EXPR_EXPECTED)
    return 0


def name_term():
    """name [ "." name ], whose first word has been read."""
    global x_kind, x_value, x_symbol, x_slot, x_storage, x_function
    first = word_name()
    member = 0
    if src.ch == C_DOT:
        src.advance()
        read_word()
        if spelling_length == 0:
            err.fatal(err.E_NAME_EXPECTED)
        member = word_name()
    err.position(x_line, x_col)
    x_kind = name_operand(first, member)
    x_value = found_value
    x_symbol = found_symbol
    x_slot = found_slot
    x_storage = found_storage
    x_function = found_function
    if x_kind == X_ADDRESS:
        x_value = 0


def term(have_word):
    """A number, a local label or a Lathe name. If `have_word`, the name's first word has been
    read already."""
    global x_kind, x_value
    if have_word:
        name_term()
    elif src.ch == C_DOT:
        src.advance()
        read_word()
        if spelling_length == 0:
            fail_at(x_line, x_col, err.E_NAME_EXPECTED)
        x_kind = X_LABEL
        x_value = label_find(word_name(), x_line, x_col)
    elif lex.is_letter(src.ch):
        read_word()
        name_term()
    else:
        x_kind = X_NUMBER
        x_value = number_term()


def expression(have_word):
    """expr = term { ( "+" | "-" ) number }. The result is in the x_ variables."""
    global x_value
    term(have_word)
    skip_blanks()
    while src.ch == C_PLUS or src.ch == C_MINUS:
        adding = src.ch == C_PLUS
        src.advance()
        skip_blanks()
        n = number_term()
        if x_kind == X_LABEL:
            fail_at(x_line, x_col, err.E_ASM_LABEL_USE)
        if x_kind == X_NUMBER and adding and n > 0xFFFF - x_value:
            fail_at(x_line, x_col, err.E_ASM_RANGE)
        if x_kind == X_NUMBER and not adding and n > x_value:
            fail_at(x_line, x_col, err.E_ASM_RANGE)
        if adding:
            x_value = (x_value + n) & 0xFFFF
        else:
            x_value = (x_value - n) & 0xFFFF
        skip_blanks()


def expression_here():
    """Note where the expression about to be read starts."""
    global x_line, x_col
    x_line = src.line
    x_col = src.col


# ---- Instructions ------------------------------------------------------------------------

def fail_mode():
    fail_at(x_line, x_col, err.E_ASM_MODE)


def use_storage(zero_page):
    if x_storage != NO_STORAGE:
        err.position(x_line, x_col)
        storage_used(x_storage, zero_page)


def address_fix(op, kind):
    """The instruction `op` with the address expression as its operand, through a fix-up."""
    fbuf.op_fix(op, kind, x_symbol, x_slot, x_value)


def implied(m):
    """No operand: implied, or the accumulator."""
    op, ok = opcode(m, M_IMP)
    if not ok:
        op, ok = opcode(m, M_ACC)
    if not ok:
        fail_mode()
    fbuf.op(op)


def accumulator(m):
    op, ok = opcode(m, M_ACC)
    if not ok:
        fail_mode()
    fbuf.op(op)


def branch(m):
    expression(False)
    op, _ = opcode(m, M_REL)
    if x_kind != X_LABEL:
        fail_at(x_line, x_col, err.E_ASM_BRANCH)
    fbuf.branch(op, label_number[x_value])


def immediate(m):
    """#expr, #<expr or #>expr, after the "#"."""
    op, ok = opcode(m, M_IMM)
    if not ok:
        fail_mode()
    selector = 0
    if src.ch == C_LESS or src.ch == C_GREATER:
        selector = src.ch
        src.advance()
        skip_blanks()
    expression_here()
    expression(False)
    if x_kind == X_LABEL:
        fail_at(x_line, x_col, err.E_ASM_LABEL_USE)
    if x_kind == X_ADDRESS:
        if selector == C_LESS:
            address_fix(op, fbuf.FIX_LOW)
        elif selector == C_GREATER:
            address_fix(op, fbuf.FIX_HIGH)
        else:
            fail_at(x_line, x_col, err.E_ASM_RANGE)
        return
    value = x_value
    if selector == C_LESS:
        value = value & 0xFF
    elif selector == C_GREATER:
        value = (value >> 8) & 0xFF
    elif value > 0xFF:
        fail_at(x_line, x_col, err.E_ASM_RANGE)
    fbuf.op_byte(op, value)


def index_register():
    """"X" or "Y", after a comma. Returns the letter."""
    skip_blanks()
    read_word()
    if not word_is_letter(C_X) and not word_is_letter(C_Y):
        err.position(src.line, src.col)
        err.fatal(err.E_SYNTAX)
    skip_blanks()
    return spelling[0]


def expect_char(c, number):
    skip_blanks()
    if src.ch != c:
        err.position(src.line, src.col)
        err.fatal(number)
    src.advance()
    skip_blanks()


def indirect(m):
    """(expr,X), (expr),Y or (expr), after the "("."""
    skip_blanks()
    expression_here()
    expression(False)
    mode = M_IND
    if src.ch == C_COMMA:
        src.advance()
        if index_register() != C_X:
            fail_mode()
        expect_char(C_RPAREN, err.E_RPAREN_EXPECTED)
        mode = M_INDX
    else:
        expect_char(C_RPAREN, err.E_RPAREN_EXPECTED)
        if src.ch == C_COMMA:
            src.advance()
            if index_register() != C_Y:
                fail_mode()
            mode = M_INDY
    op, ok = opcode(m, mode)
    if not ok:
        fail_mode()
    if x_kind == X_LABEL:
        fail_at(x_line, x_col, err.E_ASM_LABEL_USE)
    if mode == M_IND:
        if x_kind == X_NUMBER:
            fbuf.op_word(op, x_value)
        else:
            address_fix(op, fbuf.FIX_ADDRESS)
            use_storage(False)
        return
    if x_kind == X_NUMBER:
        if x_value > 0xFF:
            fail_at(x_line, x_col, err.E_ASM_RANGE)
        fbuf.op_byte(op, x_value)
    elif x_storage == NO_STORAGE:
        fail_at(x_line, x_col, err.E_ASM_RANGE)       # a function is never in zero page
    else:
        address_fix(op, fbuf.FIX_ZERO_PAGE)
        use_storage(True)


def direct(m, have_word):
    """expr, expr,X or expr,Y. If `have_word`, the expression's first word has been read."""
    expression(have_word)
    zp_mode = M_ZP
    if src.ch == C_COMMA:
        src.advance()
        if index_register() == C_X:
            zp_mode = M_ZPX
        else:
            zp_mode = M_ZPY
    zp_op, has_zp = opcode(m, zp_mode)
    abs_op, has_abs = opcode(m, zp_mode + ZP_TO_ABS)
    if not has_zp and not has_abs:
        fail_mode()
    if x_kind == X_LABEL:
        if abs_op != OP_JMP or zp_mode != M_ZP:
            fail_at(x_line, x_col, err.E_ASM_LABEL_USE)
        fbuf.jump(label_number[x_value])
    elif x_kind == X_NUMBER:
        if has_zp and x_value < 0x100:
            fbuf.op_byte(zp_op, x_value)
        elif has_abs:
            fbuf.op_word(abs_op, x_value)
        else:
            fail_at(x_line, x_col, err.E_ASM_RANGE)
    elif has_abs:
        address_fix(abs_op, fbuf.FIX_ADDRESS)
        use_storage(False)
        if x_function and (abs_op == OP_JSR or abs_op == OP_JMP):
            out.call(x_symbol, 0, out.NO_OUTER)
    elif x_storage == NO_STORAGE:
        fail_at(x_line, x_col, err.E_ASM_RANGE)
    else:
        # STX zp,Y and STY zp,X have no absolute form: the operand must be in zero page.
        address_fix(zp_op, fbuf.FIX_ZERO_PAGE)
        use_storage(True)


def instruction(m):
    """The operand of instruction `m`, if it has one, and its code."""
    skip_blanks()
    expression_here()
    if at_line_end():
        implied(m)
    elif has_mode(m, M_REL):
        branch(m)
    elif src.ch == C_HASH:
        src.advance()
        skip_blanks()
        immediate(m)
    elif src.ch == C_LPAREN:
        src.advance()
        indirect(m)
    elif lex.is_letter(src.ch):
        read_word()
        skip_blanks()
        if word_is_letter(C_A) and at_line_end() and has_mode(m, M_ACC):
            accumulator(m)
        else:
            direct(m, True)
    else:
        direct(m, False)
    skip_blanks()
    if not at_line_end():
        fail_at(src.line, src.col, err.E_NL_EXPECTED)


# ---- Lines -------------------------------------------------------------------------------

end_line = 0        # where the `end` that closed the block is
end_col = 0


def mnemonic_here(at_line, at_col):
    """The instruction the word just read names; if none, an error at the word."""
    m, ok = find_mnemonic()
    if not ok:
        fail_at(at_line, at_col, err.E_ASM_MNEMONIC)
    return m


def label_line_rest(at_line, at_col):
    """A line that starts with a dot: a label, alone or before an instruction, or a directive,
    which blocks do not have. The dot has been passed over."""
    read_word()
    if spelling_length == 0:
        fail_at(at_line, at_col, err.E_NAME_EXPECTED)
    name = word_name()
    colon = src.ch == C_COLON
    if colon:
        src.advance()
    skip_blanks()
    if at_line_end():
        label_define(name, at_line, at_col)
        return
    word_line = src.line
    word_col = src.col
    if not lex.is_letter(src.ch):
        fail_at(at_line, at_col, err.E_ASM_DIRECTIVE)
    read_word()
    m, ok = find_mnemonic()
    if not ok and not colon:
        fail_at(at_line, at_col, err.E_ASM_DIRECTIVE)
    if not ok:
        fail_at(word_line, word_col, err.E_ASM_MNEMONIC)
    label_define(name, at_line, at_col)
    instruction(m)


def asm_line():
    """One line of the block. Returns False for the line that ends it, whose `end` has been
    read; True for any other, which has been passed over with its line feed."""
    global end_line, end_col
    skip_blanks()
    if src.eof:
        fail_at(src.line, src.col, err.E_END_EXPECTED)
    if at_line_end():
        skip_line()
        return True
    at_line = src.line
    at_col = src.col
    err.position(at_line, at_col)
    if src.ch == C_DOT:
        src.advance()
        label_line_rest(at_line, at_col)
    else:
        if not lex.is_letter(src.ch):
            fail_at(at_line, at_col, err.E_ASM_MNEMONIC)
        read_word()
        if is_end_word():
            end_line = at_line
            end_col = at_col
            return False
        instruction(mnemonic_here(at_line, at_col))
    skip_line()
    return True


def lines():
    """The lines of a block, after the line that opens it, up to and including its `end`,
    which is given back to LEX as the current token."""
    global label_count
    if lex.tok != lex.T_NL:
        err.fatal(err.E_NL_EXPECTED)
    label_count = 0
    fbuf.as_written(True)
    while asm_line():
        pass
    fbuf.as_written(False)
    labels_check()
    lex.resume(lex.T_END, end_line, end_col)


def block():
    """The statement "asm" NL { asmLine NL } "end". The token is "asm"; what follows the `end`
    is left to the caller. A, X and Y hold nothing known before or after it."""
    lex.next()
    reg.forget()
    lines()
    fbuf.keep_as_written()
    reg.forget()
    lex.next()


def function_body():
    """The lines of an `asm` function, after its head, whose line end is the token, up to its
    `end`, which is the token after. If the code can run on past its last line, an RTS ends
    it: the last instruction is never made a jump, as a tail call in compiled code is."""
    lines()
    if fbuf.runs_on():
        fbuf.op(fbuf.OP_RTS)
