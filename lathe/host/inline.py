"""INLINE: the saved tokens of `inline` functions, and the state of the expansions under way.

Owns
- the saved tokens (docs/code-model.md, "Inline functions"): an `inline` function's body is
  not compiled where it is declared. save() reads it as tokens up to its `end` and keeps them,
  for the whole module, in a buffer of SAVED_SIZE bytes of text memory, in the form lex.py
  describes at SAVED_LINE. A name is kept as its name: DECL keeps every name the declaration
  made (it does not release them as a function's scope ends), so it stays valid. An imported
  `inline` function's tokens come from its module's interface (read()), where the names are
  written as text (write());
- what save() finds out about the body by looking at its tokens, once: which parameters it
  assigns to, whether it is "pure" (makes no call, takes no address, and assigns to nothing but
  its own parameters and locals and one variable of the program, by name), and whether its only
  `return` is its last statement;
- the expansions under way: EXPR replays the tokens at each call (expr.expand()). Each
  expansion is a level; its parameters and locals are symbols of the scope SCOPE_INLINE + level,
  and names in its body are looked up in that scope, then in the scope of the module that
  declared the function (lookup()), never in the caller's;
- how a parameter is given its argument (argument_symbol()), and the slots of the caller's
  frame that an expansion owns: temporaries, free again when it ends.

The record of an inline function, at sym_value of its symbol, in the buffer:
    R_END       pointer past its tokens (2)
    R_LINE      the line of its first token (2)
    R_FILE      pointer to the name of the file it was read from (2)
    R_FLAGS     PURE, LAST_RETURN (1)
    R_WRITTEN   the variable of the program that a pure body assigns to, by its name (2), or 0
    R_PARAMS    for each parameter: its name (2), and 1 if the body assigns to it, else 0 (1)
    then the tokens.
"""
import env
import err
import fbuf
import gen
import kernel
import lex
import reg
import src
import typetab

SAVED_SIZE = 4096           # bytes of saved tokens in one module
MAX_DEPTH = 6               # inline calls inside inline calls: below src.MAX_SOURCES
MAX_LOCALS = 32             # names of locals one body can declare
MAX_OWNED = 64              # slots of the caller's frame the expansions under way own
MAX_ALIASES = 16            # parameters that stand for a variable while arguments are read

SCOPE_INLINE = 0xF0         # plus a level: the parameters and locals of that expansion
K_ALIAS = 9                 # a parameter that stands for the variable that is its value
SF_INLINE = kernel.SF_ZP    # function flags: `inline` and `interrupt`. These bits are
SF_INTERRUPT = kernel.SF_NOZP   # variables' own, and mean these for a function

R_END = 0
R_LINE = 2
R_FILE = 4
R_FLAGS = 6
R_WRITTEN = 7
R_PARAMS = 9
PARAM_SIZE = 3
PURE = 1
LAST_RETURN = 2
C_DOLLAR = 0x24
C_ZERO = 0x30

saved_start = 0             # the buffer, in text memory
saved_top = 0

local_name = [0] * MAX_LOCALS       # while save() reads a body: the locals it declares
local_count = 0
scan_flags = 0              # and what the record's flags will be
scan_written = 0            # the variable it assigns to, if it is pure
scan_index = 0              # the place of the current token in its statement
scan_first = 0              # the statement's first token, and its value
scan_first_value = 0
scan_brackets = 0           # how many "[" are open in the statement
scan_close = 0              # where the "]" closing a "[" at place 1 is, or 0

level = 0                   # the expansion whose body is being compiled; 0 for none
depth = 0                   # expansions under way: level, or more while arguments are read
expanding = [0] * (MAX_DEPTH + 1)   # by level: the function
wanted = [False] * (MAX_DEPTH + 1)  # its results are used
done = [reg.NONE] * (MAX_DEPTH + 1) # the label at its end
lazy = [False] * (MAX_DEPTH + 1)    # its `return` left the value as it was, as the result
sym_base = [0] * (MAX_DEPTH + 1)    # the first of its symbols
owned_base = [0] * (MAX_DEPTH + 1)  # the first of its slots in `owned`
alias_base = [0] * (MAX_DEPTH + 1)  # the first of its parameters in `alias`
outer = [0] * (MAX_DEPTH + 1)       # the level when it began, to go back to at its end
owned = [0] * MAX_OWNED
owned_count = 0
alias = [0] * MAX_ALIASES   # parameters standing for a variable whose arguments are still read
alias_count = 0


