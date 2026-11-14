"""DECL: declarations, and interface files.

Owns the parsing of a module from its first line to its last, apart from what is inside a
function body (STMT) or a value (EXPR); what the kernel's symbol columns mean for each kind
of symbol; the names the language declares itself; and the interface file, which is written
from the symbol table when the module ends and read back into it by `import`. The format of
the interface file is in README.md.

So far a declaration is an `extern` function or a function without parameters or results.
"""
import err
import expr
import gen
import kernel
import lex
import out
import stmt
import typetab

# ---- Interface files ---------------------------------------------------------------------

LI_VERSION = 1
LI_END = 0              # entry kinds
LI_FUNC = 1
LI_EXTERN = 1           # function flag: at a fixed address, which follows the flags
LI_POINTER = 0x10       # type: a pointer to the type that follows; a basic type is its number

MAX_DIRS = 8
C_SLASH = 0x2F
C_UPPER_L = 0x4C
C_UPPER_I = 0x49
ENDING = b".li"

directory = [0] * MAX_DIRS      # pointers to the names of the directories to look in, in order
directory_count = 0

# ---- Predeclared names -------------------------------------------------------------------

REGISTERS = b"a x y ax ay xy c "            # in the order of gen.REG_A to gen.REG_C
CONSTANTS = b"false true "                  # the bool constants, in the order of their values
REGISTER_COUNT = 8
REGISTER_PARTS = b"\x00\x01\x02\x04\x03\x05\x06\x08"   # which of A, X, Y and carry each uses
C_SPACE = 0x20

register_name = [0] * REGISTER_COUNT


def init():
    """Declare what the language declares. Needs the keywords to have their tokens."""
    global directory_count
    directory_count = 0
    register = gen.REG_A
    kernel.name_begin()
    for i in range(0, len(REGISTERS)):
        if REGISTERS[i] == C_SPACE:
            register_name[register] = kernel.name_end()
            register += 1
            kernel.name_begin()
        else:
            kernel.name_add(REGISTERS[i])
    value = 0
    for i in range(0, len(CONSTANTS)):
        if CONSTANTS[i] == C_SPACE:
            s = kernel.sym_add(kernel.SCOPE_PREDECLARED, kernel.name_end(), kernel.K_CONST)
            kernel.sym_type[s] = typetab.BOOL_TYPE
            kernel.sym_value[s] = value
            value += 1
            kernel.name_begin()
        else:
            kernel.name_add(CONSTANTS[i])


def directory_add(name):
    """Interfaces are looked for in the directory whose name is at `name`, after those added before."""
    global directory_count
    if directory_count == MAX_DIRS:
        err.fatal(err.E_DIRS_FULL)
    directory[directory_count] = name
    directory_count += 1


def interface_path(directory_name, module_name):
    """Pointer to the file name of a module's interface in a directory."""
    kernel.path_begin()
    kernel.path_add_text(directory_name)
    kernel.path_add(C_SLASH)
    kernel.path_add_name(module_name)
    for i in range(0, len(ENDING)):
        kernel.path_add(ENDING[i])
    return kernel.path_end()


# ---- Writing the interface ---------------------------------------------------------------

def write_type(stream, t):
    while typetab.is_pointer(t):
        kernel.put(stream, LI_POINTER)
        t = typetab.base(t)
    kernel.put(stream, t)


def write_members(stream, first, count):
    kernel.put(stream, count)
    for m in range(first, first + count):
        write_type(stream, kernel.member_type[m])
        kernel.put(stream, kernel.member_value[m])


def write_function(stream, s):
    kernel.put(stream, LI_FUNC)
    kernel.put_name(stream, kernel.sym_name[s])
    if kernel.sym_flags[s] & kernel.SF_EXTERN != 0:
        kernel.put(stream, LI_EXTERN)
        kernel.put_word(stream, kernel.sym_value[s])
    else:
        kernel.put(stream, 0)
    write_members(stream, kernel.sym_members[s], kernel.sym_params[s])
    write_members(stream, kernel.sym_members[s] + kernel.sym_params[s], kernel.sym_results[s])


def write_interface(directory_name):
    """Write what the module exports to its interface file in the directory named."""
    stream, ok = kernel.open_out(interface_path(directory_name, kernel.module_name[0]))
    if not ok:
        err.fatal(err.E_CREATE)
    kernel.put(stream, C_UPPER_L)
    kernel.put(stream, C_UPPER_I)
    kernel.put(stream, LI_VERSION)
    kernel.put_name(stream, kernel.module_name[0])
    for s in range(0, kernel.sym_count):
        if kernel.sym_scope[s] == kernel.SCOPE_MODULE and kernel.sym_flags[s] & kernel.SF_PUB != 0:
            write_function(stream, s)
    kernel.put(stream, LI_END)
    kernel.close(stream)


