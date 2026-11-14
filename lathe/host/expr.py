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


def init():
    global passing, passed, pending_count
    passing = False
    passed = reg.NONE
    pending_count = 0


# ---- Types and names ---------------------------------------------------------------------

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
    t = basic_type(lex.tok)
    line = lex.line
    col = lex.col
    if t != typetab.NO_TYPE:
        lex.next()
    elif lex.tok == lex.T_NAME:
        s = named_symbol()
        if kernel.sym_kind[s] != kernel.K_TYPE:
            err.position(line, col)
            err.fatal(err.E_TYPE_EXPECTED)
        t = kernel.sym_type[s]
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
    err.position(lex.line, lex.col)
    return t


def new_name(scope):
    """The name being declared, which `scope` must not have yet. It is passed over."""
    if lex.tok != lex.T_NAME:
        err.fatal(err.E_NAME_EXPECTED)
    name = lex.value
    _, found = kernel.sym_find(scope, name)
    if found:
        err.fatal(err.E_DUPLICATE)
    lex.next()
    return name


def named_symbol():
    """name [ "." name ]: the symbol a name means here, or module.name means in that module,
    which must export it (a type that it does not export is in its interface all the same)."""
    if lex.tok != lex.T_NAME:
        err.fatal(err.E_NAME_EXPECTED)
    s, found = inline.lookup(lex.value)
    if not found:
        err.fatal(err.E_UNDEFINED)
    lex.next()
    if kernel.sym_kind[s] == kernel.K_MODULE:
        scope = kernel.sym_value[s]
        lex.expect(lex.T_DOT, err.E_DOT_EXPECTED)
        if lex.tok != lex.T_NAME:
            err.fatal(err.E_NAME_EXPECTED)
        s, found = kernel.sym_find(scope, lex.value)
        if not found or kernel.sym_flags[s] & kernel.SF_PUB == 0:
            err.fatal(err.E_UNDEFINED)
        lex.next()
    return s


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
        err.position(lex.line, lex.col)
    lex.expect(lex.T_RPAREN, err.E_RPAREN_EXPECTED)


def designator():
    """designator = name { "." name | "[" expression "]" }. Pushes an operand for what it
    names. A named type followed by "(" is a conversion."""
    line = lex.line
    col = lex.col
    s = named_symbol()
    kind = kernel.sym_kind[s]
    if kind == kernel.K_FUNC:
        gen.function(s)
    elif kind == kernel.K_CONST and typetab.is_array(kernel.sym_type[s]):
        gen.table(s)
    elif kind == kernel.K_CONST:
        gen.constant(kernel.sym_type[s], kernel.sym_value[s])
    elif kind == kernel.K_LOCAL:
        gen.local(kernel.sym_type[s], kernel.sym_value[s])
    elif kind == kernel.K_VAR:
        gen.variable(s)
    elif kind == kernel.K_TYPE:
        conversion(kernel.sym_type[s], line, col)
    else:
        builtin(kernel.sym_value[s])
    while lex.tok == lex.T_LBRACKET or lex.tok == lex.T_DOT:
        line = lex.line
        col = lex.col
        if lex.tok == lex.T_DOT:
            lex.next()
            field(line, col)
        else:
            lex.next()
            expression()
            lex.expect(lex.T_RBRACKET, err.E_SYNTAX)
            err.position(line, col)
            gen.index()
            err.position(lex.line, lex.col)


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
    gen.field(kernel.sym_value[f], kernel.sym_type[f])
    lex.next()


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
    err.position(lex.line, lex.col)


