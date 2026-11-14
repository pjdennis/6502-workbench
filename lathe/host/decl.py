"""DECL: declarations, and interface files.

Owns the parsing of a module from its first line to its last, apart from what is inside a
function body (STMT) or a value (EXPR); what the kernel's symbol columns mean for each kind
of symbol; the names the language declares itself; and the interface file, which is written
from the symbol table when the module ends and read back into it by `import`. The format of
the interface file is in README.md.

It also sees to what is written when a function or the module ends: the VAR records of
variables, whose weights are complete only then, and the function `module.$init`.
"""
import asmblock
import err
import expr
import gen
import kernel
import lex
import out
import reg
import stmt
import typetab

# ---- Interface files ---------------------------------------------------------------------

LI_VERSION = 1
LI_END = 0              # entry kinds
LI_FUNC = 1
LI_CONST = 2
LI_VAR = 3
LI_TYPE = 4             # a named type: flags, then its type
LI_RECORD = 5           # a record type declared here: flags, number of fields, each a name and a type
LI_ENUM = 6             # an enumeration declared here: flags. Its constants follow as constants
LI_FUNC_TYPE = 7        # a function type declared here: flags, then parameters and results
LI_PUB = 1              # flag of those four: exported (the others are there for the types of what is)
LI_EXTERN = 1           # function flag: at a fixed address, which follows the flags
LI_RECURSIVE = 2        # function and function type flag: declared `recursive`
LI_ASM = 4              # function flag: an `asm` function, called like an extern one
LI_AT = 1               # what a variable's placement byte can be: at a fixed address, which
LI_ZP = 2               # follows it; declared `zp`; declared `nozp`; or 0
LI_NOZP = 4
LI_POINTER = 0x10       # type: a pointer to the type that follows; a basic type is its number
LI_ARRAY = 0x11         # type: an array, stored by column: its length (2), then its element type
LI_ROWS = 0x12          # the same, stored by row
LI_NAMED = 0x13         # type: a record, an enumeration or a function type, as the name of its
#                         module and its own name

MAX_DIRS = 8
C_SLASH = 0x2F
C_UPPER_L = 0x4C
C_UPPER_I = 0x49
ENDING = b".li"

directory = [0] * MAX_DIRS      # pointers to the names of the directories to look in, in order
directory_count = 0

# ---- Predeclared names -------------------------------------------------------------------

REGISTERS = b"a x y ax ay xy c "            # in the order of gen.REG_A to gen.REG_C
CONSTANTS = b"false true nil "              # the bool constants in the order of their values, nil
BUILTINS = b"lo hi sizeof len "             # in the order of expr.B_LO to expr.B_LEN
INIT_NAME = b"$init"                        # no source name can be this
REGISTER_COUNT = 8
REGISTER_PARTS = b"\x00\x01\x02\x04\x03\x05\x06\x08"   # which of A, X, Y and carry each uses
C_SPACE = 0x20
C_ZERO = 0x30

register_name = [0] * REGISTER_COUNT
init_parts = 0          # how many functions of initial values have been written out early


def init():
    """Declare what the language declares. Needs the keywords to have their tokens."""
    global directory_count, init_parts
    directory_count = 0
    init_parts = 0
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
            if value == 2:
                kernel.sym_type[s] = typetab.NIL_TYPE
                kernel.sym_value[s] = 0
            value += 1
            kernel.name_begin()
        else:
            kernel.name_add(CONSTANTS[i])
    value = 0
    for i in range(0, len(BUILTINS)):
        if BUILTINS[i] == C_SPACE:
            s = kernel.sym_add(kernel.SCOPE_PREDECLARED, kernel.name_end(), kernel.K_BUILTIN)
            kernel.sym_value[s] = value
            value += 1
            kernel.name_begin()
        else:
            kernel.name_add(BUILTINS[i])


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
    while typetab.is_pointer(t) or typetab.is_array(t):
        if typetab.is_pointer(t):
            kernel.put(stream, LI_POINTER)
        else:
            kernel.put(stream, LI_ARRAY + typetab.form[t] - typetab.FORM_ARRAY)
            kernel.put_word(stream, typetab.length(t))
        t = typetab.base(t)
    if typetab.is_record(t) or typetab.is_enum(t) or typetab.is_func(t):
        s = typetab.base(t)
        kernel.put(stream, LI_NAMED)
        kernel.put_name(stream, kernel.module_name[kernel.sym_scope[s]])
        kernel.put_name(stream, kernel.sym_name[s])
    else:
        kernel.put(stream, t)


