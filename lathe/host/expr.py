"""EXPR and STMT: expressions, statements, and types as they are written in the source.

EXPR owns the parsing of everything that can stand where a value is wanted: one function for
each level of precedence in docs/language.md, from expression() down to primary(). What it
parses becomes operands on GEN's stack; EXPR itself chooses no instruction. It says where an
error in an operand's type is reported: at the operator, or at the start of the value.

STMT owns the parsing of a function's body: each statement of docs/language.md has a function
here, chosen in statement() by its first token, and the shapes they generate are those of
docs/codegen.md, "Statements". It knows the loop that `break` and `continue` belong to, and
the function whose results `return` gives.

They are one file because they call each other: a statement holds expressions, and a call of
an `inline` function inside an expression compiles that function's body, which is statements
(docs/code-model.md, "Inline functions"). Lathe forbids import cycles, so the two cannot be
modules that import each other.

Types are parsed here and not in DECL because conversions and `sizeof` need them inside
expressions, and array types need a constant expression. Variable declarations are parsed here,
for DECL too, because a body has them.
"""
import asmblock
import err
import fbuf
import fold
import gen
import inline
import kernel
import lex
import out
import parts
import reg
import src
import typetab

RECURSIVE = ["expression", "factor", "inverse", "body"]

# The functions the language declares, as decl.BUILTINS lists them
B_LO = 0
B_HI = 1
B_SIZEOF = 2
B_LEN = 3

passing = False         # True while a call that gives a value and a status may stand without
#                         `->`: in a `return` that passes both on
passed = reg.NONE       # gen.mark() just after such a call, if there was one

MAX_PENDING = 16
pending = [0] * MAX_PENDING     # the functions whose arguments are being stored in their frames,
pending_count = 0               # with at least one stored already: the outermost first

# How deeply expressions and blocks may nest: each expression (one in parentheses, brackets or
# arguments, or the operand of a `-`, `~` or `not`) and each body of a block is a level, and
# the arguments of a call and a `for` are one more each. The parser is recursive, and
# lathe/src/expr.lth keeps a level's state on the 6502's stack and rt_frame's, 256 bytes each
# (docs/code-model.md, "Recursion"): nesting this deep fits both with room to spare.
MAX_NESTING = 16
nesting = 0


def init():
    global passing, passed, pending_count, nesting
    passing = False
    passed = reg.NONE
    pending_count = 0
    nesting = 0
    parts.init()


def line_end():
    """The current token must end the line; the next line's first token is read."""
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)


def here():
    """Errors found from now on are at the current token."""
    err.position(lex.line, lex.col)


def nest():
    """One more level of nesting begins."""
    global nesting
    if nesting == MAX_NESTING:
        err.fatal(err.E_NESTING)
    nesting += 1


def unnest():
    """A level of nesting ends."""
    global nesting
    nesting -= 1


# ---- Types and names ---------------------------------------------------------------------


def type_spec():
    """type = typeKw | name [ "." name ] | "^" type | "[" constExpr "]" type. Returns the
    type. A record is written only in a type declaration (DECL)."""
    mark = typetab.prefix_count
    while lex.tok == lex.T_CARET or lex.tok == lex.T_LBRACKET:
        if lex.tok == lex.T_CARET:
            lex.next()
            typetab.prefix(typetab.FORM_POINTER, 0)
        else:
            lex.next()
            line = lex.line
            col = lex.col
            n = constant_number()
            if n == 0:
                err.position(line, col)
                err.fatal(err.E_RANGE)
            lex.expect(lex.T_RBRACKET, err.E_SYNTAX)
            typetab.prefix(typetab.FORM_ARRAY, n)
    t = parts.basic_type(lex.tok)
    line = lex.line
    col = lex.col
    if t != typetab.NO_TYPE:
        lex.next()
    elif lex.tok == lex.T_NAME:
        s = parts.named_symbol()
        if kernel.kind_of(s) != kernel.K_TYPE:
            err.position(line, col)
            err.fatal(err.E_TYPE_EXPECTED)
        t = kernel.type_of(s)
    elif lex.tok == lex.T_RECORD:
        err.fatal(err.E_RECORD_PLACE)
    elif lex.tok == lex.T_FUNC or lex.tok == lex.T_RECURSIVE:
        err.fatal(err.E_FUNC_TYPE_PLACE)
    else:
        err.fatal(err.E_TYPE_EXPECTED)
    return typetab.build(t, mark)


def value_type():
    """The type of a parameter or a result: not an array or a record, which are not values."""
    line = lex.line
    col = lex.col
    t = type_spec()
    err.position(line, col)
    if typetab.is_array(t):
        err.fatal(err.E_ARRAY_VALUE)
    if typetab.is_record(t):
        err.fatal(err.E_RECORD_VALUE)
    here()
    return t


# ---- Designators and calls ---------------------------------------------------------------

def builtin(which):
    """`lo(x)`, `hi(x)`, `len(a)` or `sizeof(type)`, after its name."""
    lex.expect(lex.T_LPAREN, err.E_LPAREN_EXPECTED)
    if which == B_SIZEOF:
        gen.size_of(type_spec())
    else:
        line = lex.line
        col = lex.col
        expression()
        err.position(line, col)
        if which == B_LEN:
            gen.length()
        else:
            gen.part(which)
        here()
    lex.expect(lex.T_RPAREN, err.E_RPAREN_EXPECTED)


def designator():
    """designator = name { "." name | "[" expression "]" }. Pushes an operand for what it
    names. A named type followed by "(" is a conversion."""
    line = lex.line
    col = lex.col
    s = parts.named_symbol()
    kind = kernel.kind_of(s)
    if kind == kernel.K_FUNC:
        gen.function(s)
    elif kind == kernel.K_CONST and typetab.is_array(kernel.type_of(s)):
        err.position(line, col)         # a table in a region is used only inside `with`
        gen.table(s)
        here()
    elif kind == kernel.K_CONST:
        gen.constant(kernel.type_of(s), kernel.value_of(s))
    elif kind == kernel.K_LOCAL:
        gen.local(kernel.type_of(s), kernel.value_of(s))
    elif kind == kernel.K_VAR:
        err.position(line, col)
        gen.variable(s)
        here()
    elif kind == kernel.K_TYPE:
        conversion(kernel.type_of(s), line, col)
    else:
        builtin(kernel.value_of(s))
    while lex.tok == lex.T_LBRACKET or lex.tok == lex.T_DOT:
        line = lex.line
        col = lex.col
        if lex.tok == lex.T_DOT:
            lex.next()
            parts.field(line, col)
        else:
            lex.next()
            expression()
            lex.expect(lex.T_RBRACKET, err.E_SYNTAX)
            err.position(line, col)
            gen.index()
            here()