def init():
    global saved_start, saved_top, level, depth, owned_count, alias_count
    saved_start = kernel.text_reserve(SAVED_SIZE)
    saved_top = saved_start
    level = 0
    depth = 0
    owned_count = 0
    alias_count = 0


def word_at(p):
    return env.mem[p] | (env.mem[p + 1] << 8)


def set_word_at(p, value):
    env.mem[p] = value & 0xFF
    env.mem[p + 1] = (value >> 8) & 0xFF


def put(value):
    """Add a byte to the saved tokens."""
    global saved_top
    if saved_top == saved_start + SAVED_SIZE:
        err.fatal(err.E_INLINE_FULL)
    env.mem[saved_top] = value
    saved_top += 1


def put_word(value):
    put(value & 0xFF)
    put((value >> 8) & 0xFF)


def param(f, i):
    """Where the record of inline function `f` has its parameter `i`."""
    return kernel.sym_value[f] + R_PARAMS + i * PARAM_SIZE


def begin_record(f, line, file_name):
    """Start the record of inline function `f`, whose tokens follow."""
    kernel.sym_value[f] = saved_top
    put_word(0)
    put_word(line)
    put_word(file_name)
    put(0)
    put_word(0)
    for i in range(0, kernel.sym_params[f]):
        put_word(0)
        put(0)


# ---- Saving a body -----------------------------------------------------------------------

def parameter_number(f, name):
    """The number of the parameter of `f` called `name`, or 0xFF."""
    for i in range(0, kernel.sym_params[f]):
        if word_at(param(f, i)) == name:
            return i
    return 0xFF


def is_own(f, name):
    """True if `name` is a parameter of `f` or a local its body has declared so far."""
    if parameter_number(f, name) != 0xFF:
        return True
    for i in range(0, local_count):
        if local_name[i] == name:
            return True
    return False


def assigns(f, name):
    """The body assigns to `name`: mark it if it is a parameter."""
    i = parameter_number(f, name)
    if i != 0xFF:
        env.mem[param(f, i) + 2] = 1


def check_name(f, name):
    """A name the body uses that is not its own: it must be declared, and if `f` is exported,
    exported too (or an imported module), because an importer expands the body."""
    s, found = kernel.sym_lookup(name)
    if not found:
        err.fatal(err.E_UNDEFINED)
    if kernel.sym_flags[f] & kernel.SF_PUB != 0 and kernel.sym_scope[s] == kernel.SCOPE_MODULE \
            and kernel.sym_kind[s] != kernel.K_MODULE and kernel.sym_flags[s] & kernel.SF_PUB == 0:
        err.fatal(err.E_INLINE_PRIVATE)


def calls(name):
    """True if `name` followed by "(" is a call: it names a function (not a type or `lo`)."""
    s, found = kernel.sym_lookup(name)
    return found and kernel.sym_kind[s] == kernel.K_FUNC


def assignment(f, before, before_value):
    """The current token is an assignment operator, after `before` (with `before_value`). If the
    assigned variable is not a parameter or local, named alone, nor a variable of the program
    named alone or with one index (not a pointer's), or not the only such, the body is not pure."""
    global scan_flags, scan_written
    if before == lex.T_NAME:
        assigns(f, before_value)
    if scan_first == lex.T_VAR:
        return                          # a local's initial value
    target = 0
    indexed = False
    if scan_first == lex.T_NAME and scan_index == 1:
        target = scan_first_value
    elif scan_first == lex.T_NAME and scan_close != 0 and scan_close == scan_index - 1:
        target = scan_first_value
        indexed = True
    elif scan_first == lex.T_FOR and scan_index == 2:
        target = before_value
    if target == 0 or is_own(f, target):
        if target == 0 or indexed:
            scan_flags = scan_flags & ~PURE
        return
    s, _ = kernel.sym_lookup(target)            # check_name() has found it
    if kernel.sym_kind[s] != kernel.K_VAR or (indexed and typetab.is_pointer(kernel.sym_type[s])) \
            or (scan_written != 0 and scan_written != target):
        scan_flags = scan_flags & ~PURE
    else:
        scan_written = target