def arguments(f):
    """[ expression { "," expression } ] ")", after the "(". Each argument goes straight to
    its parameter in the frame of function `f`, except those passed in registers (all of an
    `extern` or `asm` function's), which stay on the stack, in order, for GEN to load at the call."""
    global pending_count
    saved = gen.outer
    saved_pending = pending_count
    count = 0
    if lex.tok != lex.T_RPAREN:
        while True:
            if count == kernel.sym_params[f]:
                err.fatal(err.E_ARG_COUNT)
            by_register = gen.in_register(f, count)
            if not by_register:
                gen.parameter(f, count)
            argument(kernel.member_type[kernel.sym_members[f] + count], not by_register)
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
    if count != kernel.sym_params[f]:
        err.fatal(err.E_ARG_COUNT)
    pending_count = saved_pending
    gen.arguments_end(saved)
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
    if not gen.through(f) and kernel.sym_flags[f] & inline.SF_INTERRUPT != 0:
        err.fatal(err.E_INTERRUPT_CALL)
    if not gen.through(f) and kernel.sym_flags[f] & inline.SF_INLINE != 0:
        reg.pop()
        inline.enter(f, wanted)     # errors at the "("
        lex.next()
        saved = passing
        passing = False
        expand(f, wanted)
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
    err.position(lex.line, lex.col)
    call(True)
    if lex.tok == lex.T_ARROW:
        if kernel.sym_results[f] != 2:
            err.fatal(err.E_RESULTS)
        lex.next()
        line = lex.line
        col = lex.col
        designator()
        target(line, col)
        err.position(line, col)
        gen.store_arrow()
        err.position(lex.line, lex.col)
    elif kernel.sym_results[f] == 2 and passing:
        passed = gen.mark()
    elif kernel.sym_results[f] != 1:
        err.position(line, col)
        err.fatal(err.E_RESULTS)


# ---- Expressions -------------------------------------------------------------------------

def conversion(t, line, col):
    """"(" expression ")" after typeKw, or after "^" type: a conversion to type `t`."""
    lex.expect(lex.T_LPAREN, err.E_LPAREN_EXPECTED)
    expression()
    err.position(line, col)
    gen.convert(t)
    err.position(lex.line, lex.col)
    lex.expect(lex.T_RPAREN, err.E_RPAREN_EXPECTED)


def primary():
    """primary = number | string | "(" expression ")" | typeKw "(" expression ")"
    | "^" type "(" expression ")" | designator [ arguments [ "->" designator ] ]. Pushes its
    operand."""
    line = lex.line
    col = lex.col
    if lex.tok == lex.T_NUMBER:
        gen.constant(typetab.NUMBER_TYPE, lex.value)
        lex.next()
    elif lex.tok == lex.T_LPAREN:
        lex.next()
        expression()
        lex.expect(lex.T_RPAREN, err.E_RPAREN_EXPECTED)
    elif basic_type(lex.tok) != typetab.NO_TYPE:
        t = basic_type(lex.tok)
        lex.next()
        conversion(t, line, col)
    elif lex.tok == lex.T_CARET:
        conversion(type_spec(), line, col)
    elif lex.tok == lex.T_NAME:
        designator()
        callee()
        if reg.op_kind[reg.depth - 1] == reg.O_FUNC:
            call_value(line, col)
    elif lex.tok == lex.T_STRING:
        gen.string()
        lex.next()
    elif lex.tok == lex.T_LBRACKET:
        err.fatal(err.E_UNSUPPORTED)
    else:
        err.fatal(err.E_EXPR_EXPECTED)


def factor():
    """factor = ( "-" | "~" ) factor | "@" designator | primary."""
    line = lex.line
    col = lex.col
    if lex.tok == lex.T_MINUS or lex.tok == lex.T_TILDE:
        minus = lex.tok == lex.T_MINUS
        lex.next()
        factor()
        err.position(line, col)
        if minus:
            gen.negate()
        else:
            gen.complement()
        err.position(lex.line, lex.col)
    elif lex.tok == lex.T_ADDRESS:
        lex.next()
        designator()
        err.position(line, col)
        i = reg.depth - 1
        if reg.op_kind[i] == reg.O_FUNC and kernel.sym_flags[reg.op_var[i]] & inline.SF_INTERRUPT != 0:
            gen.code_address(reg.op_var[i])     # a ^byte, never a value of a function type
        elif reg.op_kind[i] == reg.O_FUNC and kernel.sym_flags[reg.op_var[i]] & inline.SF_INLINE != 0:
            err.fatal(err.E_INLINE_ADDRESS)
        elif reg.op_kind[i] == reg.O_FUNC:
            gen.function_address()
        else:
            gen.address()
        err.position(lex.line, lex.col)
    else:
        primary()


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