def target(line, col):
    """Check that the newest operand, which the designator at `line`, `col` gave, is a variable
    that can be assigned to."""
    i = reg.depth - 1
    if reg.op_kind[i] != reg.O_VAR or reg.op_flags[i] & reg.F_DATA != 0 \
            or (reg.op_flags[i] & reg.F_TEMP != 0 and reg.op_mode[i] != reg.M_POINTER):
        err.position(line, col)
        err.fatal(err.E_NOT_VAR)


def argument(t, stored):
    """One argument for a parameter of type `t`. If `stored`, the parameter is the newest
    operand and the argument is stored in it; if not, the argument is left on the stack. One
    that does not fit is reported at its start."""
    line = lex.line
    col = lex.col
    expression()
    err.position(line, col)
    if stored:
        gen.store()
    else:
        gen.accept(t)
    here()


def arguments(f):
    """[ expression { "," expression } ] ")", after the "(". Each argument goes straight to
    its parameter in the frame of function `f`, except those passed in registers (all of an
    `extern` or `asm` function's), which stay on the stack, in order, for GEN to load at the call."""
    global pending_count
    nest()
    saved = gen.outer
    saved_pending = pending_count
    count = 0
    if lex.tok != lex.T_RPAREN:
        while True:
            if count == kernel.params_of(f):
                err.fatal(err.E_ARG_COUNT)
            by_register = gen.in_register(f, count)
            if not by_register:
                gen.parameter(f, count)
            argument(kernel.member_type_of(kernel.word_of(f, kernel.C_MEMBERS) + count), not by_register)
            count += 1
            if lex.tok != lex.T_COMMA:
                break
            if by_register:
                gen.hold()
            elif not gen.saving(f) and (count == 1 or gen.in_register(f, count - 2)):
                add_pending(f)      # the first argument stored in the frame
            lex.next()
    if lex.tok != lex.T_RPAREN:
        err.fatal(err.E_RPAREN_EXPECTED)
    if count != kernel.params_of(f):
        err.fatal(err.E_ARG_COUNT)
    pending_count = saved_pending
    gen.arguments_end(saved)
    unnest()
    lex.next()


def add_pending(f):
    """An argument of `f` is in its frame, and the next is about to be worked out."""
    global pending_count
    if pending_count == MAX_PENDING:
        err.fatal(err.E_OPERANDS_FULL)
    pending[pending_count] = f
    pending_count += 1


def check_not_pending(f):
    """A call of `f` is about to be made: none of its own arguments may be waiting in its
    frame, which the call's arguments would overwrite. (A call of another function is
    allowed: its CALL record names the function whose arguments wait as `outer`.)"""
    for i in range(0, pending_count):
        if pending[i] == f:
            err.fatal(err.E_CALL_IN_ARGUMENTS)


def call(wanted):
    """arguments = "(" [ expression { "," expression } ] ")", for the function whose operand
    is on top of the stack. Generates the call and, if its results are `wanted`, leaves what
    gen.result() pushes. A call of an inline function is an expansion of its body."""
    global passing
    f = reg.op_var[reg.depth - 1]
    if not gen.through(f) and kernel.flags_of(f) & inline.SF_INTERRUPT != 0:
        err.fatal(err.E_INTERRUPT_CALL)
    if not gen.through(f) and kernel.flags_of(f) & inline.SF_INLINE != 0:
        reg.pop()
        inline.enter(f, wanted)     # errors at the "("
        lex.next()
        saved = passing
        passing = False
        expand()
        passing = saved
        return
    if not gen.through(f):
        reg.pop()               # a pointer called through stays until the call
    lex.next()
    inline.copy_aliases()
    first = reg.depth
    saved = passing
    passing = False             # a call inside an argument passes nothing on
    arguments(f)
    passing = saved
    gen.call(f, first, wanted)


def callee():
    """The designator just parsed is called through if it is a value of a function type and
    a "(" follows: it becomes the callee."""
    i = reg.depth - 1
    if lex.tok == lex.T_LPAREN and reg.op_kind[i] != reg.O_FUNC and typetab.is_func(reg.op_type[i]):
        gen.through_pointer()


def call_value(line, col):
    """A call where a value is wanted, of the function whose operand is on top of the stack
    and whose name is at `line`, `col`. One that gives a value and a status needs `-> v` after
    it, which stores the value and leaves the status."""
    global passed
    f = reg.op_var[reg.depth - 1]
    if lex.tok != lex.T_LPAREN:
        err.fatal(err.E_LPAREN_EXPECTED)
    err.position(line, col)
    check_not_pending(f)
    here()
    call(True)
    if lex.tok == lex.T_ARROW:
        if kernel.byte_of(f, kernel.C_RESULTS) != 2:
            err.fatal(err.E_RESULTS)
        lex.next()
        line = lex.line
        col = lex.col
        designator()
        target(line, col)
        err.position(line, col)
        gen.store_arrow()
        here()
    elif kernel.byte_of(f, kernel.C_RESULTS) == 2 and passing:
        passed = gen.mark()
    elif kernel.byte_of(f, kernel.C_RESULTS) == 0:
        err.position(line, col)
        err.fatal(err.E_RESULTS)        # a status beside a value may be ignored: v = f()


# ---- Expressions -------------------------------------------------------------------------

def conversion(t, line, col):
    """"(" expression ")" after typeKw, or after "^" type: a conversion to type `t`."""
    lex.expect(lex.T_LPAREN, err.E_LPAREN_EXPECTED)
    expression()
    err.position(line, col)
    gen.convert(t)
    here()
    lex.expect(lex.T_RPAREN, err.E_RPAREN_EXPECTED)