def write_named_type(stream, s):
    """A type entry: a record, an enumeration or a function type that `s` declares, or another
    name for a type. Every record, enumeration and function type is written, so that what is
    exported can use them; one not `pub` is known to an importer but cannot be named there.
    Another name for a type is written only if it is `pub`."""
    t = kernel.sym_type[s]
    kind = LI_TYPE
    if (typetab.is_record(t) or typetab.is_enum(t) or typetab.is_func(t)) and typetab.base(t) == s:
        kind = LI_RECORD + typetab.form[t] - typetab.FORM_RECORD
    elif kernel.sym_flags[s] & kernel.SF_PUB == 0:
        return
    kernel.put(stream, kind)
    kernel.put_name(stream, kernel.sym_name[s])
    flags = 0
    if kernel.sym_flags[s] & kernel.SF_PUB != 0:
        flags = LI_PUB
    if kind == LI_FUNC_TYPE and typetab.is_recursive(t):
        flags = flags | LI_RECURSIVE
    kernel.put(stream, flags)
    if kind == LI_FUNC_TYPE:
        write_signature(stream, s)
    elif kind == LI_TYPE:
        write_type(stream, t)
    elif kind == LI_RECORD:
        kernel.put(stream, kernel.sym_params[s])
        for f in range(s + 1, s + 1 + kernel.sym_params[s]):
            kernel.put_name(stream, kernel.sym_name[f])
            write_type(stream, kernel.sym_type[f])


def write_members(stream, first, count):
    kernel.put(stream, count)
    for m in range(first, first + count):
        write_type(stream, kernel.member_type[m])
        kernel.put(stream, kernel.member_value[m])


def write_signature(stream, s):
    """The parameters and results of function or function type `s`."""
    write_members(stream, kernel.sym_members[s], kernel.sym_params[s])
    write_members(stream, kernel.sym_members[s] + kernel.sym_params[s], kernel.sym_results[s])


def write_function(stream, s):
    kernel.put(stream, LI_FUNC)
    kernel.put_name(stream, kernel.sym_name[s])
    if kernel.sym_flags[s] & kernel.SF_EXTERN != 0:
        kernel.put(stream, LI_EXTERN)
        kernel.put_word(stream, kernel.sym_value[s])
    elif kernel.sym_flags[s] & kernel.SF_ASM != 0:
        kernel.put(stream, LI_ASM)
    elif kernel.sym_flags[s] & kernel.SF_RECURSIVE != 0:
        kernel.put(stream, LI_RECURSIVE)
    else:
        kernel.put(stream, 0)
    write_signature(stream, s)


def write_constant(stream, s):
    kernel.put(stream, LI_CONST)
    kernel.put_name(stream, kernel.sym_name[s])
    write_type(stream, kernel.sym_type[s])
    kernel.put_word(stream, kernel.sym_value[s])