def term():
    """term = factor { ( "*" | "/" | "mod" | "&" | "<<" | ">>" ) factor }."""
    factor()
    op = term_operator(lex.tok)
    while op != 0:
        line = lex.line
        col = lex.col
        lex.next()
        factor()
        apply(op, line, col)
        op = term_operator(lex.tok)


def addition():
    """sum = term { ( "+" | "-" | "|" | "^" ) term }."""
    term()
    op = sum_operator(lex.tok)
    while op != 0:
        line = lex.line
        col = lex.col
        lex.next()
        term()
        apply(op, line, col)
        op = sum_operator(lex.tok)


def relation():
    """relation = sum [ ( "==" | "!=" | "<" | "<=" | ">" | ">=" ) sum ]."""
    addition()
    op = relation_operator(lex.tok)
    if op != 0:
        line = lex.line
        col = lex.col
        lex.next()
        gen.as_value()             # a `bool` on the left cannot wait in the flags
        addition()
        apply(op, line, col)


def inverse():
    """notExpr = "not" notExpr | relation."""
    if lex.tok != lex.T_NOT:
        relation()
        return
    line = lex.line
    col = lex.col
    lex.next()
    inverse()
    err.position(line, col)
    gen.invert()
    err.position(lex.line, lex.col)


def test_operator(wanted, line, col, is_left):
    """One side of the `and` (`wanted` True) or `or` (False) at `line`, `col` is complete."""
    err.position(line, col)
    if is_left:
        gen.test_left(wanted)
    else:
        gen.test_right()
    err.position(lex.line, lex.col)


def both():
    """andExpr = notExpr { "and" notExpr }. The right side is reached only if the left is true."""
    inverse()
    while lex.tok == lex.T_AND:
        line = lex.line
        col = lex.col
        lex.next()
        test_operator(True, line, col, True)
        inverse()
        test_operator(True, line, col, False)


def expression():
    """expression = andExpr { "or" andExpr }. Its operand is left on GEN's stack: a constant,
    a variable, a value in the registers, a Condition, or GEN's pending operation."""
    both()
    while lex.tok == lex.T_OR:
        line = lex.line
        col = lex.col
        lex.next()
        test_operator(False, line, col, True)
        both()
        test_operator(False, line, col, False)


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
    err.position(lex.line, lex.col)


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
    err.position(lex.line, lex.col)
    reg.pop()
    return reg.op_value[i]


# ======== STMT: statements and control flow ===============================================

# Where a variable is declared
LEVEL_MODULE = 0
LEVEL_LOCAL = 1         # in a function: a slot of its frame
LEVEL_STATIC = 2        # in a function, but it lives for the whole program

function = 0            # the function being compiled: its symbol in the kernel's table
exit_label = reg.NONE   # where `break` goes: after the nearest loop
next_label = reg.NONE   # where `continue` goes: to that loop's next pass
placed_at = 0           # the address after "at" in the declaration being parsed
critical_depth = 0      # how many `critical` blocks the statement being compiled is inside
critical_inner = 0      # how many of those are inside the nearest loop

MAX_CASE = 256
case_value = bytearray(MAX_CASE)    # the constants of the `case` statements being compiled
case_count = 0

OP_PHP = 0x08
OP_PLP = 0x28
OP_SEI = 0x78


# ---- Variables ---------------------------------------------------------------------------

def placements():
    """{ "zp" | "nozp" | "rows" | "at" constExpr }. Returns them as symbol flags; the address
    is left in `placed_at`."""
    global placed_at
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
            placed_at = constant_number()
        elif lex.tok == lex.T_ROWS:
            flags = flags | kernel.SF_ROWS
            lex.next()
        elif lex.tok == lex.T_IN:
            err.fatal(err.E_UNSUPPORTED)
        else:
            break
    if flags & kernel.SF_ZP != 0 and flags & kernel.SF_NOZP != 0:
        err.fatal(err.E_SYNTAX)
    return flags