def primary():
    """primary = number | string | "(" expression ")" | typeKw "(" expression ")"
    | "^" type "(" expression ")" | designator [ arguments [ "->" designator ] ]. Pushes its
    operand."""
    if lex.tok == lex.T_NUMBER:
        gen.constant(typetab.NUMBER_TYPE, lex.value)
        lex.next()
        return
    if lex.tok == lex.T_LPAREN:
        lex.next()
        expression()
        lex.expect(lex.T_RPAREN, err.E_RPAREN_EXPECTED)
        return
    line = lex.line
    col = lex.col
    if lex.tok == lex.T_NAME:
        designator()
        callee()
        if reg.op_kind[reg.depth - 1] == reg.O_FUNC:
            call_value(line, col)
    elif lex.tok == lex.T_CARET:
        conversion(type_spec(), line, col)
    elif parts.basic_type(lex.tok) != typetab.NO_TYPE:
        t = parts.basic_type(lex.tok)
        lex.next()
        conversion(t, line, col)
    elif lex.tok == lex.T_STRING:
        parts.string()
        lex.next()
    elif lex.tok == lex.T_LBRACKET:
        err.fatal(err.E_UNSUPPORTED)
    else:
        err.fatal(err.E_EXPR_EXPECTED)


def factor():
    """factor = ( "-" | "~" ) factor | "@" designator | primary."""
    if lex.tok != lex.T_MINUS and lex.tok != lex.T_TILDE and lex.tok != lex.T_ADDRESS:
        primary()
        return
    line = lex.line
    col = lex.col
    if lex.tok == lex.T_MINUS or lex.tok == lex.T_TILDE:
        minus = lex.tok == lex.T_MINUS
        lex.next()
        nest()
        factor()
        unnest()
        err.position(line, col)
        if minus:
            gen.negate()
        else:
            gen.complement()
        here()
    else:
        lex.next()
        outer = gen.address_of
        gen.address_of = reg.depth
        designator()
        gen.address_of = outer
        err.position(line, col)
        i = reg.depth - 1
        if reg.op_kind[i] == reg.O_FUNC and kernel.flags_of(reg.op_var[i]) & inline.SF_INTERRUPT != 0:
            gen.code_address(reg.op_var[i])     # a ^byte, never a value of a function type
        elif reg.op_kind[i] == reg.O_FUNC and kernel.flags_of(reg.op_var[i]) & inline.SF_INLINE != 0:
            err.fatal(err.E_INLINE_ADDRESS)
        elif reg.op_kind[i] == reg.O_FUNC:
            gen.function_address()
        else:
            gen.address()
        here()


def term():
    """term = factor { ( "*" | "/" | "mod" | "&" | "<<" | ">>" ) factor }."""
    factor()
    op = parts.term_operator(lex.tok)
    while op != 0:
        line = lex.line
        col = lex.col
        lex.next()
        factor()
        parts.apply(op, line, col)
        op = parts.term_operator(lex.tok)


def addition():
    """sum = term { ( "+" | "-" | "|" | "^" ) term }."""
    term()
    op = parts.sum_operator(lex.tok)
    while op != 0:
        line = lex.line
        col = lex.col
        lex.next()
        term()
        parts.apply(op, line, col)
        op = parts.sum_operator(lex.tok)


def relation():
    """relation = sum [ ( "==" | "!=" | "<" | "<=" | ">" | ">=" ) sum ]."""
    addition()
    op = parts.relation_operator(lex.tok)
    if op != 0:
        line = lex.line
        col = lex.col
        lex.next()
        gen.as_value()             # a `bool` on the left cannot wait in the flags
        addition()
        parts.apply(op, line, col)


def inverse():
    """notExpr = "not" notExpr | relation."""
    if lex.tok != lex.T_NOT:
        relation()
        return
    line = lex.line
    col = lex.col
    lex.next()
    nest()
    inverse()
    unnest()
    err.position(line, col)
    gen.invert()
    here()


def both():
    """andExpr = notExpr { "and" notExpr }. The right side is reached only if the left is true."""
    inverse()
    while lex.tok == lex.T_AND:
        line = lex.line
        col = lex.col
        lex.next()
        parts.test_operator(True, line, col, True)
        inverse()
        parts.test_operator(True, line, col, False)


def expression():
    """expression = andExpr { "or" andExpr }. Its operand is left on GEN's stack: a constant,
    a variable, a value in the registers, a Condition, or GEN's pending operation."""
    nest()
    both()
    while lex.tok == lex.T_OR:
        line = lex.line
        col = lex.col
        lex.next()
        parts.test_operator(False, line, col, True)
        both()
        parts.test_operator(False, line, col, False)
    unnest()


def results_expression():
    """An expression after `return` in a function that gives a value and a status: a call
    that gives both may be all of it. `passed` then tells where that call ended."""
    global passing, passed
    passed = reg.NONE
    passing = True
    expression()
    passing = False


# ---- Constants ---------------------------------------------------------------------------

def constant(t):
    """constExpr: an expression that is known now, a number or an address. Unless `t` is
    typetab.NO_TYPE it must be one a `t` can be given, and takes that type. The constant is
    left on the stack."""
    line = lex.line
    col = lex.col
    expression()
    err.position(line, col)
    gen.as_value()
    if reg.op_kind[reg.depth - 1] != reg.O_CONST and reg.op_kind[reg.depth - 1] != reg.O_ADDR:
        err.fatal(err.E_NOT_CONST)
    if t != typetab.NO_TYPE:
        reg.assignable(reg.depth - 1, t)
    here()


def constant_number():
    """constExpr where a number that is not below zero is wanted, as for an address. Returns
    its value."""
    line = lex.line
    col = lex.col
    constant(typetab.NO_TYPE)
    i = reg.depth - 1
    err.position(line, col)
    if reg.op_kind[i] != reg.O_CONST:
        err.fatal(err.E_NOT_CONST)
    if reg.op_type[i] == typetab.BOOL_TYPE:
        err.fatal(err.E_TYPE)
    if typetab.is_signed(reg.op_type[i]) and reg.op_value[i] >= 0x8000:
        err.fatal(err.E_RANGE)
    here()
    reg.pop()
    return reg.op_value[i]


# ======== STMT: statements and control flow ===============================================

# Where a variable is declared
LEVEL_MODULE = 0
LEVEL_LOCAL = 1         # in a function: a slot of its frame
LEVEL_STATIC = 2        # in a function, but it lives for the whole program