def write_variable(stream, s):
    kernel.put(stream, LI_VAR)
    kernel.put_name(stream, kernel.sym_name[s])
    write_type(stream, kernel.sym_type[s])
    if kernel.sym_flags[s] & kernel.SF_AT != 0:
        kernel.put(stream, LI_AT)
        kernel.put_word(stream, kernel.sym_value[s])
    elif kernel.sym_flags[s] & kernel.SF_ZP != 0:
        kernel.put(stream, LI_ZP)
    elif kernel.sym_flags[s] & kernel.SF_NOZP != 0:
        kernel.put(stream, LI_NOZP)
    else:
        kernel.put(stream, 0)


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
        if kernel.sym_scope[s] == kernel.SCOPE_MODULE and kernel.sym_kind[s] == kernel.K_TYPE:
            write_named_type(stream, s)
        elif kernel.sym_scope[s] == kernel.SCOPE_MODULE and kernel.sym_flags[s] & kernel.SF_PUB != 0:
            if kernel.sym_kind[s] == kernel.K_FUNC:
                write_function(stream, s)
            elif kernel.sym_kind[s] == kernel.K_CONST:
                write_constant(stream, s)
            else:
                write_variable(stream, s)
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
    mark = typetab.prefix_count
    t, _ = kernel.get(stream)
    while t == LI_POINTER or t == LI_ARRAY or t == LI_ROWS:
        if t == LI_POINTER:
            typetab.prefix(typetab.FORM_POINTER, 0)
        else:
            typetab.prefix(typetab.FORM_ARRAY + t - LI_ARRAY, kernel.get_word(stream))
        t, _ = kernel.get(stream)
    if t == LI_NAMED:
        t = imported_type(stream)
    elif t < typetab.BYTE_TYPE or t > typetab.NIL_TYPE:
        err.fatal(err.E_BAD_INTERFACE)
    return typetab.build(t, mark)


def imported_type(stream):
    """A record, an enumeration or a function type given by the name of its module and its own: the module must
    have been imported already, and is in a scope of its own number."""
    name = read_name(stream)
    scope = 1
    while scope < kernel.module_count and kernel.module_name[scope] != name:
        scope += 1
    if scope == kernel.module_count:
        err.fatal(err.E_TYPE_MODULE)
    s, found = kernel.sym_find(scope, read_name(stream))
    if not found or kernel.sym_kind[s] != kernel.K_TYPE:
        err.fatal(err.E_BAD_INTERFACE)
    return kernel.sym_type[s]


def read_named_type(stream, scope, kind):
    """A type entry of kind LI_TYPE, LI_RECORD, LI_ENUM or LI_FUNC_TYPE."""
    s = kernel.sym_add(scope, read_name(stream), kernel.K_TYPE)
    flags, _ = kernel.get(stream)
    if flags & LI_PUB != 0:
        kernel.sym_flags[s] = kernel.SF_PUB
    if kind == LI_TYPE:
        kernel.sym_type[s] = read_type(stream)
        return
    t = typetab.declared(typetab.FORM_RECORD + kind - LI_RECORD, s)
    kernel.sym_type[s] = t
    if kind == LI_FUNC_TYPE:
        if flags & LI_RECURSIVE != 0:
            typetab.make_recursive(t)
        read_signature(stream, s)
        return
    if kind == LI_ENUM:
        return
    count, _ = kernel.get(stream)
    for i in range(0, count):
        name = read_name(stream)
        add_field(s, name, read_type(stream))


def add_field(s, name, t):
    """A field called `name` of type `t` after the others of the record that `s` declares."""
    r = kernel.sym_type[s]
    f = kernel.sym_add(kernel.SCOPE_FIELDS + r, name, kernel.K_FIELD)
    kernel.sym_type[f] = t
    kernel.sym_value[f] = typetab.grow(r, typetab.size(t))
    kernel.sym_params[s] += 1


def read_members(stream):
    """Read parameters or results as members of the newest symbol. Returns how many."""
    count, _ = kernel.get(stream)
    for i in range(0, count):
        t = read_type(stream)
        register, _ = kernel.get(stream)
        kernel.member_add(t, register)
    return count


def read_signature(stream, s):
    """The parameters and results of function or function type `s`, the newest symbol."""
    kernel.sym_params[s] = read_members(stream)
    kernel.sym_results[s] = read_members(stream)