def zp_class(flags):
    """The class of a slot or variable declared with these flags."""
    if flags & kernel.SF_ZP != 0:
        return reg.CLASS_ZP
    if flags & kernel.SF_NOZP != 0:
        return reg.CLASS_NOT_ZP
    return reg.CLASS_EITHER


def lasting_variable(scope, name, t, flags, level):
    """Declare a variable that is not a slot: one that lives for the whole program, which
    gets its object-file symbol now, or one at a fixed address. A `static` variable is the
    symbol `module.function.name`."""
    s = kernel.sym_add(scope, name, kernel.K_VAR)
    kernel.sym_type[s] = t
    kernel.sym_flags[s] = flags
    if flags & kernel.SF_AT != 0:
        kernel.sym_value[s] = placed_at
    elif level == LEVEL_MODULE:
        kernel.sym_obj[s] = out.symbol(out.SYM_VARIABLE, kernel.module_name[0], 0, name)
    else:
        kernel.sym_obj[s] = out.symbol(out.SYM_VARIABLE, kernel.module_name[0],
                                       kernel.sym_name[function], name)
    return s


def push_variable(s):
    """Push variable `s`: a local, or one that lives for the whole program."""
    if kernel.sym_kind[s] == kernel.K_LOCAL:
        gen.local(kernel.sym_type[s], kernel.sym_value[s])
    else:
        gen.variable(s)


def initial_assignment(s):
    """"=" expression after a local's declaration: an assignment made on every entry."""
    push_variable(s)
    line = lex.line
    col = lex.col
    expression()
    err.position(line, col)
    gen.store()
    err.position(lex.line, lex.col)


def variable(more, level):
    """varDecl = "var" name ":" type { placement } [ "=" initialiser ], from "var" on.
    `more` is kernel.SF_PUB or 0."""
    lex.next()
    scope = inline.local_scope()
    if level == LEVEL_MODULE:
        scope = kernel.SCOPE_MODULE
    name = new_name(scope)
    lex.expect(lex.T_COLON, err.E_COLON_EXPECTED)
    line = lex.line
    col = lex.col
    t = type_spec()
    flags = placements() | more
    err.position(line, col)
    if flags & kernel.SF_ROWS != 0:
        if not typetab.is_array(t):
            err.fatal(err.E_TYPE)
        t = typetab.array_of(typetab.base(t), typetab.length(t), True)
    layout(t)
    if (typetab.is_array(t) or typetab.is_record(t)) and flags & kernel.SF_ZP == 0:
        flags = flags | kernel.SF_NOZP          # nor a record: never in zero page unless asked
    err.position(lex.line, lex.col)
    if level == LEVEL_LOCAL and flags & kernel.SF_AT == 0:
        s = kernel.sym_add(scope, name, kernel.K_LOCAL)
        kernel.sym_type[s] = t
        if inline.level == 0:
            kernel.sym_value[s] = reg.new_slot(typetab.size(t), zp_class(flags), reg.SLOT_LOCAL, name)
        elif zp_class(flags) != reg.CLASS_EITHER:
            kernel.sym_value[s] = reg.new_slot(typetab.size(t), zp_class(flags), reg.SLOT_LOCAL,
                                               inline.slot_name(name, reg.local_count))
        else:
            # A local of an inline function: a temporary of the caller's frame, free again when
            # the expansion ends; one that must be in zero page, or must not (an array, a
            # record), is a slot of its own, since temporaries share theirs.
            kernel.sym_value[s] = inline.own_slot(typetab.size(t))
    else:
        s = lasting_variable(scope, name, t, flags, level)
    if lex.tok != lex.T_ASSIGN:
        return
    lex.next()
    no_record(t)
    if typetab.is_array(t):
        data = gen.anonymous()
        table_data(t, data)
        if level == LEVEL_LOCAL:
            push_variable(s)
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