function = 0            # the function being compiled: its symbol in the kernel's table
asm_last = False        # the statement compiled last is an `asm` block
exit_label = reg.NONE   # where `break` goes: after the nearest loop
next_label = reg.NONE   # where `continue` goes: to that loop's next pass
critical_depth = 0      # how many `critical` blocks the statement being compiled is inside
critical_inner = 0      # how many of those are inside the nearest loop
# `with REGION do ... end` (provisional, 2026-11-14): the temporaries that hold the bank found
# when the outermost `with` block of the function, and the outermost inside the nearest loop,
# mapped theirs; fbuf.NO_SLOT for none. Unmapping it puts back what was there before them all.
with_function = fbuf.NO_SLOT
with_loop = fbuf.NO_SLOT
data_region = 0         # the region of the table table_data() writes, or 0

MAX_CASE = 256
case_value = bytearray(MAX_CASE)    # the constants of the `case` statements being compiled
case_count = 0

OP_PHP = 0x08
OP_SEI = 0x78


# ---- Variables ---------------------------------------------------------------------------

def placements():
    """{ "zp" | "nozp" | "rows" | "at" constExpr | "in" name }. Returns them as symbol flags;
    the address is left in `parts.placed_at`, the region in `parts.placed_region`."""
    flags = 0
    while True:
        if lex.tok == lex.T_ZP:
            flags = flags | kernel.SF_ZP
            lex.next()
        elif lex.tok == lex.T_NOZP:
            flags = flags | kernel.SF_NOZP
            lex.next()
        elif lex.tok == lex.T_AT:
            flags = flags | kernel.SF_AT
            lex.next()
            parts.placed_at = constant_number()
        elif lex.tok == lex.T_ROWS:
            flags = flags | kernel.SF_ROWS
            lex.next()
        elif lex.tok == lex.T_IN:
            flags = flags | kernel.SF_IN
            parts.placed_region = parts.region_name()
        else:
            break
    if flags & kernel.SF_ZP != 0 and flags & kernel.SF_NOZP != 0:
        err.fatal(err.E_SYNTAX)
    return flags


def initial_assignment(s):
    """"=" expression after a local's declaration: an assignment made on every entry."""
    parts.push_variable(s)
    line = lex.line
    col = lex.col
    expression()
    err.position(line, col)
    gen.store()
    here()


def variable(more, level):
    """varDecl = "var" name ":" type { placement } [ "=" initialiser ], from "var" on.
    `more` is kernel.SF_PUB or 0."""
    lex.next()
    scope = inline.local_scope()
    if level == LEVEL_MODULE:
        scope = kernel.SCOPE_MODULE
    name = parts.new_name(scope)
    lex.expect(lex.T_COLON, err.E_COLON_EXPECTED)
    line = lex.line
    col = lex.col
    t = type_spec()
    flags = placements() | more
    if flags & kernel.SF_IN != 0:
        # In a region: in its bank, never in zero page, with no initial value, and not a slot.
        if flags & (kernel.SF_AT | kernel.SF_ZP) != 0 or level == LEVEL_LOCAL or lex.tok == lex.T_ASSIGN:
            parts.not_in_region()
        flags = flags | kernel.SF_NOZP
    err.position(line, col)
    if flags & kernel.SF_ROWS != 0:
        if not typetab.is_array(t):
            err.fatal(err.E_TYPE)
        t = typetab.array_of(typetab.base(t), typetab.length(t), True)
    parts.layout(t)
    if (typetab.is_array(t) or typetab.is_record(t)) and flags & kernel.SF_ZP == 0:
        flags = flags | kernel.SF_NOZP          # nor a record: never in zero page unless asked
    here()
    if level == LEVEL_LOCAL and flags & kernel.SF_AT == 0:
        s = kernel.sym_add(scope, name, kernel.K_LOCAL)
        kernel.set_byte(s, kernel.C_TYPE, t)
        if inline.level == 0:
            kernel.set_word(s, kernel.C_VALUE, reg.new_slot(typetab.size(t), parts.zp_class(flags), reg.SLOT_LOCAL, name))
        elif parts.zp_class(flags) != reg.CLASS_EITHER:
            kernel.set_word(s, kernel.C_VALUE, reg.new_slot(typetab.size(t), parts.zp_class(flags), reg.SLOT_LOCAL,
                                               inline.slot_name(name, reg.local_count)))
        else:
            # A local of an inline function: a temporary of the caller's frame, free again when
            # the expansion ends; one that must be in zero page, or must not (an array, a
            # record), is a slot of its own, since temporaries share theirs.
            kernel.set_word(s, kernel.C_VALUE, inline.own_slot(typetab.size(t)))
    else:
        if level == LEVEL_MODULE:
            s = parts.lasting_variable(scope, name, t, flags, 0)
        else:
            s = parts.lasting_variable(scope, name, t, flags, kernel.word_of(function, kernel.C_NAME))
    if lex.tok == lex.T_ASSIGN:
        initial_value(s, t, level)


def initial_value(s, t, level):
    """"=" initialiser after the declaration of variable `s` of type `t`, at `level`."""
    lex.next()
    parts.no_record(t)
    if typetab.is_array(t):
        data = gen.anonymous()
        table_data(t, data)
        if level == LEVEL_LOCAL:
            parts.push_variable(s)
            gen.copy_array(data, typetab.size(t))
            reg.pop()
        else:
            gen.initial(s, data, 0, 0)
    elif level == LEVEL_LOCAL:
        initial_assignment(s)
    else:
        constant(t)
        i = reg.depth - 1
        if reg.op_kind[i] == reg.O_ADDR:
            gen.initial(s, reg.op_symbol[i], reg.op_slot[i], reg.op_value[i])
        else:
            gen.initial(s, kernel.NO_OBJ, 0, reg.op_value[i])
        reg.pop()