def read_function(stream, scope):
    s = kernel.sym_add(scope, read_name(stream), kernel.K_FUNC)
    flags, _ = kernel.get(stream)
    kernel.sym_flags[s] = kernel.SF_PUB
    if flags & LI_EXTERN != 0:
        kernel.sym_flags[s] = kernel.SF_PUB | kernel.SF_EXTERN
        kernel.sym_value[s] = kernel.get_word(stream)
    if flags & LI_ASM != 0:
        kernel.sym_flags[s] = kernel.SF_PUB | kernel.SF_ASM
    if flags & LI_RECURSIVE != 0:
        kernel.sym_flags[s] = kernel.SF_PUB | kernel.SF_RECURSIVE
    read_signature(stream, s)


def read_constant(stream, scope):
    s = kernel.sym_add(scope, read_name(stream), kernel.K_CONST)
    kernel.sym_flags[s] = kernel.SF_PUB
    kernel.sym_type[s] = read_type(stream)
    kernel.sym_value[s] = kernel.get_word(stream)


def read_variable(stream, scope):
    s = kernel.sym_add(scope, read_name(stream), kernel.K_VAR)
    kernel.sym_type[s] = read_type(stream)
    placement, _ = kernel.get(stream)
    kernel.sym_flags[s] = kernel.SF_PUB
    if placement == LI_AT:
        kernel.sym_flags[s] = kernel.SF_PUB | kernel.SF_AT
        kernel.sym_value[s] = kernel.get_word(stream)
    elif placement == LI_ZP:
        kernel.sym_flags[s] = kernel.SF_PUB | kernel.SF_ZP
    elif placement == LI_NOZP:
        kernel.sym_flags[s] = kernel.SF_PUB | kernel.SF_NOZP
    elif placement != 0:
        err.fatal(err.E_BAD_INTERFACE)


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
        if at_end or kind > LI_FUNC_TYPE:
            err.fatal(err.E_BAD_INTERFACE)      # a file cut short has no LI_END
        if kind == LI_END:
            break
        if kind == LI_FUNC:
            read_function(stream, number)
        elif kind == LI_CONST:
            read_constant(stream, number)
        elif kind == LI_VAR:
            read_variable(stream, number)
        else:
            read_named_type(stream, number, kind)
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
    """The name after "func": declare it as a function with these flags. If it was declared
    `forward`, that symbol is the one, and what follows must repeat that declaration. Returns
    the symbol and whether it is new."""
    if lex.tok != lex.T_NAME:
        err.fatal(err.E_NAME_EXPECTED)
    s, found = kernel.sym_find(kernel.SCOPE_MODULE, lex.value)
    if found and kernel.sym_kind[s] == kernel.K_FUNC and kernel.sym_flags[s] & kernel.SF_FORWARD != 0 \
            and flags & kernel.SF_FORWARD == 0:
        if (kernel.sym_flags[s] ^ flags) & kernel.SF_RECURSIVE != 0:
            err.fatal(err.E_FORWARD)
        kernel.sym_flags[s] = flags
        lex.next()
        return s, False
    s = kernel.sym_add(kernel.SCOPE_MODULE, lex.value, kernel.K_FUNC)
    kernel.sym_flags[s] = flags
    lex.next()
    return s, True


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
    t = expr.value_type()
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
    s, _ = function_symbol(flags | kernel.SF_EXTERN)
    lex.expect(lex.T_LPAREN, err.E_LPAREN_EXPECTED)
    kernel.sym_params[s] = register_parameters()
    kernel.sym_results[s] = register_results()
    lex.expect(lex.T_AT, err.E_AT_EXPECTED)
    kernel.sym_value[s] = expr.constant_number()
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)