def no_record(t):
    """Something of type `t` is given an initial value: it cannot be a record, or an array of
    them, yet."""
    if typetab.is_record(typetab.innermost(t)):
        err.fatal(err.E_RECORD_INIT)


def layout(t):
    """Check that the elements of array type `t`, and of the arrays it is made of, can be
    reached: one of more than 256 elements larger than a byte must be stored by row, and an
    element stored by row must have a size that is a power of two."""
    while typetab.is_array(t):
        size = typetab.size(typetab.base(t))
        if typetab.length(t) > 256 and size > 1 and not typetab.is_rows(t):
            err.fatal(err.E_NEEDS_ROWS)
        if typetab.is_rows(t) and size & (size - 1) != 0:
            if typetab.is_record(typetab.base(t)):
                err.fatal_value(err.E_ROWS_RECORD, size)
            err.fatal(err.E_ELEMENT_SIZE)
        t = typetab.base(t)


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
            out.table[i] = lex.string[i]
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
    err.position(lex.line, lex.col)


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
    if reg.op_kind[i] != reg.O_FUNC or kernel.sym_results[reg.op_var[i]] != 2:
        err.position(line, col)
        err.fatal(err.E_RESULTS)
    if lex.tok != lex.T_LPAREN:
        err.fatal(err.E_LPAREN_EXPECTED)
    call(True)
    err.position(line, col)
    gen.store_pair()
    err.position(lex.line, lex.col)


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
        err.position(lex.line, lex.col)
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
    err.position(lex.line, lex.col)
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
        lex.expect(lex.T_NL, err.E_NL_EXPECTED)
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
            lex.expect(lex.T_NL, err.E_NL_EXPECTED)
            body()
            break
    end_of_block()
    if done != reg.NONE:
        reg.label(done)


def while_statement():
    """"while" expression "do" NL body "end"."""
    global exit_label, next_label, critical_inner
    saved_exit = exit_label
    saved_next = next_label
    saved_inner = critical_inner
    critical_inner = 0
    lex.next()
    top = fbuf.new_label()
    reg.loop_label(top)
    gen.loop_begin()
    exit_label = test()
    next_label = top
    lex.expect(lex.T_DO, err.E_DO_EXPECTED)
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)
    body()
    end_of_block()
    if fbuf.runs_on():
        reg.jump(top)
    reg.label(exit_label)
    gen.loop_end()
    exit_label = saved_exit
    next_label = saved_next
    critical_inner = saved_inner


def loop_statement():
    """"loop" NL body ( "end" | "until" expression ). `continue` goes to the test of `until`,
    or to the top if there is none."""
    global exit_label, next_label, critical_inner
    saved_exit = exit_label
    saved_next = next_label
    saved_inner = critical_inner
    critical_inner = 0
    lex.next()
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)
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


def loop_variable():
    """The name after "for": a variable of a number type. Returns its symbol."""
    if lex.tok != lex.T_NAME:
        err.fatal(err.E_NAME_EXPECTED)
    s, found = inline.lookup(lex.value)
    if not found:
        err.fatal(err.E_UNDEFINED)
    if kernel.sym_kind[s] != kernel.K_LOCAL and kernel.sym_kind[s] != kernel.K_VAR:
        err.fatal(err.E_NOT_VAR)
    if not typetab.is_number(kernel.sym_type[s]):
        err.fatal(err.E_TYPE)
    lex.next()
    return s


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
    err.position(lex.line, lex.col)


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