def table_data(t, symbol):
    """initialiser = "[" constExpr { "," constExpr } "]", or a string, for an array of type
    `t`: write it as the constant data `symbol`, laid out as the array is. Elements not given
    are 0; a string fills a byte array and is followed by a zero if there is room."""
    n = typetab.length(t)
    e = typetab.base(t)
    total = typetab.size(t)
    spacing = typetab.size(e)           # how far apart the elements start; their bytes: step
    step = 1
    if typetab.is_column(t):
        spacing = 1
        step = n
    if typetab.is_array(e):
        err.fatal(err.E_UNSUPPORTED)
    out.table_begin(total)
    if lex.tok == lex.T_STRING:
        if e != typetab.BYTE_TYPE:
            err.fatal(err.E_TYPE)
        if lex.string_length > n:
            err.fatal(err.E_TOO_MANY)
        for i in range(0, lex.string_length):
            out.table_byte(i, lex.string_byte(i))
        lex.next()
    else:
        lex.expect(lex.T_LBRACKET, err.E_SYNTAX)
        count = 0
        while True:
            if count == n:
                err.fatal(err.E_TOO_MANY)
            constant(e)
            gen.table_element(count * spacing, step)
            count += 1
            if lex.tok != lex.T_COMMA:
                break
            lex.next()
        lex.expect(lex.T_RBRACKET, err.E_SYNTAX)
    if data_region != 0:
        out.region(data_region)
    out.table_end(symbol, total)


# ---- Assignments and calls ---------------------------------------------------------------

def assignment(line, col):
    """assignOp expression, after the designator at `line`, `col`."""
    target(line, col)
    token = lex.tok
    lex.next()
    line = lex.line
    col = lex.col
    expression()
    err.position(line, col)
    if token == lex.T_ASSIGN:
        gen.store()
    else:
        gen.assign(token - lex.T_PLUS_ASSIGN + fold.ADD)
    here()


def pair_assignment(line, col):
    """"," designator "=" call, after the designator at `line`, `col`: the value and the
    status of a call that gives both."""
    target(line, col)
    lex.next()
    line = lex.line
    col = lex.col
    designator()
    target(line, col)
    lex.expect(lex.T_ASSIGN, err.E_SYNTAX)
    line = lex.line
    col = lex.col
    designator()
    callee()
    i = reg.depth - 1
    if reg.op_kind[i] != reg.O_FUNC or kernel.byte_of(reg.op_var[i], kernel.C_RESULTS) != 2:
        err.position(line, col)
        err.fatal(err.E_RESULTS)
    if lex.tok != lex.T_LPAREN:
        err.fatal(err.E_LPAREN_EXPECTED)
    call(True)
    err.position(line, col)
    gen.store_pair()
    here()


def name_statement():
    """designator ( assignOp expression | "," designator "=" call | arguments ): the token
    after the designator says which."""
    line = lex.line
    col = lex.col
    designator()
    callee()
    if reg.op_kind[reg.depth - 1] == reg.O_FUNC:
        if lex.tok != lex.T_LPAREN:
            err.fatal(err.E_LPAREN_EXPECTED)
        err.position(line, col)
        check_not_pending(reg.op_var[reg.depth - 1])   # in an inline body, inside arguments
        here()
        call(False)                # a call used as a statement may ignore its results
    elif lex.tok == lex.T_LPAREN:
        err.fatal(err.E_NOT_FUNC)
    elif lex.tok == lex.T_COMMA:
        pair_assignment(line, col)
    elif lex.tok >= lex.T_ASSIGN and lex.tok <= lex.T_SHR_ASSIGN:
        assignment(line, col)
    else:
        err.fatal(err.E_SYNTAX)


# ---- Control flow ------------------------------------------------------------------------

def test():
    """An expression used as a test: goes on when it is true. Returns the label gone to when
    it is false."""
    line = lex.line
    col = lex.col
    expression()
    err.position(line, col)
    target = gen.jump_false()
    here()
    return target


def end_of_block():
    if lex.tok != lex.T_END:
        err.fatal(err.E_END_EXPECTED)
    lex.next()


def if_statement():
    """"if" expression "then" NL body { "elif" expression "then" NL body } [ "else" NL body ]
    "end". Each part but the last ends with a JMP to the end, unless it cannot be run off."""
    done = reg.NONE
    while True:
        lex.next()
        skip = test()
        lex.expect(lex.T_THEN, err.E_THEN_EXPECTED)
        line_end()
        body()
        if lex.tok != lex.T_ELIF and lex.tok != lex.T_ELSE:
            reg.label(skip)
            break
        if fbuf.runs_on():
            if done == reg.NONE:
                done = fbuf.new_label()
            reg.jump(done)
        reg.label(skip)
        if lex.tok == lex.T_ELSE:
            lex.next()
            line_end()
            body()
            break
    end_of_block()
    if done != reg.NONE:
        reg.label(done)


def while_statement():
    """"while" expression "do" NL body "end"."""
    global exit_label, next_label, critical_inner, with_loop
    saved_exit = exit_label
    saved_next = next_label
    saved_inner = critical_inner
    critical_inner = 0
    saved_with = with_loop
    with_loop = fbuf.NO_SLOT
    lex.next()
    top = fbuf.new_label()
    reg.loop_label(top)
    gen.loop_begin()
    exit_label = test()
    next_label = top
    lex.expect(lex.T_DO, err.E_DO_EXPECTED)
    line_end()
    body()
    end_of_block()
    if fbuf.runs_on():
        reg.jump(top)
    reg.label(exit_label)
    gen.loop_end()
    exit_label = saved_exit
    next_label = saved_next
    critical_inner = saved_inner
    with_loop = saved_with


def loop_statement():
    """"loop" NL body ( "end" | "until" expression ). `continue` goes to the test of `until`,
    or to the top if there is none."""
    global exit_label, next_label, critical_inner, with_loop
    saved_exit = exit_label
    saved_next = next_label
    saved_inner = critical_inner
    critical_inner = 0
    saved_with = with_loop
    with_loop = fbuf.NO_SLOT
    lex.next()
    line_end()
    top = fbuf.new_label()
    reg.loop_label(top)
    gen.loop_begin()
    exit_label = fbuf.new_label()
    next_label = fbuf.new_label()
    body()
    if lex.tok == lex.T_UNTIL:
        lex.next()
        reg.label(next_label)
        reg.join(top, test())          # when the test is false: round again
    else:
        end_of_block()
        reg.join(top, next_label)
        if fbuf.runs_on():
            reg.jump(top)
    reg.label(exit_label)
    gen.loop_end()
    exit_label = saved_exit
    next_label = saved_next
    critical_inner = saved_inner
    with_loop = saved_with


