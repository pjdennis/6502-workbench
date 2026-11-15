"""PARTS: the pieces of EXPR and STMT that parse no expression and call nothing of theirs that
does: type keywords, names and fields, the operators of each level of precedence and the
operands they combine, a string as a value, the code of a `for` loop's variable and step, and
the code of `with` blocks.

They are a module of their own, below EXPR (expr.py), so that EXPR's code fits a bank of the BBC
(16,300 bytes, docs/configurations.md, "The symbol table in a region"). EXPR and STMT stay one
module: they call each other, and Lathe forbids import cycles. What is here reaches no cycle of
their calls, so it can be below them.
"""
import err
import fbuf
import fold
import gen
import inline
import kernel
import lex
import out
import reg
import typetab

with_entry = reg.NONE   # map_bank(): the buffer entry of its LDA #bank, whose symbol comes later
FARCALL_MODULE = b"rt_with"     # the far-call module, as the linker resolves it (configurations.md)
MAP_NAME = b"map"               # map(value: byte in a): byte in a, the old value
UNMAP_NAME = b"unmap"           # unmap(value: byte in y), which keeps A, X, Y and the flags
map_symbol = kernel.NO_OBJ      # their object-file symbols, once used
unmap_symbol = kernel.NO_OBJ
FIX_BANK = 6                    # fix-up kind 6: the register value of a symbol's region
OP_LDA_IMMEDIATE = 0xA9
OP_STA = 0x8D
OP_LDY = 0xAC
OP_PHP = 0x08
OP_PLP = 0x28


def init():
    global map_symbol, unmap_symbol
    map_symbol = kernel.NO_OBJ
    unmap_symbol = kernel.NO_OBJ


def basic_type(token):
    """The type a type keyword names, or typetab.NO_TYPE."""
    if token == lex.T_BYTE:
        return typetab.BYTE_TYPE
    if token == lex.T_SBYTE:
        return typetab.SBYTE_TYPE
    if token == lex.T_WORD:
        return typetab.WORD_TYPE
    if token == lex.T_INT:
        return typetab.INT_TYPE
    if token == lex.T_BOOL:
        return typetab.BOOL_TYPE
    return typetab.NO_TYPE


def named_symbol():
    """name [ "." name ]: the symbol a name means here, or module.name means in that module,
    which must export it (a type that it does not export is in its interface all the same)."""
    if lex.tok != lex.T_NAME:
        err.fatal(err.E_NAME_EXPECTED)
    s, found = inline.lookup(lex.value)
    if not found:
        err.fatal(err.E_UNDEFINED)
    lex.next()
    if kernel.byte_of(s, kernel.C_KIND) == kernel.K_MODULE:
        m = s
        lex.expect(lex.T_DOT, err.E_DOT_EXPECTED)
        if lex.tok != lex.T_NAME:
            err.fatal(err.E_NAME_EXPECTED)
        s, found = kernel.module_find(m, lex.value)
        if not found or kernel.byte_of(s, kernel.C_FLAGS) & kernel.SF_PUB == 0:
            err.fatal(err.E_UNDEFINED)
        lex.next()
    return s


def field(line, col):
    """The name after the "." at `line`, `col`: a field of the record that the newest operand
    is or points to."""
    if lex.tok != lex.T_NAME:
        err.fatal(err.E_NAME_EXPECTED)
    err.position(line, col)
    t = gen.record_of()
    err.position(lex.line, lex.col)
    f, found = kernel.sym_find(kernel.SCOPE_FIELDS + t, lex.value)
    if not found:
        err.fatal(err.E_NO_FIELD)
    gen.field(kernel.word_of(f, kernel.C_VALUE), kernel.byte_of(f, kernel.C_TYPE))
    lex.next()


def string():
    """The string LEX has just read, used as a value: a `^byte` to constant data that holds
    it, with a zero after it. (Here and not in GEN, which then need not import LEX: its names
    would take 2 KB of GEN's name heap.)"""
    gen.settle()
    symbol = gen.anonymous()
    out.data(symbol, lex.string_length + 1)
    for i in range(0, lex.string_length):
        out.data_byte(lex.string_byte(i))
    out.data_byte(0)
    reg.push(reg.O_ADDR, typetab.pointer_to(typetab.BYTE_TYPE), 0)
    reg.op_symbol[reg.depth - 1] = symbol


