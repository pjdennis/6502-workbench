"""EXPR: expressions, and types as they are written in the source.

Owns the parsing of everything that can stand where a value is wanted: one function for each
level of precedence in docs/language.md, from expression() down to primary(). What it parses
becomes operands on GEN's stack; EXPR itself chooses no instruction. It says where an error
in an operand's type is reported: at the operator, or at the start of the value.

Types are parsed here and not in DECL because conversions and `sizeof` need them inside
expressions, array types need a constant expression, and modules cannot import each other.
"""
import err
import fold
import gen
import kernel
import lex
import reg
import typetab

RECURSIVE = ["expression", "factor", "inverse"]

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
    """type = typeKw | "^" type. Returns the type. Named types, arrays and records come later."""
    pointers = 0
    while lex.tok == lex.T_CARET:
        pointers += 1
        lex.next()
    t = basic_type(lex.tok)
    if t == typetab.NO_TYPE:
        if lex.tok == lex.T_NAME or lex.tok == lex.T_LBRACKET or lex.tok == lex.T_RECORD:
            err.fatal(err.E_UNSUPPORTED)
        err.fatal(err.E_TYPE_EXPECTED)
    lex.next()
    while pointers > 0:
        t = typetab.pointer_to(t)
        pointers -= 1
    return t


def scalar_type():
    """The type of a variable, parameter, result or constant: so far one of the basic types."""
    if lex.tok == lex.T_CARET:
        err.fatal(err.E_UNSUPPORTED)
    return type_spec()


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
    """name [ "." name ]: the symbol a name means here, or module.name means in that module."""
    if lex.tok != lex.T_NAME:
        err.fatal(err.E_NAME_EXPECTED)
    s, found = kernel.sym_lookup(lex.value)
    if not found:
        err.fatal(err.E_UNDEFINED)
    lex.next()
    if kernel.sym_kind[s] == kernel.K_MODULE:
        scope = kernel.sym_value[s]
        lex.expect(lex.T_DOT, err.E_DOT_EXPECTED)
        if lex.tok != lex.T_NAME:
            err.fatal(err.E_NAME_EXPECTED)
        s, found = kernel.sym_find(scope, lex.value)
        if not found:
            err.fatal(err.E_UNDEFINED)
        lex.next()
    return s


# ---- Designators and calls ---------------------------------------------------------------

def builtin(which):
    """`lo(x)`, `hi(x)` or `sizeof(type)`, after its name."""
    lex.expect(lex.T_LPAREN, err.E_LPAREN_EXPECTED)
    if which == B_SIZEOF:
        gen.size_of(type_spec())
    elif which == B_LEN:
        err.fatal(err.E_UNSUPPORTED)
    else:
        line = lex.line
        col = lex.col
        expression()
        err.position(line, col)
        gen.part(which)
        err.position(lex.line, lex.col)
    lex.expect(lex.T_RPAREN, err.E_RPAREN_EXPECTED)


def designator():
    """designator = name { "." name | "[" expression "]" }. Pushes an operand for what it
    names. Fields and elements come later."""
    s = named_symbol()
    kind = kernel.sym_kind[s]
    if kind == kernel.K_FUNC:
        gen.function(s)
    elif kind == kernel.K_CONST:
        gen.constant(kernel.sym_type[s], kernel.sym_value[s])
    elif kind == kernel.K_LOCAL:
        gen.local(kernel.sym_type[s], kernel.sym_value[s])
    elif kind == kernel.K_VAR:
        gen.variable(s)
    else:
        builtin(kernel.sym_value[s])
    if lex.tok == lex.T_LBRACKET or lex.tok == lex.T_DOT:
        err.fatal(err.E_UNSUPPORTED)


def target(line, col):
    """Check that the newest operand, which the designator at `line`, `col` gave, is a variable
    that can be assigned to."""
    i = reg.depth - 1
    if reg.op_kind[i] != reg.O_VAR or reg.op_flags[i] & reg.F_TEMP != 0:
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
    its parameter in the frame of function `f`; those of an `extern` or `asm` function stay on the
    stack, in order, for GEN to put in the registers."""
    global pending_count
    by_register = gen.by_registers(f)
    saved = gen.outer
    saved_pending = pending_count
    count = 0
    if lex.tok != lex.T_RPAREN:
        while True:
            if count == kernel.sym_params[f]:
                err.fatal(err.E_ARG_COUNT)
            if not by_register:
                gen.parameter(f, count)
            argument(kernel.member_type[kernel.sym_members[f] + count], not by_register)
            count += 1
            if lex.tok != lex.T_COMMA:
                break
            if by_register:
                gen.hold()
            elif count == 1:
                add_pending(f)
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
    gen.result() pushes."""
    global passing
    f = reg.op_var[reg.depth - 1]
    reg.pop()
    lex.next()
    first = reg.depth
    saved = passing
    passing = False             # a call inside an argument passes nothing on
    arguments(f)
    passing = saved
    gen.call(f, first, wanted)


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

def conversion(line, col):
    """typeKw "(" expression ")"."""
    t = basic_type(lex.tok)
    lex.next()
    lex.expect(lex.T_LPAREN, err.E_LPAREN_EXPECTED)
    expression()
    err.position(line, col)
    gen.convert(t)
    err.position(lex.line, lex.col)
    lex.expect(lex.T_RPAREN, err.E_RPAREN_EXPECTED)


def primary():
    """primary = number | "(" expression ")" | typeKw "(" expression ")"
    | designator [ arguments [ "->" designator ] ]. Pushes its operand."""
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
        conversion(line, col)
    elif lex.tok == lex.T_NAME:
        designator()
        if reg.op_kind[reg.depth - 1] == reg.O_FUNC:
            call_value(line, col)
    elif lex.tok == lex.T_STRING or lex.tok == lex.T_CARET or lex.tok == lex.T_LBRACKET:
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
        err.fatal(err.E_UNSUPPORTED)
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
    """constExpr: an expression that is known now. Unless `t` is typetab.NO_TYPE it must be
    one a `t` can be given, and takes that type. The constant is left on the stack."""
    line = lex.line
    col = lex.col
    expression()
    err.position(line, col)
    gen.as_value()
    if reg.op_kind[reg.depth - 1] != reg.O_CONST:
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
    if reg.op_type[i] == typetab.BOOL_TYPE:
        err.fatal(err.E_TYPE)
    if typetab.is_signed(reg.op_type[i]) and reg.op_value[i] >= 0x8000:
        err.fatal(err.E_RANGE)
    err.position(lex.line, lex.col)
    reg.pop()
    return reg.op_value[i]