def limit_value(t):
    """The expression after "to" or "downto", for a loop variable of type `t`: left on the
    stack as a constant or a variable, which is a temporary unless it was one already."""
    line = lex.line
    col = lex.col
    expression()
    gen.resolve(True)
    err.position(line, col)
    reg.assignable(reg.depth - 1, t)
    if reg.in_registers(reg.depth - 1):
        reg.spill(reg.depth - 1)
    here()


def for_statement():
    """"for" name "=" expression ( "to" | "downto" | "until" ) expression "do" NL body "end".
    The variable is set to the first value, the loop is skipped if that is past the limit, and
    the test is at the bottom: the variable is compared with the limit before each step
    (docs/codegen.md, "Statements"). With `until` the test, variable < limit, is at the top
    instead. A limit that is a variable is not copied: it is read at each test."""
    global exit_label, next_label, critical_inner, with_loop
    nest()
    saved_exit = exit_label
    saved_next = next_label
    saved_inner = critical_inner
    critical_inner = 0
    saved_with = with_loop
    with_loop = fbuf.NO_SLOT
    lex.next()
    s = parts.loop_variable()
    t = kernel.type_of(s)
    lex.expect(lex.T_ASSIGN, err.E_SYNTAX)
    parts.push_variable(s)
    line = lex.line
    col = lex.col
    expression()
    err.position(line, col)
    known = gen.pend_op == 0 and reg.op_kind[reg.depth - 1] == reg.O_CONST
    if known:
        reg.assignable(reg.depth - 1, t)
    first = reg.op_value[reg.depth - 1]
    gen.store()
    here()
    if lex.tok != lex.T_TO and lex.tok != lex.T_DOWNTO and lex.tok != lex.T_UNTIL:
        err.fatal(err.E_TO_EXPECTED)
    down = lex.tok == lex.T_DOWNTO
    exclusive = lex.tok == lex.T_UNTIL
    lex.next()
    limit_value(t)
    limit = reg.depth - 1
    lex.expect(lex.T_DO, err.E_DO_EXPECTED)
    line_end()
    op = fold.LE
    if down:
        op = fold.GE
    top = fbuf.new_label()
    if exclusive:
        reg.loop_label(top)             # `until`: the test is at the top
        parts.push_variable(s)
        exit_label = parts.compare_limit(limit, fold.LT)
    else:
        if known:
            gen.constant(t, first)      # a constant first value can make the test known
        else:
            parts.push_variable(s)
        exit_label = parts.compare_limit(limit, op)
        reg.loop_label(top)
    gen.loop_begin()
    next_label = fbuf.new_label()
    body()
    end_of_block()
    reg.label(next_label)
    if not exclusive:
        parts.push_variable(s)
        reg.join(exit_label, parts.compare_limit(limit, fold.NE))
    parts.step_back(s, down, limit, top)
    gen.loop_end()
    reg.label(exit_label)
    reg.pop()
    exit_label = saved_exit
    next_label = saved_next
    critical_inner = saved_inner
    with_loop = saved_with
    unnest()


def case_constants(selector, chosen, base):
    """constExpr { "," constExpr }: compare the selector, operand `selector`, with each, and
    go to `chosen` if it is equal to one. Returns the label gone to if it is equal to none."""
    global case_count
    while True:
        line = lex.line
        col = lex.col
        constant(reg.op_type[selector])
        value = reg.op_value[reg.depth - 1] & 0xFF
        reg.pop()
        for n in range(base, case_count):
            if case_value[n] == value:
                err.position(line, col)
                err.fatal(err.E_CASE_TWICE)
        if case_count == MAX_CASE:
            err.fatal(err.E_LABELS_FULL)
        case_value[case_count] = value
        case_count += 1
        reg.load(reg.A, selector, 0)
        if value == 0:
            reg.test(reg.A)             # no CMP just after the load
        else:
            reg.compare_const(value)
        if lex.tok != lex.T_COMMA:
            break
        lex.next()
        reg.branch(gen.OP_BEQ, chosen)
    other = fbuf.new_label()
    reg.branch(gen.OP_BNE, other)
    return other


def case_statement():
    """"case" expression NL { "of" constExpr { "," constExpr } NL body } [ "else" NL body ]
    "end". The selector is compared with the constants of each `of` in turn: it is a variable,
    or is stored in a temporary, so that it can be loaded again (docs/codegen.md,
    "Statements"). A variable at a fixed address may be a device, and is read once; an
    element is copied too, so that the register memory knows A holds it."""
    global case_count
    lex.next()
    line = lex.line
    col = lex.col
    expression()
    err.position(line, col)
    gen.as_value()
    selector = reg.depth - 1
    t = reg.op_type[selector]
    if typetab.size(t) != 1 or typetab.is_untyped(t):
        err.fatal(err.E_CASE_SELECTOR)
    if reg.op_kind[selector] == reg.O_VAR and (reg.op_symbol[selector] == kernel.NO_OBJ
                                               or not reg.is_direct(selector)):
        reg.release(selector)
        reg.load(reg.A, selector, 0)
        reg.become(selector, reg.O_A, t)
    if reg.in_registers(selector):
        reg.spill(selector)
    here()
    line_end()
    done = fbuf.new_label()
    base = case_count
    while lex.tok == lex.T_OF:
        lex.next()
        chosen = fbuf.new_label()
        other = case_constants(selector, chosen, base)
        line_end()
        reg.label(chosen)               # the selector is in A on every way in
        body()
        if lex.tok == lex.T_END:
            reg.label(other)            # the body runs on to here: A may hold anything
        else:
            if fbuf.runs_on():
                reg.jump(done)
            reg.label(other)
    if lex.tok == lex.T_ELSE:
        lex.next()
        line_end()
        body()
    end_of_block()
    reg.label(done)
    reg.pop()
    case_count = base


def critical_statement():
    """"critical" NL body "end": PHP and SEI, the body, PLP. `break`, `continue` and `return`
    that leave the block restore the flags first (docs/codegen.md, "Statements")."""
    global critical_depth, critical_inner
    lex.next()
    line_end()
    fbuf.op(OP_PHP)
    fbuf.op(OP_SEI)
    critical_depth += 1
    critical_inner += 1
    body()
    end_of_block()
    critical_depth -= 1
    critical_inner -= 1
    parts.restore_flags(1)