def for_statement():
    """"for" name "=" expression ( "to" | "downto" ) expression "do" NL body "end". The
    variable is set to the first value, the loop is skipped if that is past the limit, and
    the test is at the bottom: the variable is compared with the limit before each step
    (docs/codegen.md, "Statements"). A limit that is a variable is not copied: it is read
    at each test."""
    global exit_label, next_label, critical_inner
    saved_exit = exit_label
    saved_next = next_label
    saved_inner = critical_inner
    critical_inner = 0
    lex.next()
    s = loop_variable()
    t = kernel.sym_type[s]
    lex.expect(lex.T_ASSIGN, err.E_SYNTAX)
    push_variable(s)
    line = lex.line
    col = lex.col
    expression()
    err.position(line, col)
    known = gen.pend_op == 0 and reg.op_kind[reg.depth - 1] == reg.O_CONST
    if known:
        reg.assignable(reg.depth - 1, t)
    first = reg.op_value[reg.depth - 1]
    gen.store()
    err.position(lex.line, lex.col)
    if lex.tok != lex.T_TO and lex.tok != lex.T_DOWNTO:
        err.fatal(err.E_TO_EXPECTED)
    down = lex.tok == lex.T_DOWNTO
    lex.next()
    limit_value(t)
    limit = reg.depth - 1
    lex.expect(lex.T_DO, err.E_DO_EXPECTED)
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)
    op = fold.LE
    if down:
        op = fold.GE
    if known:
        gen.constant(t, first)          # a constant first value can make the test known
    else:
        push_variable(s)
    exit_label = compare_limit(limit, op)
    top = fbuf.new_label()
    reg.loop_label(top)
    gen.loop_begin()
    next_label = fbuf.new_label()
    body()
    end_of_block()
    reg.label(next_label)
    push_variable(s)
    reg.join(exit_label, compare_limit(limit, fold.NE))
    step_back(s, down, limit, top)
    gen.loop_end()
    reg.label(exit_label)
    reg.pop()
    exit_label = saved_exit
    next_label = saved_next
    critical_inner = saved_inner


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
    err.position(lex.line, lex.col)
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)
    done = fbuf.new_label()
    base = case_count
    while lex.tok == lex.T_OF:
        lex.next()
        chosen = fbuf.new_label()
        other = case_constants(selector, chosen, base)
        lex.expect(lex.T_NL, err.E_NL_EXPECTED)
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
        lex.expect(lex.T_NL, err.E_NL_EXPECTED)
        body()
    end_of_block()
    reg.label(done)
    reg.pop()
    case_count = base


def restore_flags(count):
    """Leave `count` `critical` blocks: a PLP for each. The flags then show nothing known."""
    for n in range(0, count):
        fbuf.op(OP_PLP)
    reg.flags = reg.NO_REG


def critical_statement():
    """"critical" NL body "end": PHP and SEI, the body, PLP. `break`, `continue` and `return`
    that leave the block restore the flags first (docs/codegen.md, "Statements")."""
    global critical_depth, critical_inner
    lex.next()
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)
    fbuf.op(OP_PHP)
    fbuf.op(OP_SEI)
    critical_depth += 1
    critical_inner += 1
    body()
    end_of_block()
    critical_depth -= 1
    critical_inner -= 1
    restore_flags(1)


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
    err.position(lex.line, lex.col)
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
    restore_flags(critical_inner)
    reg.jump(target)


def status():
    """An expression whose value is returned in the carry flag."""
    line = lex.line
    col = lex.col
    gen.carry_wanted()
    expression()
    err.position(line, col)
    gen.carry()
    err.position(lex.line, lex.col)


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
    err.position(lex.line, lex.col)
    lex.expect(lex.T_COMMA, err.E_RESULTS)
    status()                            # may need A: the value waits where it is
    gen.load_result()