def opens_block(token):
    return token == lex.T_IF or token == lex.T_WHILE or token == lex.T_LOOP or token == lex.T_FOR \
        or token == lex.T_CASE or token == lex.T_CRITICAL


def save_token(at_line):
    """Save the current token, which is on line `at_line` or later. Returns its line."""
    while lex.line > at_line:
        step = lex.line - at_line
        if step > 0xFF:
            step = 0xFF
        put(lex.SAVED_LINE)
        put(step)
        at_line += step
    put(lex.tok)
    if lex.col > lex.MAX_COLUMN:
        put(lex.MAX_COLUMN)
    else:
        put(lex.col)
    if lex.tok == lex.T_NAME or lex.tok == lex.T_NUMBER:
        put_word(lex.value)
    elif lex.tok == lex.T_STRING:
        if lex.string_length > 0xFF:
            err.fatal(err.E_STRING_LONG)        # a saved string has a length of one byte
        put(lex.string_length)
        for i in range(0, lex.string_length):
            put(lex.string[i])
    return at_line


def save(f):
    """Save the body of inline function `f`, whose parameters are declared: its tokens from the
    current one up to the `end` that closes it, which is left as the current token. Looks at
    each token with the two before it, for what the record's flags and parameters say:
    - a parameter is assigned to if it is followed by an assignment operator, or is the first
      token of a statement and is followed by ",", or follows `for`, `->` or `@`;
    - the body is pure unless it has a name that is a function followed by "(", or a name after
      "." followed by "(", or `@`, or an assignment (outside a `var` declaration) to something
      other than a parameter or local named alone, or than one variable of the program named
      alone or with one index (`n = `, `t[i] += `, not a pointer's: assignment());
    - its last statement is its only `return` if it has one `return`, and the last statement
      at the outermost level starts with it.
    `asm`, `static` and `#if` are not allowed: ASM reads lines, not tokens, and the condition
    of an `#if` would have to be worked out as the tokens are read."""
    global local_count, scan_flags, scan_written, scan_index, scan_first, scan_first_value, \
        scan_brackets, scan_close
    begin_record(f, lex.line, src.name)
    for i in range(0, kernel.sym_params[f]):
        set_word_at(param(f, i), kernel.sym_name[kernel.local_base + i])
    local_count = 0
    scan_flags = PURE
    scan_written = 0
    scan_index = 0
    at_line = lex.line
    blocks = 0                  # how many blocks are open
    last = lex.T_NL             # the first token of the last statement at the outermost level
    before = lex.T_NL           # the token before the current one, and its value
    before_value = 0
    earlier = lex.T_NL          # the one before that
    returns = 0
    while lex.tok != lex.T_END or blocks > 0:
        token = lex.tok
        if token == lex.T_EOF:
            err.fatal(err.E_END_EXPECTED)
        if token == lex.T_ASM or token == lex.T_STATIC or token == lex.T_HASH_IF:
            err.fatal(err.E_INLINE_NOT_HERE)
        if scan_index == 0:
            scan_first = token
            scan_first_value = lex.value
            scan_brackets = 0
            scan_close = 0
            if blocks == 0:
                last = token
        if token == lex.T_NAME and before != lex.T_DOT:
            if before == lex.T_VAR:
                if local_count == MAX_LOCALS:
                    err.fatal(err.E_SLOTS_FULL)
                local_name[local_count] = lex.value
                local_count += 1
            elif not is_own(f, lex.value):
                check_name(f, lex.value)
            elif before == lex.T_FOR or before == lex.T_ARROW or before == lex.T_ADDRESS:
                assigns(f, lex.value)
        elif token >= lex.T_ASSIGN and token <= lex.T_SHR_ASSIGN:
            assignment(f, before, before_value)
        elif token == lex.T_COMMA and scan_index == 1 and before == lex.T_NAME:
            assigns(f, before_value)
        elif token == lex.T_LPAREN and before == lex.T_NAME:
            if earlier == lex.T_DOT or calls(before_value):
                scan_flags = scan_flags & ~PURE
        elif token == lex.T_ADDRESS:
            scan_flags = scan_flags & ~PURE
        elif token == lex.T_RETURN:
            returns += 1
        elif token == lex.T_LBRACKET:
            scan_brackets += 1
        elif token == lex.T_RBRACKET:
            scan_brackets -= 1
            if scan_brackets == 0 and scan_close == 0:
                scan_close = scan_index
        elif opens_block(token):
            blocks += 1
        elif token == lex.T_END or token == lex.T_UNTIL:
            blocks -= 1
        at_line = save_token(at_line)
        scan_index += 1
        if token == lex.T_NL:
            scan_index = 0
        earlier = before
        before = token
        before_value = lex.value
        lex.next()
    if returns == 1 and last == lex.T_RETURN:
        scan_flags = scan_flags | LAST_RETURN
    r = kernel.sym_value[f]
    set_word_at(r + R_END, saved_top)
    env.mem[r + R_FLAGS] = scan_flags
    if scan_flags & PURE != 0:
        set_word_at(r + R_WRITTEN, scan_written)


