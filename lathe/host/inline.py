"""INLINE: the saved tokens of `inline` functions, and the state of the expansions under way.

Owns
- the saved tokens (docs/code-model.md, "Inline functions"): an `inline` function's body is
  not compiled where it is declared. save() reads it as tokens up to its `end` and keeps them,
  for the whole module, in a buffer of SAVED_SIZE bytes of token memory, in the form lex.py
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

SAVED_SIZE = 2048           # bytes of saved tokens in one module
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

saved_start = 0             # the buffer, in token memory (kernel.token_byte())
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
done = bytearray(MAX_DEPTH + 1)     # the label at its end
lazy = [False] * (MAX_DEPTH + 1)    # its `return` left the value as it was, as the result
sym_base = [0] * (MAX_DEPTH + 1)    # the first of its symbols
owned_base = bytearray(MAX_DEPTH + 1)   # the first of its slots in `owned`
alias_base = bytearray(MAX_DEPTH + 1)   # the first of its parameters in `alias`
outer = bytearray(MAX_DEPTH + 1)        # the level when it began, to go back to at its end
owned = bytearray(MAX_OWNED)        # slot numbers
owned_count = 0
alias = [0] * MAX_ALIASES   # parameters standing for a variable whose arguments are still read
alias_count = 0

MAX_USES = 32               # names of other entries one exported body names (write_uses())
use_module = [0] * MAX_USES     # the module's name, 0 for the body's own module
use_name = [0] * MAX_USES
use_count = 0


def init():
    global saved_start, saved_top, level, depth, owned_count, alias_count
    saved_start = kernel.token_start()
    saved_top = saved_start
    level = 0
    depth = 0
    owned_count = 0
    alias_count = 0


def word_at(p):
    return kernel.token_byte(p) | (kernel.token_byte(p + 1) << 8)


def set_word_at(p, value):
    kernel.set_token_byte(p, value & 0xFF)
    kernel.set_token_byte(p + 1, (value >> 8) & 0xFF)


def put(value):
    """Add a byte to the saved tokens."""
    global saved_top
    if saved_top == saved_start + SAVED_SIZE:
        err.fatal(err.E_INLINE_FULL)
    kernel.set_token_byte(saved_top, value)
    saved_top += 1


def put_word(value):
    put(value & 0xFF)
    put((value >> 8) & 0xFF)


def param(f, i):
    """Where the record of inline function `f` has its parameter `i`."""
    return kernel.value_of(f) + R_PARAMS + i * PARAM_SIZE


def begin_record(f, line, file_name):
    """Start the record of inline function `f`, whose tokens follow."""
    kernel.set_word(f, kernel.C_VALUE, saved_top)
    put_word(0)
    put_word(line)
    put_word(file_name)
    put(0)
    put_word(0)
    for i in range(0, kernel.params_of(f)):
        put_word(0)
        put(0)


# ---- Saving a body -----------------------------------------------------------------------

def parameter_number(f, name):
    """The number of the parameter of `f` called `name`, or 0xFF."""
    for i in range(0, kernel.params_of(f)):
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
        kernel.set_token_byte(param(f, i) + 2, 1)


def check_name(f, name):
    """A name the body uses that is not its own: it must be declared, and if `f` is exported,
    exported too (or an imported module), because an importer expands the body."""
    s, found = kernel.sym_lookup(name)
    if not found:
        err.fatal(err.E_UNDEFINED)
    if kernel.flags_of(f) & kernel.SF_PUB != 0 and kernel.scope_of(s) == kernel.SCOPE_MODULE \
            and kernel.kind_of(s) != kernel.K_MODULE and kernel.flags_of(s) & kernel.SF_PUB == 0:
        err.fatal(err.E_INLINE_PRIVATE)


def calls(name):
    """True if `name` followed by "(" is a call: it names a function (not a type or `lo`)."""
    s, found = kernel.sym_lookup(name)
    return found and kernel.kind_of(s) == kernel.K_FUNC


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
    if kernel.kind_of(s) != kernel.K_VAR or (indexed and typetab.is_pointer(kernel.type_of(s))) \
            or (scan_written != 0 and scan_written != target):
        scan_flags = scan_flags & ~PURE
    else:
        scan_written = target


def opens_block(token):
    return token == lex.T_IF or token == lex.T_WHILE or token == lex.T_LOOP or token == lex.T_FOR \
        or token == lex.T_CASE or token == lex.T_CRITICAL or token == lex.T_WITH


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
            put(lex.string_byte(i))
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
    for i in range(0, kernel.params_of(f)):
        set_word_at(param(f, i), kernel.word_of(kernel.local_base + i, kernel.C_NAME))
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
    named = kernel.NO_SYM       # the module the token before names, if it does
    dotted = kernel.NO_SYM      # the module named before the "." before, if there is one
    returns = 0
    while lex.tok != lex.T_END or blocks > 0:
        token = lex.tok
        if token == lex.T_EOF:
            err.fatal(err.E_END_EXPECTED)
        if token == lex.T_NAME and dotted != kernel.NO_SYM and kernel.flags_of(dotted) & kernel.SF_LIST != 0:
            kernel.module_find(dotted, lex.value)       # `m.name`: in m's list (error 101)
        if token == lex.T_ASM or token == lex.T_STATIC or token == lex.T_HASH_IF \
                or token == lex.T_WITH:
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
        dotted = kernel.NO_SYM
        if token == lex.T_DOT:
            dotted = named
        named = kernel.NO_SYM
        if token == lex.T_NAME and before != lex.T_DOT and not is_own(f, lex.value):
            s, found = kernel.sym_lookup(lex.value)
            if found and kernel.kind_of(s) == kernel.K_MODULE:
                named = s
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
    r = kernel.value_of(f)
    set_word_at(r + R_END, saved_top)
    kernel.set_token_byte(r + R_FLAGS, scan_flags)
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
    r = kernel.value_of(f)
    name = word_at(r + R_FILE)
    length = 0
    while env.mem[name + length] != 0:
        length += 1
    kernel.put(stream, length)
    for i in range(0, length):
        kernel.put(stream, env.mem[name + i])
    kernel.put_word(stream, word_at(r + R_LINE))
    kernel.put(stream, kernel.token_byte(r + R_FLAGS))
    if word_at(r + R_WRITTEN) == 0:
        kernel.put(stream, 0)
    else:
        kernel.put(stream, 1)
        kernel.put_name(stream, word_at(r + R_WRITTEN))
    for i in range(0, kernel.params_of(f)):
        kernel.put_name(stream, word_at(param(f, i)))
        kernel.put(stream, kernel.token_byte(param(f, i) + 2))
    p = r + R_PARAMS + kernel.params_of(f) * PARAM_SIZE
    while p < word_at(r + R_END):
        token = kernel.token_byte(p)
        kernel.put(stream, token)
        kernel.put(stream, kernel.token_byte(p + 1))
        size = 0
        if token == lex.T_NAME:
            kernel.put_name(stream, word_at(p + 2))
            size = 2
        elif token == lex.T_NUMBER:
            size = 2
        elif token == lex.T_STRING:
            size = 1 + kernel.token_byte(p + 2)
        for i in range(0, size):
            if token != lex.T_NAME:
                kernel.put(stream, kernel.token_byte(p + 2 + i))
        p += 2 + size
    kernel.put(stream, lex.T_EOF)


def skip_name(stream):
    """Pass over a name written as a string, making no name of it."""
    length, _ = kernel.get(stream)
    for i in range(0, length):
        kernel.get(stream)


def skip(stream, params):
    """Pass over the record write() wrote for an inline function of `params` parameters that the
    importer does not want (decl.read_function()): nothing is kept of it."""
    skip_name(stream)
    kernel.get_word(stream)
    kernel.get(stream)
    written, _ = kernel.get(stream)
    if written != 0:
        skip_name(stream)
    for i in range(0, params):
        skip_name(stream)
        kernel.get(stream)
    while True:
        token, at_end = kernel.get(stream)
        if at_end or token > lex.SAVED_LINE:
            err.fatal(err.E_BAD_INTERFACE)
        if token == lex.T_EOF:
            break
        kernel.get(stream)
        if token == lex.T_NAME:
            skip_name(stream)
        elif token == lex.T_NUMBER:
            kernel.get_word(stream)
        elif token == lex.T_STRING:
            skip_name(stream)       # a length and that many bytes, as a name is written


def token_size(p):
    """The bytes a saved token at `p` has after its token and column bytes."""
    token = kernel.token_byte(p)
    if token == lex.T_NAME or token == lex.T_NUMBER:
        return 2
    if token == lex.T_STRING:
        return 1 + kernel.token_byte(p + 2)
    return 0


def use(owner, name):
    """write_uses() found the body names `name` of module `owner` (its name, or 0 for its own
    module): keep it, once."""
    global use_count
    for i in range(0, use_count):
        if use_module[i] == owner and use_name[i] == name:
            return
    if use_count == MAX_USES:
        err.fatal(err.E_WANTS_FULL)
    use_module[use_count] = owner
    use_name[use_count] = name
    use_count += 1


def write_uses(stream, f):
    """After the LI_USES entry's name: what the body of exported inline function `f` names that an
    importer must read with it, so that it finds them though its list does not name them
    (decl.read_uses()). That is each function, constant and variable of the module that it names
    by a plain name, its own parameters and locals apart, and each `m.name` of a module m that
    the module imports: their number, then each as a module name (empty for this module) and a
    name. Types and modules are not there: an import reads all of them."""
    global local_count, use_count
    local_count = 0
    use_count = 0
    r = kernel.value_of(f)
    last = word_at(r + R_END)
    p = r + R_PARAMS + kernel.params_of(f) * PARAM_SIZE
    before = lex.T_NL
    while p < last:
        token = kernel.token_byte(p)
        if token == lex.T_NAME and before != lex.T_DOT:
            name = word_at(p + 2)
            if before == lex.T_VAR:
                local_name[local_count] = name
                local_count += 1
            elif not is_own(f, name):
                s, found = kernel.sym_lookup(name)
                q = p + 2 + token_size(p)
                if found and kernel.kind_of(s) == kernel.K_MODULE:
                    if q < last and kernel.token_byte(q) == lex.T_DOT:
                        q += 2
                        if q < last and kernel.token_byte(q) == lex.T_NAME:
                            use(name, word_at(q + 2))
                elif found and kernel.scope_of(s) == kernel.SCOPE_MODULE \
                        and kernel.kind_of(s) >= kernel.K_FUNC and kernel.kind_of(s) <= kernel.K_VAR:
                    use(0, name)
        if token != lex.SAVED_LINE:
            before = token
        p += 2 + token_size(p)
    kernel.put(stream, use_count)
    for i in range(0, use_count):
        if use_module[i] == 0:
            kernel.put(stream, 0)
        else:
            kernel.put_name(stream, use_module[i])
        kernel.put_name(stream, use_name[i])


def read(stream, f):
    """Read the record that write() wrote for function `f`, which an import declares."""
    length, _ = kernel.get(stream)
    name = kernel.text_reserve(length + 1)
    for i in range(0, length):
        env.mem[name + i], _ = kernel.get(stream)
    env.mem[name + length] = 0
    begin_record(f, kernel.get_word(stream), name)
    flags, _ = kernel.get(stream)
    kernel.set_token_byte(kernel.value_of(f) + R_FLAGS, flags)
    written, _ = kernel.get(stream)
    if written != 0:
        set_word_at(kernel.value_of(f) + R_WRITTEN, read_name(stream))
    for i in range(0, kernel.params_of(f)):
        set_word_at(param(f, i), read_name(stream))
        assigned, _ = kernel.get(stream)
        kernel.set_token_byte(param(f, i) + 2, assigned)
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
    set_word_at(kernel.value_of(f) + R_END, saved_top)


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
    home = kernel.scope_of(expanding[level])
    s = kernel.name_symbol(name)
    while s != kernel.NO_SYM and kernel.scope_of(s) != scope and kernel.scope_of(s) != home \
            and kernel.scope_of(s) != kernel.SCOPE_PREDECLARED:
        s = kernel.word_of(s, kernel.C_LINK)
    if home != kernel.SCOPE_MODULE and (s == kernel.NO_SYM or kernel.scope_of(s) == kernel.SCOPE_PREDECLARED):
        # An imported module's symbol may be frozen, or thawed under another entry of the name.
        t, found = kernel.sym_find(home, name)
        if found:
            s = t
    if s != kernel.NO_SYM and kernel.kind_of(s) == K_ALIAS:
        s = kernel.value_of(s)
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
    if kernel.token_byte(kernel.value_of(f) + R_FLAGS) & PURE == 0 or word_at(kernel.value_of(f) + R_WRITTEN) != 0:
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
    r = kernel.value_of(f)
    t = kernel.member_type_of(kernel.word_of(f, kernel.C_MEMBERS) + i)
    j = reg.depth - 1
    kind = kernel.K_LOCAL
    value = 0
    stands = False              # for a variable
    if kernel.token_byte(param(f, i) + 2) == 0:
        if reg.op_kind[j] == reg.O_CONST:
            kind = kernel.K_CONST
            value = reg.op_value[j]
        elif reg.op_kind[j] == reg.O_VAR and reg.op_mode[j] == reg.M_DIRECT and reg.op_value[j] == 0 \
                and reg.op_flags[j] & (reg.F_TEMP | reg.F_DATA) == 0 and reg.op_type[j] == t \
                and reg.op_symbol[j] != kernel.NO_OBJ and reg.op_kind[j + reg.INDEX] == 0:
            if reg.op_symbol[j] == reg.own and reg.op_slot[j] != fbuf.NO_SLOT:
                value = reg.op_slot[j]
                stands = True
            elif reg.op_var[j] != kernel.NO_SYM and kernel.token_byte(r + R_FLAGS) & PURE != 0 \
                    and kernel.word_of(reg.op_var[j], kernel.C_NAME) != word_at(r + R_WRITTEN):
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
    kernel.set_byte(s, kernel.C_TYPE, t)
    kernel.set_word(s, kernel.C_VALUE, value)
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
        t = kernel.type_of(s)
        slot = own_slot(typetab.size(t))
        gen.local(t, slot)
        if kernel.kind_of(s) == K_ALIAS:
            gen.variable(kernel.value_of(s))
        else:
            gen.local(t, kernel.value_of(s))
        gen.store()
        kernel.set_byte(s, kernel.C_KIND, kernel.K_LOCAL)
        kernel.set_word(s, kernel.C_VALUE, slot)
    alias_count = 0


def copies_due():
    """True if copy_aliases() would copy something."""
    return alias_count > 0 or gen.must_protect()


def body_begin(f):
    """The arguments of the newest expansion are read: replay the body of `f`."""
    global level, alias_count
    alias_count = alias_base[depth]
    level = depth
    r = kernel.value_of(f)
    src.open_saved(r + R_PARAMS + kernel.params_of(f) * PARAM_SIZE, word_at(r + R_END),
                   word_at(r + R_FILE), word_at(r + R_LINE))


def leaves_operand():
    """At a `return` of the newest expansion: True if its value may stay as the operand it is,
    which is then the expansion's result, with no load and no jump. That is so if the results
    are wanted, there is one, and this `return` is the body's last statement and its only one,
    and the expansion owns no slot that the operand could use."""
    f = expanding[level]
    return wanted[level] and kernel.byte_of(f, kernel.C_RESULTS) == 1 \
        and kernel.token_byte(kernel.value_of(f) + R_FLAGS) & LAST_RETURN != 0 \
        and owned_count == owned_base[level]


def leave():
    """The newest expansion has ended: its symbols go, and its slots are free again."""
    global level, depth, owned_count
    kernel.sym_release(sym_base[depth])
    while owned_count > owned_base[depth]:
        owned_count -= 1
        reg.slot_busy[owned[owned_count]] = False
    level = outer[depth]
    depth -= 1