def term_operator(token):
    """The operator a token of the `*` level stands for, or 0."""
    if token == lex.T_STAR:
        return fold.MUL
    if token == lex.T_SLASH:
        return fold.DIV
    if token == lex.T_MOD:
        return fold.REM
    if token == lex.T_AMP:
        return fold.BAND
    if token == lex.T_SHL:
        return fold.SHL
    if token == lex.T_SHR:
        return fold.SHR
    return 0


def sum_operator(token):
    """The operator a token of the `+` level stands for, or 0."""
    if token == lex.T_PLUS:
        return fold.ADD
    if token == lex.T_MINUS:
        return fold.SUB
    if token == lex.T_BAR:
        return fold.BOR
    if token == lex.T_CARET:
        return fold.BXOR
    return 0


def relation_operator(token):
    """The comparison a token stands for, or 0."""
    if token == lex.T_EQ:
        return fold.EQ
    if token == lex.T_NE:
        return fold.NE
    if token == lex.T_LT:
        return fold.LT
    if token == lex.T_GE:
        return fold.GE
    if token == lex.T_GT:
        return fold.GT
    if token == lex.T_LE:
        return fold.LE
    return 0


def apply(op, line, col):
    """Do the operator `op`, which was at `line`, `col`, on the two newest operands. Operands
    of the wrong type are reported there."""
    err.position(line, col)
    if op >= fold.EQ:
        gen.compare(op)
    else:
        gen.binary(op)
    err.position(lex.line, lex.col)


def test_operator(wanted, line, col, is_left):
    """One side of the `and` (`wanted` True) or `or` (False) at `line`, `col` is complete."""
    err.position(line, col)
    if is_left:
        if inline.copies_due():
            # The right side may not be run, so a call in it must not be what copies an
            # argument waiting for a register, or a variable an inline parameter stands for, to
            # its temporary: they are copied now, on both ways, keeping the flags, which hold
            # the left side's test.
            fbuf.op(OP_PHP)
            inline.copy_aliases()
            fbuf.op(OP_PLP)
            reg.flags = reg.NO_REG
        gen.test_left(wanted)
    else:
        gen.test_right()
    err.position(lex.line, lex.col)


def push_variable(s):
    """Push variable `s`: a local, or one that lives for the whole program."""
    if kernel.byte_of(s, kernel.C_KIND) == kernel.K_LOCAL:
        gen.local(kernel.byte_of(s, kernel.C_TYPE), kernel.word_of(s, kernel.C_VALUE))
    else:
        gen.variable(s)


def loop_variable():
    """The name after "for": a variable of a number type. Returns its symbol."""
    if lex.tok != lex.T_NAME:
        err.fatal(err.E_NAME_EXPECTED)
    s, found = inline.lookup(lex.value)
    if not found:
        err.fatal(err.E_UNDEFINED)
    if kernel.byte_of(s, kernel.C_KIND) != kernel.K_LOCAL and kernel.byte_of(s, kernel.C_KIND) != kernel.K_VAR:
        err.fatal(err.E_NOT_VAR)
    if not typetab.is_number(kernel.byte_of(s, kernel.C_TYPE)):
        err.fatal(err.E_TYPE)
    lex.next()
    return s


def compare_limit(limit, op):
    """Compare the newest operand, the loop variable or its first value, with the limit,
    operand `limit`. Returns the label gone to when the comparison is false."""
    reg.duplicate(limit)
    gen.compare(op)
    return gen.jump_false()