# ---- Interfaces --------------------------------------------------------------------------

def read_name(stream):
    """A name written as a string: its length, then its characters."""
    length, _ = kernel.get(stream)
    kernel.name_begin()
    for i in range(0, length):
        ch, _ = kernel.get(stream)
        kernel.name_add(ch)
    return kernel.name_end()


def write(stream, f):
    """Write the record of exported inline function `f` after its entry in the interface: the
    file name as a string, the line, the flags, each parameter's name and whether it is
    assigned to, then the tokens with each name as a string, and T_EOF."""
    r = kernel.sym_value[f]
    name = word_at(r + R_FILE)
    length = 0
    while env.mem[name + length] != 0:
        length += 1
    kernel.put(stream, length)
    for i in range(0, length):
        kernel.put(stream, env.mem[name + i])
    kernel.put_word(stream, word_at(r + R_LINE))
    kernel.put(stream, env.mem[r + R_FLAGS])
    if word_at(r + R_WRITTEN) == 0:
        kernel.put(stream, 0)
    else:
        kernel.put(stream, 1)
        kernel.put_name(stream, word_at(r + R_WRITTEN))
    for i in range(0, kernel.sym_params[f]):
        kernel.put_name(stream, word_at(param(f, i)))
        kernel.put(stream, env.mem[param(f, i) + 2])
    p = r + R_PARAMS + kernel.sym_params[f] * PARAM_SIZE
    while p < word_at(r + R_END):
        token = env.mem[p]
        kernel.put(stream, token)
        kernel.put(stream, env.mem[p + 1])
        size = 0
        if token == lex.T_NAME:
            kernel.put_name(stream, word_at(p + 2))
            size = 2
        elif token == lex.T_NUMBER:
            size = 2
        elif token == lex.T_STRING:
            size = 1 + env.mem[p + 2]
        for i in range(0, size):
            if token != lex.T_NAME:
                kernel.put(stream, env.mem[p + 2 + i])
        p += 2 + size
    kernel.put(stream, lex.T_EOF)


def read(stream, f):
    """Read the record that write() wrote for function `f`, which an import declares."""
    length, _ = kernel.get(stream)
    name = kernel.text_reserve(length + 1)
    for i in range(0, length):
        env.mem[name + i], _ = kernel.get(stream)
    env.mem[name + length] = 0
    begin_record(f, kernel.get_word(stream), name)
    env.mem[kernel.sym_value[f] + R_FLAGS], _ = kernel.get(stream)
    written, _ = kernel.get(stream)
    if written != 0:
        set_word_at(kernel.sym_value[f] + R_WRITTEN, read_name(stream))
    for i in range(0, kernel.sym_params[f]):
        set_word_at(param(f, i), read_name(stream))
        env.mem[param(f, i) + 2], _ = kernel.get(stream)
    while True:
        token, at_end = kernel.get(stream)
        if at_end or token > lex.SAVED_LINE:
            err.fatal(err.E_BAD_INTERFACE)
        if token == lex.T_EOF:
            break
        put(token)
        b, _ = kernel.get(stream)
        put(b)
        if token == lex.T_NAME:
            put_word(read_name(stream))
        elif token == lex.T_NUMBER:
            put_word(kernel.get_word(stream))
        elif token == lex.T_STRING:
            length, _ = kernel.get(stream)
            put(length)
            for i in range(0, length):
                b, _ = kernel.get(stream)
                put(b)
    set_word_at(kernel.sym_value[f] + R_END, saved_top)


