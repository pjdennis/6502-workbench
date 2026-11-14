"""EXPR: expressions, and types as they are written in the source.

Owns the parsing of everything that can stand where a value is wanted. What it parses
becomes operands on GEN's stack; no code is generated until an operand has to be somewhere,
which is what makes a constant argument a single load and will make constant folding free.

So far an expression is a number, a character or a named constant, and a call takes such
values to an `extern` function's registers or calls a function without parameters. The
operators of docs/language.md go into expression(), one function per level of precedence.

Types are parsed here and not in DECL because conversions and `sizeof` will need them inside
expressions, array types need a constant expression, and modules cannot import each other.
"""
import err
import gen
import kernel
import lex
import typetab


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


def designator():
    """designator = name { "." name | "[" expression "]" }. Pushes an operand for what it
    names. Fields and elements come later."""
    s = named_symbol()
    if kernel.sym_kind[s] == kernel.K_FUNC:
        gen.push(gen.O_FUNC, typetab.NO_TYPE, s)
    else:
        gen.push(gen.O_CONST, kernel.sym_type[s], kernel.sym_value[s])


def starts_expression(token):
    """True for the tokens an expression can start with, other than a number or a name."""
    if token == lex.T_STRING or token == lex.T_LPAREN or token == lex.T_MINUS:
        return True
    if token == lex.T_TILDE or token == lex.T_ADDRESS or token == lex.T_NOT:
        return True
    return token == lex.T_CARET or basic_type(token) != typetab.NO_TYPE


def is_operator(token):
    """True for a binary operator."""
    return lex.joins_lines(token) and token != lex.T_COMMA


def primary():
    """primary = number | designator, so far. Pushes its operand."""
    if lex.tok == lex.T_NUMBER:
        gen.push(gen.O_CONST, typetab.NUMBER_TYPE, lex.value)
        lex.next()
    elif lex.tok == lex.T_NAME:
        designator()
        if gen.op_kind[gen.depth - 1] == gen.O_FUNC:
            err.fatal(err.E_UNSUPPORTED)        # a call as a value
    elif starts_expression(lex.tok):
        err.fatal(err.E_UNSUPPORTED)
    else:
        err.fatal(err.E_EXPR_EXPECTED)


def expression():
    """Parse an expression. Its operand is left on GEN's stack."""
    primary()
    if is_operator(lex.tok):
        err.fatal(err.E_UNSUPPORTED)


def constant_number():
    """constExpr where a number is wanted, as for an address. Returns its value."""
    line = lex.line
    col = lex.col
    expression()
    operand = gen.depth - 1
    if gen.op_kind[operand] != gen.O_CONST:
        err.position(line, col)
        err.fatal(err.E_NOT_CONST)
    if gen.op_type[operand] != typetab.NUMBER_TYPE and not typetab.is_number(gen.op_type[operand]):
        err.position(line, col)
        err.fatal(err.E_TYPE)
    gen.pop()
    return gen.op_value[operand]


def check_fits(operand, t):
    """Check that operand number `operand` can be given to something of type `t`: a number as
    written must be in the type's range, and anything else must have exactly that type.
    The caller has set the position an error is reported at."""
    actual = gen.op_type[operand]
    if actual == typetab.NUMBER_TYPE and typetab.is_number(t):
        if gen.op_kind[operand] == gen.O_CONST and not typetab.number_fits(gen.op_value[operand], t):
            err.fatal(err.E_RANGE)
    elif actual != t:
        err.fatal(err.E_TYPE)


def argument(t):
    """One argument for a parameter of type `t`. Its operand is left on the stack."""
    line = lex.line
    col = lex.col
    expression()
    after_line = lex.line
    after_col = lex.col
    err.position(line, col)                 # an argument that does not fit is reported at its start
    check_fits(gen.depth - 1, t)
    err.position(after_line, after_col)


def arguments(f):
    """[ expression { "," expression } ] ")", after the "(". Leaves one operand on the stack
    for each parameter of function `f`, in order."""
    count = 0
    if lex.tok != lex.T_RPAREN:
        while True:
            if count == kernel.sym_params[f]:
                err.fatal(err.E_ARG_COUNT)
            argument(kernel.member_type[kernel.sym_members[f] + count])
            count += 1
            if lex.tok != lex.T_COMMA:
                break
            lex.next()
    if lex.tok != lex.T_RPAREN:
        err.fatal(err.E_RPAREN_EXPECTED)
    if count != kernel.sym_params[f]:
        err.fatal(err.E_ARG_COUNT)
    lex.next()


def load_registers(f, first):
    """Put the arguments of `extern` function `f`, which are the operands from number `first`
    on, into the registers its parameters are bound to. The carry flag is set last, because
    getting a value into a register will often change it."""
    members = kernel.sym_members[f]
    for i in range(0, kernel.sym_params[f]):
        if kernel.member_value[members + i] != gen.REG_C:
            gen.load_register(kernel.member_value[members + i], first + i)
    for i in range(0, kernel.sym_params[f]):
        if kernel.member_value[members + i] == gen.REG_C:
            gen.load_register(gen.REG_C, first + i)


def call():
    """arguments = "(" [ expression { "," expression } ] ")", for the function whose operand
    is on top of the stack. Generates the call. The results are not yet made into an operand."""
    f = gen.op_value[gen.depth - 1]
    gen.pop()
    lex.next()
    first = gen.depth
    arguments(f)
    if kernel.sym_flags[f] & kernel.SF_EXTERN != 0:
        load_registers(f, first)
        gen.call_address(kernel.sym_value[f])
    else:
        gen.call_function(f)
    while gen.depth > first:
        gen.pop()