def return_statement():
    """"return" [ expression [ "," expression ] ], as the function's results require. The
    value goes to A, or A and X, and a `bool` to the carry flag."""
    results = kernel.sym_results[function]
    first = kernel.sym_members[function] + kernel.sym_params[function]
    if critical_depth > 0 and results > 0 and kernel.member_value[first + results - 1] == gen.REG_C:
        err.fatal(err.E_STATUS_IN_CRITICAL)     # PLP would change the carry flag
    lex.next()
    if (results == 0) != (lex.tok == lex.T_NL):
        err.fatal(err.E_RESULTS)
    # In an expansion, the value may stay the operand it is (inline.leaves_operand()); if not,
    # it goes where a call leaves it, and the `return` is a jump to the expansion's end.
    keep = inline.level > 0 and inline.leaves_operand()
    t = kernel.member_type[first]
    line = lex.line
    col = lex.col
    if results == 2:
        value_and_status(t)
    elif results == 1 and kernel.member_value[first] == gen.REG_C and not keep:
        status()
    elif results == 1:
        expression()
        err.position(line, col)
        if not keep or gen.pend_op == 0 or gen.pend_type != t:
            gen.accept(t)
        err.position(lex.line, lex.col)
        if not keep and t != typetab.BOOL_TYPE:
            gen.load_result()
    restore_flags(critical_depth)
    if keep:
        inline.lazy[inline.level] = True
    elif inline.level > 0:
        reg.jump(inline.done[inline.level])
    else:
        gen.ret()


def statement():
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
    elif lex.tok == lex.T_HASH_IF:
        directive()
    else:
        err.fatal(err.E_STMT_EXPECTED)
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)


def ends_body(token):
    """True for the tokens that end a body; which of them is right is for the caller to check."""
    return token == lex.T_END or token == lex.T_EOF or token == lex.T_ELIF or token == lex.T_ELSE \
        or token == lex.T_UNTIL or token == lex.T_OF


def body():
    """body = { varDecl | statement }."""
    while not ends_body(lex.tok):
        statement()


def inline_argument(f, i):
    """The argument for parameter `i` of inline function `f`: a value it can be given, which
    INLINE makes the parameter's symbol of (inline.argument_symbol())."""
    line = lex.line
    col = lex.col
    expression()
    err.position(line, col)
    gen.as_value()
    gen.accept(kernel.member_type[kernel.sym_members[f] + i])
    inline.argument_symbol(f, i)
    err.position(lex.line, lex.col)


def expand(f, wanted):
    """The arguments and ")" of a call of inline function `f` (which inline.enter() has begun),
    after its "(", and its body,
    replayed from its saved tokens as if it were written here (docs/code-model.md, "Inline
    functions"). A `return` goes to the end of the expansion, where the result is left as a
    call leaves it, if it is `wanted`; or, from the last statement, it may leave its value
    as the operand it is. The token after the ")" is the current one at the end."""
    global function, exit_label, next_label, critical_depth, critical_inner
    count = 0
    if lex.tok != lex.T_RPAREN:
        while True:
            if count == kernel.sym_params[f]:
                err.fatal(err.E_ARG_COUNT)
            inline_argument(f, count)
            count += 1
            if lex.tok != lex.T_COMMA:
                break
            lex.next()
    if lex.tok != lex.T_RPAREN:
        err.fatal(err.E_RPAREN_EXPECTED)
    if count != kernel.sym_params[f]:
        err.fatal(err.E_ARG_COUNT)
    line = lex.line
    col = lex.col
    brackets = lex.open_brackets
    saved_function = function
    saved_exit = exit_label
    saved_next = next_label
    saved_depth = critical_depth
    saved_inner = critical_inner
    function = f
    exit_label = reg.NONE
    next_label = reg.NONE
    critical_depth = 0
    critical_inner = 0
    lex.open_brackets = 0
    inline.body_begin(f)
    lex.next()
    body()
    if lex.tok != lex.T_EOF:
        err.fatal(err.E_END_EXPECTED)
    src.close()
    function = saved_function
    exit_label = saved_exit
    next_label = saved_next
    critical_depth = saved_depth
    critical_inner = saved_inner
    lex.open_brackets = brackets
    lex.resume(lex.T_RPAREN, line, col)
    if not inline.lazy[inline.depth]:
        reg.label(inline.done[inline.depth])
        if wanted:
            gen.result(f)
    inline.leave()
    lex.next()


def function_body(f):
    """The body of function `f`, whose parameters are declared."""
    global function, exit_label, next_label, critical_depth, critical_inner
    function = f
    exit_label = reg.NONE
    next_label = reg.NONE
    critical_depth = 0
    critical_inner = 0
    body()