# ---- Expansions --------------------------------------------------------------------------

def lookup(name):
    """What a plain `name` means here (kernel.sym_lookup, as seen from an expansion's body): a
    parameter or local of the expansion, else a symbol of the module that declared its function
    (for an imported one, what its interface declares: what it exports, and the modules it
    imports, decl.imported_module()), or one the language declares. A parameter that stands for
    a variable means that variable."""
    if level == 0:
        return kernel.sym_lookup(name)
    scope = SCOPE_INLINE + level
    home = kernel.sym_scope[expanding[level]]
    s = kernel.name_word(name + kernel.N_SYMBOL)
    while s != kernel.NO_SYM and kernel.sym_scope[s] != scope and kernel.sym_scope[s] != home \
            and kernel.sym_scope[s] != kernel.SCOPE_PREDECLARED:
        s = kernel.sym_link[s]
    if s != kernel.NO_SYM and kernel.sym_kind[s] == K_ALIAS:
        s = kernel.sym_value[s]
    return s, s != kernel.NO_SYM


def local_scope():
    """The scope a local declared now goes to."""
    if level == 0:
        return kernel.SCOPE_LOCAL
    return SCOPE_INLINE + level


def own_slot(size):
    """A temporary of the caller's frame, owned by the newest expansion until it ends."""
    global owned_count
    if owned_count == MAX_OWNED:
        err.fatal(err.E_SLOTS_FULL)
    n = reg.temp(size)
    owned[owned_count] = n
    owned_count += 1
    return n


