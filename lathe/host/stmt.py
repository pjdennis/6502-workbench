"""STMT: statements and control flow.

Owns the parsing of a function's body: each statement of docs/language.md has a function
here, chosen in statement() by its first token, and the shapes they generate are those of
docs/codegen.md, "Statements". It knows the loop that `break` and `continue` belong to, and
the function whose results `return` gives.

Variable declarations are parsed here, for DECL too, because a body has them and modules
cannot import each other.
"""
import asmblock
import err
import expr
import fbuf
import fold
import gen
import kernel
import lex
import out
import reg
import typetab

RECURSIVE = ["body"]

# Where a variable is declared
LEVEL_MODULE = 0
LEVEL_LOCAL = 1         # in a function: a slot of its frame
LEVEL_STATIC = 2        # in a function, but it lives for the whole program

function = 0            # the function being compiled: its symbol in the kernel's table
exit_label = reg.NONE   # where `break` goes: after the nearest loop
next_label = reg.NONE   # where `continue` goes: to that loop's next pass
placed_at = 0           # the address after "at" in the declaration being parsed


# ---- Variables ---------------------------------------------------------------------------

def placements():
    """{ "zp" | "nozp" | "at" constExpr }. Returns them as symbol flags; the address is left
    in `placed_at`."""
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
            placed_at = expr.constant_number()
        elif lex.tok == lex.T_ROWS or lex.tok == lex.T_IN:
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


def initial_assignment(s):
    """"=" expression after a local's declaration: an assignment made on every entry."""
    if kernel.sym_kind[s] == kernel.K_LOCAL:
        gen.local(kernel.sym_type[s], kernel.sym_value[s])
    else:
        gen.variable(s)
    line = lex.line
    col = lex.col
    expr.expression()
    err.position(line, col)
    gen.store()
    err.position(lex.line, lex.col)


def variable(more, level):
    """varDecl = "var" name ":" type { placement } [ "=" initialiser ], from "var" on.
    `more` is kernel.SF_PUB or 0."""
    lex.next()
    scope = kernel.SCOPE_LOCAL
    if level == LEVEL_MODULE:
        scope = kernel.SCOPE_MODULE
    name = expr.new_name(scope)
    lex.expect(lex.T_COLON, err.E_COLON_EXPECTED)
    t = expr.scalar_type()
    flags = placements() | more
    if level == LEVEL_LOCAL and flags & kernel.SF_AT == 0:
        s = kernel.sym_add(scope, name, kernel.K_LOCAL)
        kernel.sym_type[s] = t
        kernel.sym_value[s] = reg.new_slot(typetab.size(t), zp_class(flags), reg.SLOT_LOCAL, name)
    else:
        s = lasting_variable(scope, name, t, flags, level)
    if lex.tok != lex.T_ASSIGN:
        return
    lex.next()
    if level == LEVEL_LOCAL:
        initial_assignment(s)
    else:
        expr.constant(t)
        gen.initial(s, reg.op_value[reg.depth - 1])
        reg.pop()


# ---- Assignments and calls ---------------------------------------------------------------

def assignment(line, col):
    """assignOp expression, after the designator at `line`, `col`."""
    expr.target(line, col)
    token = lex.tok
    lex.next()
    line = lex.line
    col = lex.col
    expr.expression()
    err.position(line, col)
    if token == lex.T_ASSIGN:
        gen.store()
    else:
        gen.assign(token - lex.T_PLUS_ASSIGN + fold.ADD)
    err.position(lex.line, lex.col)


def pair_assignment(line, col):
    """"," designator "=" call, after the designator at `line`, `col`: the value and the
    status of a call that gives both."""
    expr.target(line, col)
    lex.next()
    line = lex.line
    col = lex.col
    expr.designator()
    expr.target(line, col)
    lex.expect(lex.T_ASSIGN, err.E_SYNTAX)
    line = lex.line
    col = lex.col
    expr.designator()
    i = reg.depth - 1
    if reg.op_kind[i] != reg.O_FUNC or kernel.sym_results[reg.op_var[i]] != 2:
        err.position(line, col)
        err.fatal(err.E_RESULTS)
    if lex.tok != lex.T_LPAREN:
        err.fatal(err.E_LPAREN_EXPECTED)
    expr.call(True)
    err.position(line, col)
    gen.store_pair()
    err.position(lex.line, lex.col)


