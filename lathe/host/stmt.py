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
        fbuf.jump(top)
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
    critical_inner = saved_inner


def loop_variable():
    """The name after "for": a variable of a number type. Returns its symbol."""
    if lex.tok != lex.T_NAME:
        err.fatal(err.E_NAME_EXPECTED)
    s, found = kernel.sym_lookup(lex.value)
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
    expr.expression()
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
            fbuf.branch(gen.OP_BNE, top)
            reg.modify(reg.OP_INC, i, 1)
    if back:
        fbuf.branch(gen.OP_BNE, top)
    else:
        fbuf.jump(top)
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
    expr.expression()
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
    fbuf.join(exit_label, compare_limit(limit, fold.NE))
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
        expr.constant(reg.op_type[selector])
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
        fbuf.branch(gen.OP_BEQ, chosen)
    other = fbuf.new_label()
    fbuf.branch(gen.OP_BNE, other)
    return other


def arrive_with(target, selector):
    """Put label `target` here, where every way in has the selector, operand `selector`, in A."""
    reg.label(target)
    if reg.op_kind[selector] == reg.O_VAR:
        reg.remember(reg.A, selector, 0)


def case_statement():
    """"case" expression NL { "of" constExpr { "," constExpr } NL body } [ "else" NL body ]
    "end". The selector is compared with the constants of each `of` in turn: it is a variable,
    or is stored in a temporary, so that it can be loaded again (docs/codegen.md,
    "Statements"). A variable at a fixed address may be a device, and is read once."""
    global case_count
    lex.next()
    line = lex.line
    col = lex.col
    expr.expression()
    err.position(line, col)
    gen.as_value()
    selector = reg.depth - 1
    t = reg.op_type[selector]
    if typetab.size(t) != 1 or typetab.is_untyped(t):
        err.fatal(err.E_CASE_SELECTOR)
    if reg.op_kind[selector] == reg.O_VAR and reg.op_symbol[selector] == kernel.NO_OBJ:
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
        arrive_with(chosen, selector)
        body()
        if lex.tok == lex.T_END:
            reg.label(other)            # the body runs on to here: A may hold anything
        else:
            fbuf.jump(done)
            arrive_with(other, selector)
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
    expr.constant(typetab.NO_TYPE)
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
    results = kernel.sym_results[function]
    first = kernel.sym_members[function] + kernel.sym_params[function]
    if critical_depth > 0 and results > 0 and kernel.member_value[first + results - 1] == gen.REG_C:
        err.fatal(err.E_STATUS_IN_CRITICAL)     # PLP would change the carry flag
    lex.next()
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
    restore_flags(critical_depth)
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


def function_body(f):
    """The body of function `f`, whose parameters are declared."""
    global function, exit_label, next_label, critical_depth, critical_inner
    function = f
    exit_label = reg.NONE
    next_label = reg.NONE
    critical_depth = 0
    critical_inner = 0
    body()