def slot_name(name, n):
    """The name of slot `n`, a local `name` of an inline function at one of its expansions:
    `name$n`, which no source name can be and no other slot has."""
    kernel.name_begin()
    for i in range(0, kernel.name_length(name)):
        kernel.name_add(kernel.name_char(name, i))
    kernel.name_add(C_DOLLAR)
    if n >= 100:
        kernel.name_add(C_ZERO + n // 100)
    if n >= 10:
        kernel.name_add(C_ZERO + n // 10 % 10)
    kernel.name_add(C_ZERO + n % 10)
    return kernel.name_end()


def enter(f, results_wanted):
    """A call of inline function `f` begins; its arguments are read next. Unless its body is
    pure and assigns to no variable of the program, it could change variables that parameters
    of the calls whose arguments are being read stand for. Only expansions whose bodies are
    being compiled count for recursion: `f(f(x))` is two calls, one inside the other's arguments."""
    global depth
    if env.mem[kernel.sym_value[f] + R_FLAGS] & PURE == 0 or word_at(kernel.sym_value[f] + R_WRITTEN) != 0:
        copy_aliases()
    d = level
    while d > 0:
        if expanding[d] == f:
            err.fatal(err.E_INLINE_RECURSIVE)
        d = outer[d]
    if depth == MAX_DEPTH:
        err.fatal(err.E_INLINE_DEEP)
    depth += 1
    outer[depth] = level
    expanding[depth] = f
    wanted[depth] = results_wanted
    lazy[depth] = False
    done[depth] = fbuf.new_label()
    sym_base[depth] = kernel.sym_count
    owned_base[depth] = owned_count
    alias_base[depth] = alias_count


def argument_symbol(f, i):
    """The argument for parameter `i` of the newest expansion is the newest operand, a value
    that can be given to it: make the parameter's symbol. Where the body does not assign to it,
    the parameter stands for the argument if that is a constant, a slot of the caller's frame,
    or (if the body is pure and does not assign to it) a variable of the program, which must
    not be at a fixed address; a variable must be of the parameter's own type. It is the
    constant, or that variable, and no slot is used. Otherwise it is a slot that the newest
    expansion owns, and the argument is stored there. The operand is used up."""
    global alias_count
    r = kernel.sym_value[f]
    t = kernel.member_type[kernel.sym_members[f] + i]
    j = reg.depth - 1
    kind = kernel.K_LOCAL
    value = 0
    stands = False              # for a variable
    if env.mem[param(f, i) + 2] == 0:
        if reg.op_kind[j] == reg.O_CONST:
            kind = kernel.K_CONST
            value = reg.op_value[j]
        elif reg.op_kind[j] == reg.O_VAR and reg.op_mode[j] == reg.M_DIRECT and reg.op_value[j] == 0 \
                and reg.op_flags[j] & (reg.F_TEMP | reg.F_DATA) == 0 and reg.op_type[j] == t \
                and reg.op_symbol[j] != kernel.NO_OBJ and reg.op_kind[j + reg.INDEX] == 0:
            if reg.op_symbol[j] == reg.own and reg.op_slot[j] != fbuf.NO_SLOT:
                value = reg.op_slot[j]
                stands = True
            elif reg.op_var[j] != kernel.NO_SYM and env.mem[r + R_FLAGS] & PURE != 0 \
                    and kernel.sym_name[reg.op_var[j]] != word_at(r + R_WRITTEN):
                kind = K_ALIAS
                value = reg.op_var[j]
                stands = True
    if kind == kernel.K_LOCAL and not stands:
        value = own_slot(typetab.size(t))
        gen.local(t, value)
        reg.swap()
        gen.store()
    else:
        reg.pop()
    s = kernel.sym_add(SCOPE_INLINE + depth, word_at(param(f, i)), kind)
    kernel.sym_type[s] = t
    kernel.sym_value[s] = value
    if stands:
        if alias_count == MAX_ALIASES:
            err.fatal(err.E_OPERANDS_FULL)
        alias[alias_count] = s
        alias_count += 1


def copy_aliases():
    """A call is about to be made, or an expansion to begin, while the arguments of inline calls
    are being read: it could change a variable that a parameter already stands for. Each such
    parameter becomes a slot that holds the variable's value now. So does each argument that
    waits for a register (gen.protect())."""
    global alias_count
    gen.protect()
    for n in range(0, alias_count):
        s = alias[n]
        t = kernel.sym_type[s]
        slot = own_slot(typetab.size(t))
        gen.local(t, slot)
        if kernel.sym_kind[s] == K_ALIAS:
            gen.variable(kernel.sym_value[s])
        else:
            gen.local(t, kernel.sym_value[s])
        gen.store()
        kernel.sym_kind[s] = kernel.K_LOCAL
        kernel.sym_value[s] = slot
    alias_count = 0


def body_begin(f):
    """The arguments of the newest expansion are read: replay the body of `f`."""
    global level, alias_count
    alias_count = alias_base[depth]
    level = depth
    r = kernel.sym_value[f]
    src.open_saved(r + R_PARAMS + kernel.sym_params[f] * PARAM_SIZE, word_at(r + R_END),
                   word_at(r + R_FILE), word_at(r + R_LINE))


def leaves_operand():
    """At a `return` of the newest expansion: True if its value may stay as the operand it is,
    which is then the expansion's result, with no load and no jump. That is so if the results
    are wanted, there is one, and this `return` is the body's last statement and its only one,
    and the expansion owns no slot that the operand could use."""
    f = expanding[level]
    return wanted[level] and kernel.sym_results[f] == 1 \
        and env.mem[kernel.sym_value[f] + R_FLAGS] & LAST_RETURN != 0 \
        and owned_count == owned_base[level]


def leave():
    """The newest expansion has ended: its symbols go, and its slots are free again."""
    global level, depth, owned_count
    while kernel.sym_count > sym_base[depth]:
        kernel.sym_count -= 1
        kernel.name_set_word(kernel.sym_name[kernel.sym_count] + kernel.N_SYMBOL,
                             kernel.sym_link[kernel.sym_count])
    while owned_count > owned_base[depth]:
        owned_count -= 1
        reg.slot_busy[owned[owned_count]] = False
    level = outer[depth]
    depth -= 1