def with_statement():
    """"with" name "do" NL body "end" (provisional, 2026-11-14): inside it the variables and
    tables `in` that region can be used. Its bank is mapped at the start and the bank found
    there put back at the end, and by a `return`, `break` or `continue` that leaves it. A block
    inside a block of the same region costs nothing; one of another region maps its own, and
    the outer region's names cannot be used in it."""
    global with_function, with_loop
    line = lex.line
    col = lex.col
    if kernel.flags_of(function) & inline.SF_INTERRUPT != 0:
        err.fatal(err.E_WITH_INTERRUPT)
    if inline.level > 0:
        err.fatal(err.E_INLINE_NOT_HERE)
    lex.next()
    if lex.tok != lex.T_NAME:
        err.fatal(err.E_NAME_EXPECTED)
    region = lex.value
    lex.next()
    lex.expect(lex.T_DO, err.E_DO_EXPECTED)
    line_end()
    outer_region = out.with_region
    outer_used = out.with_used
    saved_function = with_function
    saved_loop = with_loop
    temp = fbuf.NO_SLOT
    entry = reg.NONE
    if not reg.same_region(region, outer_region):
        temp = parts.map_bank()
        entry = parts.with_entry
        if with_function == fbuf.NO_SLOT:
            with_function = temp
        if with_loop == fbuf.NO_SLOT:
            with_loop = temp
    out.with_region = region
    out.with_used = kernel.NO_OBJ
    body()
    end_of_block()
    used = out.with_used
    out.with_region = outer_region
    out.with_used = outer_used
    if temp != fbuf.NO_SLOT:
        if used == kernel.NO_OBJ:
            used = parts.region_symbol(region)
        if used == kernel.NO_OBJ:
            err.position(line, col)
            err.fatal(err.E_WITH_UNKNOWN)
        if entry != reg.NONE:
            fbuf.set_symbol(entry, used)
        parts.unmap_bank(temp)
        reg.slot_busy[temp] = False
    elif outer_used == kernel.NO_OBJ:
        out.with_used = used
    with_function = saved_function
    with_loop = saved_loop


def directive():
    """"#if" constExpr NL. LEX passes over what is not to be compiled. The condition is a
    `bool`, or a number, which is true unless it is 0 (docs/language.md, "Conditional
    compilation")."""
    lex.next()
    line = lex.line
    col = lex.col
    constant(typetab.NO_TYPE)
    i = reg.depth - 1
    err.position(line, col)
    if not typetab.is_number(reg.op_type[i]) and not typetab.is_untyped(reg.op_type[i]) \
            and reg.op_type[i] != typetab.BOOL_TYPE:
        err.fatal(err.E_TYPE)
    reg.pop()
    here()
    if lex.tok != lex.T_NL:
        err.fatal(err.E_NL_EXPECTED)
    err.position(line, col)
    lex.choose(reg.op_value[i] != 0)


def jump_statement(target):
    """"break" or "continue": a JMP to `target`, the label the nearest loop has for it, after
    leaving the `critical` blocks inside that loop."""
    if target == reg.NONE:
        err.fatal(err.E_NO_LOOP)
    lex.next()
    parts.restore_flags(critical_inner)
    if with_loop != fbuf.NO_SLOT:
        parts.unmap_bank(with_loop)
    reg.jump(target)


def status():
    """An expression whose value is returned in the carry flag."""
    line = lex.line
    col = lex.col
    gen.carry_wanted()
    expression()
    err.position(line, col)
    gen.carry()
    here()


def passes_on(t):
    """True if the expression just parsed is nothing but a call that gives a value of type
    `t` and a status: both are then where this function's own results must be."""
    i = reg.depth - 1
    return lex.tok == lex.T_NL and gen.mark() == passed and reg.in_registers(i) \
        and reg.op_type[i] == t


def value_and_status(t):
    """expression "," expression after "return", or a call that gives both results."""
    line = lex.line
    col = lex.col
    results_expression()
    if passed != reg.NONE:
        if not passes_on(t):
            err.position(line, col)
            err.fatal(err.E_RESULTS)
        reg.pop()
        return
    err.position(line, col)
    gen.accept(t)
    here()
    lex.expect(lex.T_COMMA, err.E_RESULTS)
    status()                            # may need A: the value waits where it is
    gen.load_result()


def return_statement():
    """"return" [ expression [ "," expression ] ], as the function's results require. The
    value goes to A, or A and X, and a `bool` to the carry flag."""
    results = kernel.byte_of(function, kernel.C_RESULTS)
    first = kernel.word_of(function, kernel.C_MEMBERS) + kernel.params_of(function)
    if critical_depth > 0 and results > 0 and kernel.member_value_of(first + results - 1) == gen.REG_C:
        err.fatal(err.E_STATUS_IN_CRITICAL)     # PLP would change the carry flag
    lex.next()
    if (results == 0) != (lex.tok == lex.T_NL):
        err.fatal(err.E_RESULTS)
    # In an expansion, the value may stay the operand it is (inline.leaves_operand()); if not,
    # it goes where a call leaves it, and the `return` is a jump to the expansion's end.
    keep = inline.level > 0 and inline.leaves_operand()
    t = kernel.member_type_of(first)
    line = lex.line
    col = lex.col
    if results == 2:
        value_and_status(t)
    elif results == 1 and kernel.member_value_of(first) == gen.REG_C and not keep:
        status()
    elif results == 1:
        expression()
        err.position(line, col)
        if not keep or gen.pend_op == 0 or gen.pend_type != t:
            gen.accept(t)
        here()
        if not keep and t != typetab.BOOL_TYPE:
            gen.load_result()
    parts.restore_flags(critical_depth)
    if with_function != fbuf.NO_SLOT:
        parts.unmap_bank(with_function)
    if keep:
        inline.lazy[inline.level] = True
    elif inline.level > 0:
        reg.jump(inline.done[inline.level])
    else:
        gen.ret()