def name_statement():
    """designator ( assignOp expression | "," designator "=" call | arguments ): the token
    after the designator says which."""
    line = lex.line
    col = lex.col
    expr.designator()
    if reg.op_kind[reg.depth - 1] == reg.O_FUNC:
        if lex.tok != lex.T_LPAREN:
            err.fatal(err.E_LPAREN_EXPECTED)
        expr.call(False)                # a call used as a statement may ignore its results
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
    expr.expression()
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
            fbuf.jump(done)
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
    global exit_label, next_label
    saved_exit = exit_label
    saved_next = next_label
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
        fbuf.jump(top)
    reg.label(exit_label)
    gen.loop_end()
    exit_label = saved_exit
    next_label = saved_next


def loop_statement():
    """"loop" NL body ( "end" | "until" expression ). `continue` goes to the test of `until`,
    or to the top if there is none."""
    global exit_label, next_label
    saved_exit = exit_label
    saved_next = next_label
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
        fbuf.join(top, test())          # when the test is false: round again
    else:
        end_of_block()
        fbuf.join(top, next_label)
        if fbuf.runs_on():
            fbuf.jump(top)
    reg.label(exit_label)
    gen.loop_end()
    exit_label = saved_exit
    next_label = saved_next


def jump_statement(target):
    """"break" or "continue": a JMP to `target`, the label the nearest loop has for it."""
    if target == reg.NONE:
        err.fatal(err.E_NO_LOOP)
    lex.next()
    fbuf.jump(target)


def status():
    """An expression whose value is returned in the carry flag."""
    line = lex.line
    col = lex.col
    gen.carry_wanted()
    expr.expression()
    err.position(line, col)
    gen.carry()
    err.position(lex.line, lex.col)


def passes_on(t):
    """True if the expression just parsed is nothing but a call that gives a value of type
    `t` and a status: both are then where this function's own results must be."""
    i = reg.depth - 1
    return lex.tok == lex.T_NL and gen.mark() == expr.passed and reg.in_registers(i) \
        and reg.op_type[i] == t


def value_and_status(t):
    """expression "," expression after "return", or a call that gives both results."""
    line = lex.line
    col = lex.col
    expr.results_expression()
    if expr.passed != reg.NONE:
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
    lex.next()
    results = kernel.sym_results[function]
    first = kernel.sym_members[function] + kernel.sym_params[function]
    if (results == 0) != (lex.tok == lex.T_NL):
        err.fatal(err.E_RESULTS)
    if results == 2:
        value_and_status(kernel.member_type[first])
    elif results == 1 and kernel.member_value[first] == gen.REG_C:
        status()
    elif results == 1:
        line = lex.line
        col = lex.col
        expr.expression()
        err.position(line, col)
        gen.accept(kernel.member_type[first])
        err.position(lex.line, lex.col)
        gen.load_result()
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
    elif lex.tok == lex.T_FOR or lex.tok == lex.T_CASE or lex.tok == lex.T_CRITICAL:
        err.fatal(err.E_UNSUPPORTED)
    else:
        err.fatal(err.E_STMT_EXPECTED)
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)


def ends_body(token):
    """True for the tokens that end a body; which of them is right is for the caller to check."""
    return token == lex.T_END or token == lex.T_EOF or token == lex.T_ELIF or token == lex.T_ELSE \
        or token == lex.T_UNTIL


def body():
    """body = { varDecl | statement }."""
    while not ends_body(lex.tok):
        statement()


def function_body(f):
    """The body of function `f`, whose parameters are declared."""
    global function, exit_label, next_label
    function = f
    exit_label = reg.NONE
    next_label = reg.NONE
    body()