def asm_function_declaration(flags):
    """"asm" regHead NL { asmLine NL } "end" NL: a function whose body is assembly, with its
    parameters and results in registers and no slots. It is called like an `extern` function,
    but through its symbol, with a CALL record."""
    lex.next()
    lex.expect(lex.T_FUNC, err.E_FUNC_EXPECTED)
    s, _ = function_symbol(flags | kernel.SF_ASM)
    lex.expect(lex.T_LPAREN, err.E_LPAREN_EXPECTED)
    kernel.sym_params[s] = register_parameters()
    kernel.sym_results[s] = register_results()
    kernel.scope_begin()                # the names of its labels go when it ends
    gen.function_begin(gen.object_symbol(s))
    asmblock.function_body()
    gen.function_end(object_flags(s) | out.FUNC_REGISTERS)
    kernel.scope_end()
    lex.next()
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)


def object_flags(s):
    """The flags of function `s` as its FUNC record has them."""
    flags = 0
    if kernel.sym_flags[s] & kernel.SF_PUB != 0:
        flags = out.FUNC_EXPORTED
    if kernel.sym_flags[s] & kernel.SF_RECURSIVE != 0:
        flags = flags | out.FUNC_RECURSIVE
    return flags


def member(s, fresh, index, where):
    """type: the type of parameter or result number `index` of function `s`, which is in
    `where`, or for a result in the place its type gives it. If the function is not `fresh`,
    this must be what the forward declaration said. Returns the type."""
    line = lex.line
    col = lex.col
    t = expr.value_type()
    if where != gen.REG_NONE:
        where = result_register(t)
    if fresh:
        kernel.member_add(t, where)
    elif index >= kernel.sym_params[s] + kernel.sym_results[s] \
            or kernel.member_type[kernel.sym_members[s] + index] != t \
            or kernel.member_value[kernel.sym_members[s] + index] != where:
        err.position(line, col)
        err.fatal(err.E_FORWARD)
    return t


def parameters(s, fresh):
    """[ param { "," param } ] ")", after the "(". param = name ":" type. Each is a slot of
    the frame, in order, and a local name. Returns how many."""
    count = 0
    if lex.tok != lex.T_RPAREN:
        while True:
            name = expr.new_name(kernel.SCOPE_LOCAL)
            lex.expect(lex.T_COLON, err.E_COLON_EXPECTED)
            t = member(s, fresh, count, gen.REG_NONE)
            p = kernel.sym_add(kernel.SCOPE_LOCAL, name, kernel.K_LOCAL)
            kernel.sym_type[p] = t
            kernel.sym_value[p] = reg.new_slot(typetab.size(t), reg.CLASS_EITHER, reg.SLOT_PARAMETER,
                                               name)
            count += 1
            if lex.tok != lex.T_COMMA:
                break
            lex.next()
    lex.expect(lex.T_RPAREN, err.E_RPAREN_EXPECTED)
    return count


def result_register(t):
    """Where a result of type `t` is returned (docs/code-model.md, "Convention")."""
    if t == typetab.BOOL_TYPE:
        return gen.REG_C
    if typetab.size(t) == 2:
        return gen.REG_AX
    return gen.REG_A


def results(s, fresh, index):
    """[ ":" type [ "," "bool" ] ]: nothing, a value, a status, or a value and a status.
    They are the members of `s` from number `index` on. Returns how many."""
    if lex.tok != lex.T_COLON:
        return 0
    lex.next()
    t = member(s, fresh, index, gen.REG_A)
    if lex.tok != lex.T_COMMA:
        return 1
    lex.next()
    if t == typetab.BOOL_TYPE or lex.tok != lex.T_BOOL:
        err.fatal(err.E_TYPE)
    member(s, fresh, index + 1, gen.REG_C)
    return 2


def head(s, fresh):
    """funcHead from its "(" on, for function `s`, which is declared for the first time if
    `fresh` and must otherwise repeat its forward declaration."""
    lex.expect(lex.T_LPAREN, err.E_LPAREN_EXPECTED)
    count = parameters(s, fresh)
    if fresh:
        kernel.sym_params[s] = count
    elif count != kernel.sym_params[s]:
        err.fatal(err.E_FORWARD)
    count = results(s, fresh, count)
    if fresh:
        kernel.sym_results[s] = count
    elif count != kernel.sym_results[s]:
        err.fatal(err.E_FORWARD)
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)