def statement():
    global asm_last
    asm_last = lex.tok == lex.T_ASM
    if lex.tok == lex.T_NAME:
        name_statement()
    elif lex.tok == lex.T_RETURN:
        return_statement()
    elif lex.tok == lex.T_IF:
        if_statement()
    elif lex.tok == lex.T_WHILE:
        while_statement()
    elif lex.tok == lex.T_LOOP:
        loop_statement()
    elif lex.tok == lex.T_BREAK:
        jump_statement(exit_label)
    elif lex.tok == lex.T_CONTINUE:
        jump_statement(next_label)
    elif lex.tok == lex.T_VAR:
        variable(0, LEVEL_LOCAL)
    elif lex.tok == lex.T_STATIC:
        lex.next()
        if lex.tok != lex.T_VAR:
            err.fatal(err.E_SYNTAX)
        variable(0, LEVEL_STATIC)
    elif lex.tok == lex.T_ASM:
        asmblock.block()
    elif lex.tok == lex.T_FOR:
        for_statement()
    elif lex.tok == lex.T_CASE:
        case_statement()
    elif lex.tok == lex.T_CRITICAL:
        critical_statement()
    elif lex.tok == lex.T_WITH:
        with_statement()
    elif lex.tok == lex.T_HASH_IF:
        directive()
    else:
        err.fatal(err.E_STMT_EXPECTED)
    line_end()


def ends_body(token):
    """True for the tokens that end a body; which of them is right is for the caller to check."""
    return token == lex.T_END or token == lex.T_EOF or token == lex.T_ELIF or token == lex.T_ELSE \
        or token == lex.T_UNTIL or token == lex.T_OF


def body():
    """body = { varDecl | statement }."""
    nest()
    while not ends_body(lex.tok):
        statement()
    unnest()


def inline_argument(f, i):
    """The argument for parameter `i` of inline function `f`: a value it can be given, which
    INLINE makes the parameter's symbol of (inline.argument_symbol())."""
    line = lex.line
    col = lex.col
    expression()
    err.position(line, col)
    gen.as_value()
    gen.accept(kernel.member_type_of(kernel.word_of(f, kernel.C_MEMBERS) + i))
    inline.argument_symbol(f, i)
    here()


# What expand() keeps while an expansion's body is compiled, by inline.depth: in arrays and not
# in its locals, so that lathe/src/expr.lth's saving call of body() has nothing to push
EXPANSIONS = inline.MAX_DEPTH + 1
expand_line = [0] * EXPANSIONS          # where the ")" of the call is
expand_col = [0] * EXPANSIONS
expand_brackets = bytearray(EXPANSIONS) # lex.open_brackets there
expand_function = [0] * EXPANSIONS      # the caller's `function`, `exit_label` and the others
expand_exit = [0] * EXPANSIONS
expand_next = [0] * EXPANSIONS
expand_depth = bytearray(EXPANSIONS)
expand_inner = bytearray(EXPANSIONS)
expand_with_function = bytearray(EXPANSIONS)   # the caller's `with_function` and `with_loop`
expand_with_loop = bytearray(EXPANSIONS)


def inline_arguments(f):
    """The arguments and ")" of a call of inline function `f`, after its "("."""
    count = 0
    if lex.tok != lex.T_RPAREN:
        while True:
            if count == kernel.params_of(f):
                err.fatal(err.E_ARG_COUNT)
            inline_argument(f, count)
            count += 1
            if lex.tok != lex.T_COMMA:
                break
            lex.next()
    if lex.tok != lex.T_RPAREN:
        err.fatal(err.E_RPAREN_EXPECTED)
    if count != kernel.params_of(f):
        err.fatal(err.E_ARG_COUNT)


def expand():
    """The arguments and ")" of the newest inline call, which inline.enter() has begun, after its
    "(", and the body of its function, replayed from its saved tokens as if it were written here
    (docs/code-model.md, "Inline functions"). A `return` goes to the end of the expansion, where
    the result is left as a call leaves it, if it is wanted; or, from the last statement, it may
    leave its value as the operand it is. The token after the ")" is the current one at the end."""
    global function, exit_label, next_label, critical_depth, critical_inner, with_function, with_loop
    inline_arguments(inline.expanding[inline.depth])
    expand_line[inline.depth] = lex.line
    expand_col[inline.depth] = lex.col
    expand_brackets[inline.depth] = lex.open_brackets
    expand_function[inline.depth] = function
    expand_exit[inline.depth] = exit_label
    expand_next[inline.depth] = next_label
    expand_depth[inline.depth] = critical_depth
    expand_inner[inline.depth] = critical_inner
    expand_with_function[inline.depth] = with_function
    expand_with_loop[inline.depth] = with_loop
    function = inline.expanding[inline.depth]
    exit_label = reg.NONE
    next_label = reg.NONE
    critical_depth = 0
    critical_inner = 0
    with_function = fbuf.NO_SLOT        # its `return` is a jump inside the caller's blocks
    with_loop = fbuf.NO_SLOT
    lex.open_brackets = 0
    inline.body_begin(function)
    lex.next()
    body()
    if lex.tok != lex.T_EOF:
        err.fatal(err.E_END_EXPECTED)
    src.close()
    function = expand_function[inline.depth]
    exit_label = expand_exit[inline.depth]
    next_label = expand_next[inline.depth]
    critical_depth = expand_depth[inline.depth]
    critical_inner = expand_inner[inline.depth]
    with_function = expand_with_function[inline.depth]
    with_loop = expand_with_loop[inline.depth]
    lex.open_brackets = expand_brackets[inline.depth]
    lex.resume(lex.T_RPAREN, expand_line[inline.depth], expand_col[inline.depth])
    if not inline.lazy[inline.depth]:
        reg.label(inline.done[inline.depth])
        if inline.wanted[inline.depth]:
            gen.result(inline.expanding[inline.depth])
    inline.leave()
    lex.next()


def function_body(f):
    """The body of function `f`, whose parameters are declared. If `f` has a result, its end
    must not be reached: the code before it returns or jumps, or it is an `asm` block, which
    the programmer has made return by itself."""
    global function, exit_label, next_label, critical_depth, critical_inner, asm_last, \
        with_function, with_loop
    function = f
    exit_label = reg.NONE
    next_label = reg.NONE
    critical_depth = 0
    critical_inner = 0
    with_function = fbuf.NO_SLOT
    with_loop = fbuf.NO_SLOT
    asm_last = False
    body()
    if kernel.byte_of(f, kernel.C_RESULTS) != 0 and fbuf.runs_on() and not asm_last:
        err.fatal(err.E_NO_RETURN)