def step_back(s, down, limit, top):
    """INC or DEC loop variable `s` and go back to `top`. A BNE goes back where the step
    cannot give 0: counting up without a sign, or a byte counting down to a constant from 1
    to 127 (docs/codegen.md, "Statements")."""
    push_variable(s)
    i = reg.depth - 1
    size = typetab.size(reg.op_type[i])
    back = not down and not typetab.is_signed(reg.op_type[i])
    if down:
        back = size == 1 and reg.op_kind[limit] == reg.O_CONST and reg.op_value[limit] != 0 \
            and reg.op_value[limit] < 0x8000
        gen.step(fold.SUB, size, i)
    else:
        reg.modify(reg.OP_INC, i, 0)
        if size == 2:
            reg.branch(gen.OP_BNE, top)
            reg.modify(reg.OP_INC, i, 1)
    if back:
        reg.branch(gen.OP_BNE, top)
    else:
        reg.jump(top)
    reg.pop()


def restore_flags(count):
    """Leave `count` `critical` blocks: a PLP for each. The flags then show nothing known."""
    for n in range(0, count):
        fbuf.op(OP_PLP)
    reg.flags = reg.NO_REG


def farcall_symbols():
    """The symbols of rt_with.map and rt_with.unmap, and the IMP record of `rt_with`, which the
    first `with` block of the module writes. The linker gives these names to the environment's
    far-call module, or, with none, to the module `rt_with` that maps nothing."""
    global map_symbol, unmap_symbol
    if map_symbol != kernel.NO_OBJ:
        return
    module_name = gen.fixed_name(FARCALL_MODULE)
    out.imported(module_name)
    map_symbol = out.symbol(out.SYM_FUNCTION, module_name, 0, gen.fixed_name(MAP_NAME))
    unmap_symbol = out.symbol(out.SYM_FUNCTION, module_name, 0, gen.fixed_name(UNMAP_NAME))


def map_bank():
    """LDA #bank(REGION) / JSR rt_with.map / STA temporary: the region's bank in the window,
    and the bank it replaces kept. Returns the temporary; with_entry is the buffer entry of the
    LDA, whose fix-up names a symbol of the region once the block has used one (reg.NONE if
    the code cannot be reached)."""
    global with_entry
    farcall_symbols()
    reg.clobber()
    fbuf.op_fix(OP_LDA_IMMEDIATE, FIX_BANK, 0, fbuf.NO_SLOT, 0)
    with_entry = reg.NONE
    if not fbuf.unreached:
        with_entry = fbuf.newest
    fbuf.op_fix(fbuf.OP_JSR, fbuf.FIX_ADDRESS, map_symbol, fbuf.NO_SLOT, 0)
    out.call(map_symbol, 0, out.NO_OUTER)
    temp = reg.temp(1)
    fbuf.op_fix(OP_STA, fbuf.FIX_ADDRESS, reg.own, temp, 0)
    reg.use_slot(temp)
    reg.forget()
    return temp


def unmap_bank(temp):
    """LDY temporary / JSR rt_with.unmap: the bank that was in the window before the block
    that kept it in `temp`. A, X and the carry are kept, so a result can be on its way."""
    fbuf.op_fix(OP_LDY, fbuf.FIX_ADDRESS, reg.own, temp, 0)
    reg.use_slot(temp)
    fbuf.op_fix(fbuf.OP_JSR, fbuf.FIX_ADDRESS, unmap_symbol, fbuf.NO_SLOT, 0)
    out.call(unmap_symbol, 0, out.NO_OUTER)
    reg.forget()


def region_symbol(region):
    """The object-file symbol of the first variable or table of `region` that this module
    declares (at module level, or `static` in the function being compiled), or NO_OBJ. A block
    that uses nothing of its region names its bank by it: the linker learns a bank only from a
    variable or table of the region, and the module has no symbol of another module's that it
    has not used."""
    for s in range(0, kernel.sym_count):
        if (kernel.byte_of(s, kernel.C_KIND) == kernel.K_VAR or kernel.byte_of(s, kernel.C_KIND) == kernel.K_CONST) \
                and kernel.byte_of(s, kernel.C_FLAGS) & kernel.SF_IN != 0 and kernel.word_of(s, kernel.C_OBJ) != kernel.NO_OBJ \
                and reg.same_region(kernel.word_of(s, kernel.C_VALUE), region):
            return kernel.word_of(s, kernel.C_OBJ)
    return kernel.NO_OBJ