def lasting_variables(first, scope):
    """Write the VAR record of each variable of `scope` from symbol `first` on that lives for
    the whole program. Its weight is complete: nothing that follows can use it."""
    for s in range(first, kernel.sym_count):
        if kernel.sym_kind[s] == kernel.K_VAR and kernel.sym_scope[s] == scope \
                and kernel.sym_flags[s] & kernel.SF_AT == 0:
            out.variable(kernel.sym_obj[s], typetab.size(kernel.sym_type[s]),
                         stmt.zp_class(kernel.sym_flags[s]), kernel.sym_weight[s])


def function_declaration(flags):
    """funcDecl = funcHead NL body "end" NL, or "forward" funcHead NL if `flags` say so."""
    lex.next()
    s, fresh = function_symbol(flags)
    # The scope begins once the function's own name is declared and the token after it has
    # been read: every name made from here on is a parameter's or a local's.
    kernel.scope_begin()
    gen.function_begin(gen.object_symbol(s))
    gen.saves_frame = kernel.sym_flags[s] & kernel.SF_RECURSIVE != 0
    head(s, fresh)
    if flags & kernel.SF_FORWARD != 0:
        kernel.scope_end()
        return
    stmt.function_body(s)
    if lex.tok != lex.T_END:
        err.fatal(err.E_END_EXPECTED)
    gen.function_end(object_flags(s))
    lasting_variables(kernel.local_base, kernel.SCOPE_LOCAL)
    # The scope ends before "end" is passed over, so that no token read after it can be
    # taken for one of the function's own names.
    kernel.scope_end()
    lex.next()
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)


# ---- Constants, and what the end of the module writes ------------------------------------

def constant_declaration(flags):
    """constDecl = "const" name [ ":" type ] "=" initialiser NL. A constant of an array type,
    or one that is a string, is a table: constant data with the constant's name."""
    lex.next()
    name = expr.new_name(kernel.SCOPE_MODULE)
    t = typetab.NO_TYPE
    if lex.tok == lex.T_COLON:
        lex.next()
        line = lex.line
        col = lex.col
        t = expr.type_spec()
        err.position(line, col)
        stmt.layout(t)
    lex.expect(lex.T_ASSIGN, err.E_SYNTAX)
    stmt.no_record(t)
    if t == typetab.NO_TYPE and lex.tok == lex.T_STRING:
        t = typetab.array_of(typetab.BYTE_TYPE, lex.string_length + 1, False)
    if typetab.is_array(t):
        symbol = out.symbol(out.SYM_DATA, kernel.module_name[0], 0, name)
        stmt.table_data(t, symbol)
        s = kernel.sym_add(kernel.SCOPE_MODULE, name, kernel.K_CONST)
        kernel.sym_flags[s] = flags
        kernel.sym_type[s] = t
        kernel.sym_obj[s] = symbol
        lex.expect(lex.T_NL, err.E_NL_EXPECTED)
        return
    line = lex.line
    col = lex.col
    expr.constant(t)
    if reg.op_kind[reg.depth - 1] != reg.O_CONST:
        err.position(line, col)
        err.fatal(err.E_NOT_CONST)
    s = kernel.sym_add(kernel.SCOPE_MODULE, name, kernel.K_CONST)
    kernel.sym_flags[s] = flags
    kernel.sym_type[s] = reg.op_type[reg.depth - 1]
    kernel.sym_value[s] = reg.op_value[reg.depth - 1]
    reg.pop()
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)