# ---- Reading an interface ----------------------------------------------------------------

def read_name(stream):
    length, _ = kernel.get(stream)
    kernel.name_begin()
    for i in range(0, length):
        ch, _ = kernel.get(stream)
        kernel.name_add(ch)
    return kernel.name_end()


def read_type(stream):
    pointers = 0
    t, _ = kernel.get(stream)
    while t == LI_POINTER:
        pointers += 1
        t, _ = kernel.get(stream)
    if t < typetab.BYTE_TYPE or t > typetab.BOOL_TYPE:
        err.fatal(err.E_BAD_INTERFACE)
    while pointers > 0:
        t = typetab.pointer_to(t)
        pointers -= 1
    return t


def read_members(stream):
    """Read parameters or results as members of the newest symbol. Returns how many."""
    count, _ = kernel.get(stream)
    for i in range(0, count):
        t = read_type(stream)
        register, _ = kernel.get(stream)
        kernel.member_add(t, register)
    return count


def read_function(stream, scope):
    s = kernel.sym_add(scope, read_name(stream), kernel.K_FUNC)
    flags, _ = kernel.get(stream)
    kernel.sym_flags[s] = kernel.SF_PUB
    if flags & LI_EXTERN != 0:
        kernel.sym_flags[s] = kernel.SF_PUB | kernel.SF_EXTERN
        kernel.sym_value[s] = kernel.get_word(stream)
    kernel.sym_params[s] = read_members(stream)
    kernel.sym_results[s] = read_members(stream)


def open_interface(name):
    """The interface of the module called `name`, from the first directory that has one."""
    for i in range(0, directory_count):
        stream, ok = kernel.open_in(interface_path(directory[i], name))
        if ok:
            return stream
    err.fatal(err.E_NO_INTERFACE)
    return 0


def read_interface(number):
    """Declare what module number `number` exports, as symbols in the scope of that number."""
    stream = open_interface(kernel.module_name[number])
    letter_l, _ = kernel.get(stream)
    letter_i, _ = kernel.get(stream)
    version, _ = kernel.get(stream)
    if letter_l != C_UPPER_L or letter_i != C_UPPER_I or version != LI_VERSION:
        err.fatal(err.E_BAD_INTERFACE)
    if read_name(stream) != kernel.module_name[number]:
        err.fatal(err.E_BAD_INTERFACE)
    while True:
        kind, at_end = kernel.get(stream)
        if at_end or (kind != LI_END and kind != LI_FUNC):
            err.fatal(err.E_BAD_INTERFACE)      # a file cut short has no LI_END
        if kind == LI_END:
            break
        read_function(stream, number)
    kernel.close(stream)


# ---- The module and its imports ----------------------------------------------------------

def module_line():
    """"module" name NL. The name must be the file's."""
    lex.expect(lex.T_MODULE, err.E_MODULE_EXPECTED)
    if lex.tok != lex.T_NAME:
        err.fatal(err.E_NAME_EXPECTED)
    if lex.value != kernel.module_name[0]:
        err.fatal(err.E_MODULE_NAME)
    lex.next()
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)
    out.begin_module(gen.cpu, kernel.module_name[0])


def import_line():
    """"import" name NL. The module's name becomes a symbol; what it exports is declared in
    a scope of its own and reached as name.member."""
    lex.next()
    if lex.tok != lex.T_NAME:
        err.fatal(err.E_NAME_EXPECTED)
    if lex.value == kernel.module_name[0]:
        err.fatal(err.E_SELF_IMPORT)
    s = kernel.sym_add(kernel.SCOPE_MODULE, lex.value, kernel.K_MODULE)
    kernel.sym_value[s] = kernel.module_add(lex.value)
    read_interface(kernel.sym_value[s])
    out.imported(lex.value)
    lex.next()
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)


# ---- Functions ---------------------------------------------------------------------------

def function_symbol(flags):
    """The name after "func": declare it as a function. Returns the symbol."""
    if lex.tok != lex.T_NAME:
        err.fatal(err.E_NAME_EXPECTED)
    s = kernel.sym_add(kernel.SCOPE_MODULE, lex.value, kernel.K_FUNC)
    kernel.sym_flags[s] = flags
    lex.next()
    return s


def register():
    """register = "a" | "x" | "y" | "ax" | "ay" | "xy" | "c". These are not keywords: they
    are names with this meaning only here. Returns the register; the token is not passed over."""
    if lex.tok == lex.T_NAME:
        for r in range(gen.REG_A, REGISTER_COUNT):
            if lex.value == register_name[r]:
                return r
    err.fatal(err.E_REGISTER_EXPECTED)
    return gen.REG_NONE