def init_symbol(number):
    """The object-file symbol of the function of initial values: `module.$init`, or with a
    number after it for one written out early."""
    kernel.name_begin()
    for i in range(0, len(INIT_NAME)):
        kernel.name_add(INIT_NAME[i])
    if number >= 10:
        kernel.name_add(C_ZERO + number // 10)
    if number > 0:
        kernel.name_add(C_ZERO + number % 10)
    return out.symbol(out.SYM_FUNCTION, kernel.module_name[0], 0, kernel.name_end())


def init_early():
    """The list of initial values is getting long: write a function for what it holds now.
    The next such function, or `module.$init` itself, calls it first."""
    global init_parts
    init_parts += 1
    gen.init_function(init_symbol(init_parts))


def check_bodies():
    """Every function declared `forward` must have had its body."""
    for s in range(0, kernel.sym_count):
        if kernel.sym_scope[s] == kernel.SCOPE_MODULE and kernel.sym_kind[s] == kernel.K_FUNC \
                and kernel.sym_flags[s] & kernel.SF_FORWARD != 0:
            err.fatal(err.E_NO_BODY)


def starts_later_declaration(token):
    """True for the first token of a declaration not done yet."""
    return token == lex.T_INLINE or token == lex.T_INTERRUPT


def type_symbol(name, flags):
    s = kernel.sym_add(kernel.SCOPE_MODULE, name, kernel.K_TYPE)
    kernel.sym_flags[s] = flags
    return s


def record_type(s):
    """"record" NL { name ":" type NL } "end", for the type that `s` declares. Its symbol and
    type exist before the fields are read, so a field can point to the record."""
    t = typetab.declared(typetab.FORM_RECORD, s)
    kernel.sym_type[s] = t
    lex.next()
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)
    while lex.tok != lex.T_END:
        name = expr.new_name(kernel.SCOPE_FIELDS + t)
        lex.expect(lex.T_COLON, err.E_COLON_EXPECTED)
        line = lex.line
        col = lex.col
        f = expr.type_spec()
        err.position(line, col)
        stmt.layout(f)
        if typetab.innermost(f) == t:
            err.fatal(err.E_RECORD_SELF)
        add_field(s, name, f)
        lex.expect(lex.T_NL, err.E_NL_EXPECTED)
    if typetab.size(t) == 0:
        err.fatal(err.E_EMPTY_RECORD)
    lex.next()


def function_type(s):
    """funcType = [ "recursive" ] "func" "(" [ param { "," param } ] ")" [ ":" type [ "," "bool" ] ],
    for the type that `s` declares: its parameters and results are the members of `s`, as a
    function's are. The names of the parameters are only read."""
    t = typetab.declared(typetab.FORM_FUNC, s)
    kernel.sym_type[s] = t
    if lex.tok == lex.T_RECURSIVE:
        typetab.make_recursive(t)
        lex.next()
        if lex.tok != lex.T_FUNC:
            err.fatal(err.E_FUNC_EXPECTED)
    lex.next()
    lex.expect(lex.T_LPAREN, err.E_LPAREN_EXPECTED)
    count = 0
    if lex.tok != lex.T_RPAREN:
        while True:
            if lex.tok != lex.T_NAME:
                err.fatal(err.E_NAME_EXPECTED)
            lex.next()
            lex.expect(lex.T_COLON, err.E_COLON_EXPECTED)
            member(s, True, count, gen.REG_NONE)
            count += 1
            if lex.tok != lex.T_COMMA:
                break
            lex.next()
    lex.expect(lex.T_RPAREN, err.E_RPAREN_EXPECTED)
    kernel.sym_params[s] = count
    kernel.sym_results[s] = results(s, True, count)


def type_declaration(flags):
    """typeDecl = "type" name "=" ( type | recordType | funcType ) NL."""
    lex.next()
    name = expr.new_name(kernel.SCOPE_MODULE)
    lex.expect(lex.T_ASSIGN, err.E_SYNTAX)
    if lex.tok == lex.T_RECORD:
        record_type(type_symbol(name, flags))
    elif lex.tok == lex.T_FUNC or lex.tok == lex.T_RECURSIVE:
        function_type(type_symbol(name, flags))
    else:
        line = lex.line
        col = lex.col
        t = expr.type_spec()
        err.position(line, col)
        stmt.layout(t)
        kernel.sym_type[type_symbol(name, flags)] = t
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)