def register_suits(r, t):
    """True if a value of type `t` can be in register `r`."""
    if r == gen.REG_C:
        return t == typetab.BOOL_TYPE
    if r <= gen.REG_Y:
        return typetab.size(t) == 1
    return typetab.size(t) == 2


def bound_member(used):
    """type "in" register: a parameter or result of the newest symbol. `used` says which of
    A, X, Y and carry are taken already; returns that with this member's added."""
    t = expr.type_spec()
    lex.expect(lex.T_IN, err.E_IN_EXPECTED)
    r = register()
    if not register_suits(r, t):
        err.fatal(err.E_REG_TYPE)
    if used & REGISTER_PARTS[r] != 0:
        err.fatal(err.E_REG_USED)
    lex.next()
    kernel.member_add(t, r)
    return used | REGISTER_PARTS[r]


def register_parameters():
    """[ regParam { "," regParam } ] ")", after the "(". regParam = name ":" type "in" register.
    Returns how many."""
    count = 0
    used = 0
    if lex.tok != lex.T_RPAREN:
        while True:
            if lex.tok != lex.T_NAME:
                err.fatal(err.E_NAME_EXPECTED)
            lex.next()
            lex.expect(lex.T_COLON, err.E_COLON_EXPECTED)
            used = bound_member(used)
            count += 1
            if lex.tok != lex.T_COMMA:
                break
            lex.next()
    lex.expect(lex.T_RPAREN, err.E_RPAREN_EXPECTED)
    return count


def register_results():
    """[ ":" regResult [ "," regResult ] ]. regResult = type "in" register. Returns how many."""
    if lex.tok != lex.T_COLON:
        return 0
    lex.next()
    used = bound_member(0)
    if lex.tok != lex.T_COMMA:
        return 1
    lex.next()
    bound_member(used)
    return 2


def extern_declaration(flags):
    """externDecl = "extern" regHead "at" constExpr NL."""
    lex.next()
    lex.expect(lex.T_FUNC, err.E_FUNC_EXPECTED)
    s = function_symbol(flags | kernel.SF_EXTERN)
    lex.expect(lex.T_LPAREN, err.E_LPAREN_EXPECTED)
    kernel.sym_params[s] = register_parameters()
    kernel.sym_results[s] = register_results()
    lex.expect(lex.T_AT, err.E_AT_EXPECTED)
    kernel.sym_value[s] = expr.constant_number()
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)


def object_flags(s):
    """The flags of function `s` as its FUNC record has them."""
    if kernel.sym_flags[s] & kernel.SF_PUB != 0:
        return out.FUNC_EXPORTED
    return 0


def function_declaration(flags):
    """funcDecl = funcHead NL body "end" NL, so far without parameters or results."""
    lex.next()
    s = function_symbol(flags)
    # The scope begins once the function's own name is declared and the token after it has
    # been read: every name made from here on is a parameter's or a local's.
    kernel.scope_begin()
    lex.expect(lex.T_LPAREN, err.E_LPAREN_EXPECTED)
    if lex.tok != lex.T_RPAREN:
        err.fatal(err.E_UNSUPPORTED)
    lex.next()
    if lex.tok == lex.T_COLON:
        err.fatal(err.E_UNSUPPORTED)
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)
    symbol = gen.object_symbol(s)
    gen.function_begin()
    stmt.body()
    if lex.tok != lex.T_END:
        err.fatal(err.E_END_EXPECTED)
    gen.function_end(symbol, object_flags(s))
    # The scope ends before "end" is passed over, so that no token read after it can be
    # taken for one of the function's own names.
    kernel.scope_end()
    lex.next()
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)


def starts_later_declaration(token):
    """True for the first token of a declaration not done yet."""
    if token == lex.T_CONST or token == lex.T_TYPE or token == lex.T_ENUM or token == lex.T_VAR:
        return True
    if token == lex.T_STATIC or token == lex.T_FORWARD or token == lex.T_ASM:
        return True
    return token == lex.T_INLINE or token == lex.T_RECURSIVE or token == lex.T_INTERRUPT


def declaration():
    """declaration = [ "pub" ] ( externDecl | funcDecl ), so far."""
    flags = 0
    if lex.tok == lex.T_PUB:
        flags = kernel.SF_PUB
        lex.next()
    if lex.tok == lex.T_EXTERN:
        extern_declaration(flags)
    elif lex.tok == lex.T_FUNC:
        function_declaration(flags)
    elif starts_later_declaration(lex.tok):
        err.fatal(err.E_UNSUPPORTED)
    else:
        err.fatal(err.E_DECL_EXPECTED)


def unit():
    """unit = "module" name NL { "import" name NL } { declaration }. Compiles the source that
    has just been opened, to its end."""
    lex.next()
    module_line()
    while lex.tok == lex.T_IMPORT:
        import_line()
    while lex.tok != lex.T_EOF:
        declaration()