def enum_declaration(flags):
    """enumDecl = "enum" name NL { name [ "=" constExpr ] NL } "end" NL. The constants are
    numbered on from the one before, from 0; each must fit a byte."""
    lex.next()
    s = type_symbol(expr.new_name(kernel.SCOPE_MODULE), flags)
    t = typetab.declared(typetab.FORM_ENUM, s)
    kernel.sym_type[s] = t
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)
    value = 0
    while lex.tok != lex.T_END:
        line = lex.line
        col = lex.col
        name = expr.new_name(kernel.SCOPE_MODULE)
        if lex.tok == lex.T_ASSIGN:
            lex.next()
            line = lex.line
            col = lex.col
            value = expr.constant_number()
        if value > 0xFF:
            err.position(line, col)
            err.fatal(err.E_RANGE)
        c = kernel.sym_add(kernel.SCOPE_MODULE, name, kernel.K_CONST)
        kernel.sym_flags[c] = flags
        kernel.sym_type[c] = t
        kernel.sym_value[c] = value
        value += 1
        lex.expect(lex.T_NL, err.E_NL_EXPECTED)
    lex.next()
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)


def declaration():
    """declaration = [ "pub" ] ( constDecl | typeDecl | enumDecl | varDecl | funcDecl | externDecl | asmFunc )
    | "forward" funcHead NL."""
    flags = 0
    if lex.tok == lex.T_FORWARD:
        lex.next()
        if lex.tok == lex.T_RECURSIVE:
            flags = kernel.SF_RECURSIVE
            lex.next()
        if lex.tok != lex.T_FUNC:
            err.fatal(err.E_FUNC_EXPECTED)
        function_declaration(kernel.SF_FORWARD | flags)
        return
    if lex.tok == lex.T_PUB:
        flags = kernel.SF_PUB
        lex.next()
    if lex.tok == lex.T_RECURSIVE:
        lex.next()
        if lex.tok == lex.T_EXTERN or lex.tok == lex.T_ASM:
            err.fatal(err.E_RECURSIVE_BODY)
        if lex.tok != lex.T_FUNC:
            err.fatal(err.E_FUNC_EXPECTED)
        function_declaration(flags | kernel.SF_RECURSIVE)
    elif lex.tok == lex.T_EXTERN:
        extern_declaration(flags)
    elif lex.tok == lex.T_FUNC:
        function_declaration(flags)
    elif lex.tok == lex.T_ASM:
        asm_function_declaration(flags)
    elif lex.tok == lex.T_CONST:
        constant_declaration(flags)
    elif lex.tok == lex.T_TYPE:
        type_declaration(flags)
    elif lex.tok == lex.T_ENUM:
        enum_declaration(flags)
    elif lex.tok == lex.T_VAR:
        stmt.variable(flags, stmt.LEVEL_MODULE)
        lex.expect(lex.T_NL, err.E_NL_EXPECTED)
    elif lex.tok == lex.T_HASH_IF:
        stmt.directive()
        lex.expect(lex.T_NL, err.E_NL_EXPECTED)
    elif starts_later_declaration(lex.tok) or lex.tok == lex.T_STATIC:
        err.fatal(err.E_UNSUPPORTED)
    else:
        err.fatal(err.E_DECL_EXPECTED)


def unit():
    """unit = "module" name NL { "import" name NL } { declaration }. Compiles the source that
    has just been opened, to its end."""
    lex.next()
    module_line()
    while lex.tok == lex.T_IMPORT or lex.tok == lex.T_HASH_IF:
        if lex.tok == lex.T_IMPORT:
            import_line()
        else:
            declaration()
    while lex.tok != lex.T_EOF:
        if gen.init_count >= gen.INIT_FLUSH:
            init_early()
        declaration()
    check_bodies()
    lasting_variables(0, kernel.SCOPE_MODULE)
    if gen.init_count > 0 or init_parts > 0:
        gen.init_function(init_symbol(0))
