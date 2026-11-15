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
import inline
import kernel
import lex
import out
import parts
import reg
import typetab

RECURSIVE = ["read_interface"]

# ---- Interface files ---------------------------------------------------------------------

LI_VERSION = 2
LI_END = 0              # entry kinds
LI_FUNC = 1
LI_CONST = 2
LI_VAR = 3
LI_TYPE = 4             # a named type: flags, then its type
LI_RECORD = 5           # a record type declared here: flags, number of fields, each a name and a type
LI_ENUM = 6             # an enumeration declared here: flags. Its constants follow as constants
LI_FUNC_TYPE = 7        # a function type declared here: flags, then parameters and results
LI_MODULE = 8           # a module this one imports, which its exported inline functions can name
LI_CONST_IN = 9         # a constant table `in REGION`: as LI_CONST, then the region's name
LI_USES = 10            # what the body of an exported inline function names: the function's name,
#                         how many, and each as a module (string, empty for this one) and a name
LI_PUB = 1             # flag of those four: exported (the others are there for the types of what is)
LI_EXTERN = 1           # function flag: at a fixed address, which follows the flags
LI_RECURSIVE = 2        # function and function type flag: declared `recursive`
LI_ASM = 4              # function flag: an `asm` function, called like an extern one
LI_INLINE = 8           # function flag: an `inline` function, whose saved tokens follow its members
LI_INTERRUPT = 16       # function flag: an `interrupt` function, which cannot be called
LI_AT = 1               # what a variable's placement byte can be: at a fixed address, which
LI_ZP = 2               # follows it; declared `zp`; declared `nozp`; or 0
LI_NOZP = 4
LI_IN = 8               # `in REGION` (and so never in zero page): the region's name follows
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

# The entry being read, until it is frozen (kernel.freeze()): its name, and its members
MAX_ENTRY_MEMBERS = 64
entry_name = bytearray(kernel.MAX_NAME)
entry_length = 0
entry_type = bytearray(MAX_ENTRY_MEMBERS)
entry_register = bytearray(MAX_ENTRY_MEMBERS)
entry_members = 0

# What the import being read wants of the interfaces it reads (import_line()): the names its list
# gives, and what the bodies of the inline functions read name (read_uses()). A row is a module
# and a name, by their name entries; where a listed name was, for error 102. The rows last while
# one `import` line is read, the interfaces it brings in included.
MAX_WANTS = 160
W_LISTED = 1            # want_flags: the importer's list names it
W_FOUND = 2             # an entry of the interface has its name, or the module had it already
NO_ROW = 0xFF
want_module = [0] * MAX_WANTS
want_name = [0] * MAX_WANTS
want_hash = bytearray(MAX_WANTS)        # kernel.name_hash() of the name
want_flags = bytearray(MAX_WANTS)
want_line = [0] * MAX_WANTS
want_col = [0] * MAX_WANTS
want_count = 0
entry_row = NO_ROW      # the row that wanted() found for the entry being read
row_name = 0            # and its name

# How each module's interface is read: everything in it (M_WHOLE: an `import` without a list,
# or a module whose functions the compiler calls by itself, WHOLE_MODULES), and whether the
# importer can name all of it (M_SHOWN: an `import` without a list)
M_WHOLE = 1
M_SHOWN = 2
module_read = bytearray(kernel.MAX_MODULES)
WHOLE_MODULES = b"rt_math rt_frame "    # gen.math_function() and gen.frame_routines() look these up
READ_SKIP = 0           # what wanted() says of an entry: not read;
READ_FROZEN = 1         # read as a frozen entry;
READ_ROW = 2            # made a symbol at once, with the name of row entry_row;
READ_SHOWN = 4          # and with either of those, the importer can name it

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
            kernel.set_byte(s, kernel.C_TYPE, typetab.BOOL_TYPE)
            kernel.set_word(s, kernel.C_VALUE, value)
            if value == 2:
                kernel.set_byte(s, kernel.C_TYPE, typetab.NIL_TYPE)
                kernel.set_word(s, kernel.C_VALUE, 0)
            value += 1
            kernel.name_begin()
        else:
            kernel.name_add(CONSTANTS[i])
    value = 0
    for i in range(0, len(BUILTINS)):
        if BUILTINS[i] == C_SPACE:
            s = kernel.sym_add(kernel.SCOPE_PREDECLARED, kernel.name_end(), kernel.K_BUILTIN)
            kernel.set_word(s, kernel.C_VALUE, value)
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
        kernel.put_name(stream, kernel.module_name[kernel.byte_of(s, kernel.C_SCOPE)])
        kernel.put_name(stream, kernel.word_of(s, kernel.C_NAME))
    else:
        kernel.put(stream, t)


def write_named_type(stream, s):
    """A type entry: a record, an enumeration or a function type that `s` declares, or another
    name for a type. Every record, enumeration and function type is written, so that what is
    exported can use them; one not `pub` is known to an importer but cannot be named there.
    Another name for a type is written only if it is `pub`."""
    t = kernel.byte_of(s, kernel.C_TYPE)
    kind = LI_TYPE
    if (typetab.is_record(t) or typetab.is_enum(t) or typetab.is_func(t)) and typetab.base(t) == s:
        kind = LI_RECORD + typetab.form[t] - typetab.FORM_RECORD
    elif kernel.byte_of(s, kernel.C_FLAGS) & kernel.SF_PUB == 0:
        return
    kernel.put(stream, kind)
    kernel.put_name(stream, kernel.word_of(s, kernel.C_NAME))
    flags = 0
    if kernel.byte_of(s, kernel.C_FLAGS) & kernel.SF_PUB != 0:
        flags = LI_PUB
    if kind == LI_FUNC_TYPE and typetab.is_recursive(t):
        flags = flags | LI_RECURSIVE
    kernel.put(stream, flags)
    if kind == LI_FUNC_TYPE:
        write_signature(stream, s)
    elif kind == LI_TYPE:
        write_type(stream, t)
    elif kind == LI_RECORD:
        kernel.put(stream, kernel.byte_of(s, kernel.C_PARAMS))
        for f in range(s + 1, s + 1 + kernel.byte_of(s, kernel.C_PARAMS)):
            kernel.put_name(stream, kernel.word_of(f, kernel.C_NAME))
            write_type(stream, kernel.byte_of(f, kernel.C_TYPE))


def write_members(stream, first, count):
    kernel.put(stream, count)
    for m in range(first, first + count):
        write_type(stream, kernel.member_type_of(m))
        kernel.put(stream, kernel.member_value_of(m))


def write_signature(stream, s):
    """The parameters and results of function or function type `s`."""
    write_members(stream, kernel.word_of(s, kernel.C_MEMBERS), kernel.byte_of(s, kernel.C_PARAMS))
    write_members(stream, kernel.word_of(s, kernel.C_MEMBERS) + kernel.byte_of(s, kernel.C_PARAMS), kernel.byte_of(s, kernel.C_RESULTS))


def write_function(stream, s):
    kernel.put(stream, LI_FUNC)
    kernel.put_name(stream, kernel.word_of(s, kernel.C_NAME))
    if kernel.byte_of(s, kernel.C_FLAGS) & kernel.SF_EXTERN != 0:
        kernel.put(stream, LI_EXTERN)
        kernel.put_word(stream, kernel.word_of(s, kernel.C_VALUE))
    elif kernel.byte_of(s, kernel.C_FLAGS) & kernel.SF_ASM != 0:
        kernel.put(stream, LI_ASM)
    elif kernel.byte_of(s, kernel.C_FLAGS) & kernel.SF_RECURSIVE != 0:
        kernel.put(stream, LI_RECURSIVE)
    elif kernel.byte_of(s, kernel.C_FLAGS) & inline.SF_INLINE != 0:
        kernel.put(stream, LI_INLINE)
    elif kernel.byte_of(s, kernel.C_FLAGS) & inline.SF_INTERRUPT != 0:
        kernel.put(stream, LI_INTERRUPT)
    else:
        kernel.put(stream, 0)
    write_signature(stream, s)
    if kernel.byte_of(s, kernel.C_FLAGS) & inline.SF_INLINE != 0:
        inline.write(stream, s)


def write_constant(stream, s):
    if kernel.byte_of(s, kernel.C_FLAGS) & kernel.SF_IN != 0:
        kernel.put(stream, LI_CONST_IN)
        kernel.put_name(stream, kernel.word_of(s, kernel.C_NAME))
        write_type(stream, kernel.byte_of(s, kernel.C_TYPE))
        kernel.put_word(stream, 0)
        kernel.put_name(stream, kernel.word_of(s, kernel.C_VALUE))
        return
    kernel.put(stream, LI_CONST)
    kernel.put_name(stream, kernel.word_of(s, kernel.C_NAME))
    write_type(stream, kernel.byte_of(s, kernel.C_TYPE))
    kernel.put_word(stream, kernel.word_of(s, kernel.C_VALUE))


def write_variable(stream, s):
    kernel.put(stream, LI_VAR)
    kernel.put_name(stream, kernel.word_of(s, kernel.C_NAME))
    write_type(stream, kernel.byte_of(s, kernel.C_TYPE))
    if kernel.byte_of(s, kernel.C_FLAGS) & kernel.SF_AT != 0:
        kernel.put(stream, LI_AT)
        kernel.put_word(stream, kernel.word_of(s, kernel.C_VALUE))
    elif kernel.byte_of(s, kernel.C_FLAGS) & kernel.SF_IN != 0:
        kernel.put(stream, LI_IN)
        kernel.put_name(stream, kernel.word_of(s, kernel.C_VALUE))
    elif kernel.byte_of(s, kernel.C_FLAGS) & kernel.SF_ZP != 0:
        kernel.put(stream, LI_ZP)
    elif kernel.byte_of(s, kernel.C_FLAGS) & kernel.SF_NOZP != 0:
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
    expands = False                     # an importer may expand an inline function of this one
    for s in range(0, kernel.sym_count):
        if kernel.byte_of(s, kernel.C_SCOPE) == kernel.SCOPE_MODULE and kernel.byte_of(s, kernel.C_KIND) == kernel.K_FUNC \
                and kernel.byte_of(s, kernel.C_FLAGS) & (kernel.SF_PUB | inline.SF_INLINE) == kernel.SF_PUB | inline.SF_INLINE:
            expands = True
    # What each exported inline function's body names, newest function first (read_uses()).
    s = kernel.sym_count
    while s > 0:
        s -= 1
        if kernel.byte_of(s, kernel.C_SCOPE) == kernel.SCOPE_MODULE and kernel.byte_of(s, kernel.C_KIND) == kernel.K_FUNC \
                and kernel.byte_of(s, kernel.C_FLAGS) & (kernel.SF_PUB | inline.SF_INLINE) == kernel.SF_PUB | inline.SF_INLINE:
            kernel.put(stream, LI_USES)
            kernel.put_name(stream, kernel.word_of(s, kernel.C_NAME))
            inline.write_uses(stream, s)
    for s in range(0, kernel.sym_count):
        if kernel.byte_of(s, kernel.C_SCOPE) == kernel.SCOPE_MODULE and kernel.byte_of(s, kernel.C_KIND) == kernel.K_TYPE:
            write_named_type(stream, s)
        elif kernel.byte_of(s, kernel.C_SCOPE) == kernel.SCOPE_MODULE and kernel.byte_of(s, kernel.C_KIND) == kernel.K_MODULE:
            if expands:
                kernel.put(stream, LI_MODULE)
                kernel.put_name(stream, kernel.word_of(s, kernel.C_NAME))
        elif kernel.byte_of(s, kernel.C_SCOPE) == kernel.SCOPE_MODULE and kernel.byte_of(s, kernel.C_FLAGS) & kernel.SF_PUB != 0:
            if kernel.byte_of(s, kernel.C_KIND) == kernel.K_FUNC:
                write_function(stream, s)
            elif kernel.byte_of(s, kernel.C_KIND) == kernel.K_CONST:
                write_constant(stream, s)
            else:
                write_variable(stream, s)
    kernel.put(stream, LI_END)
    kernel.close(stream)


# ---- Reading an interface ----------------------------------------------------------------

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
    name = inline.read_name(stream)
    scope = 1
    while scope < kernel.module_count and kernel.module_name[scope] != name:
        scope += 1
    if scope == kernel.module_count:
        err.fatal(err.E_TYPE_MODULE)
    s, found = kernel.sym_find(scope, inline.read_name(stream))
    if not found or kernel.byte_of(s, kernel.C_KIND) != kernel.K_TYPE:
        err.fatal(err.E_BAD_INTERFACE)
    return kernel.byte_of(s, kernel.C_TYPE)


def read_named_type(stream, scope, kind, again):
    """A type entry of kind LI_TYPE, LI_RECORD, LI_ENUM or LI_FUNC_TYPE. Every type of the
    interface is read, listed or not, the first time it is read; `again`, it is passed over, but
    the importer can name it from now on if it is listed. A listed type that is not `pub` is
    error 102."""
    read_entry_name(stream)
    entry_name_begin()
    how = wanted(scope, True)
    flags, _ = kernel.get(stream)
    if flags & LI_PUB == 0 and listed(entry_row):
        not_exported(entry_row)
    if again:
        kernel.built_loaded(scope, how & READ_SHOWN != 0)
        skip_named_type(stream, kind)
        return
    s = kernel.sym_add(scope, kernel.name_end(), kernel.K_TYPE)
    if flags & LI_PUB != 0:
        kernel.set_byte(s, kernel.C_FLAGS, hidden(kernel.SF_PUB, how))
    if kind == LI_TYPE:
        kernel.set_byte(s, kernel.C_TYPE, read_type(stream))
        return
    t = typetab.declared(typetab.FORM_RECORD + kind - LI_RECORD, s)
    kernel.set_byte(s, kernel.C_TYPE, t)
    if kind == LI_FUNC_TYPE:
        if flags & LI_RECURSIVE != 0:
            typetab.make_recursive(t)
        read_signature(stream, s)
        return
    if kind == LI_ENUM:
        return
    count, _ = kernel.get(stream)
    for i in range(0, count):
        name = inline.read_name(stream)
        add_field(s, name, read_type(stream))


def skip_named_type(stream, kind):
    """What follows the flags of a type entry read before: its types are read again, which
    makes no new type, and nothing else is made."""
    global entry_members
    entry_members = 0
    if kind == LI_TYPE:
        read_type(stream)
    elif kind == LI_FUNC_TYPE:
        read_entry_members(stream)
        read_entry_members(stream)
    elif kind == LI_RECORD:
        count, _ = kernel.get(stream)
        for i in range(0, count):
            inline.skip_name(stream)
            read_type(stream)


def add_field(s, name, t):
    """A field called `name` of type `t` after the others of the record that `s` declares."""
    r = kernel.byte_of(s, kernel.C_TYPE)
    f = kernel.sym_add(kernel.SCOPE_FIELDS + r, name, kernel.K_FIELD)
    kernel.set_byte(f, kernel.C_TYPE, t)
    kernel.set_word(f, kernel.C_VALUE, typetab.grow(r, typetab.size(t)))
    kernel.set_byte(s, kernel.C_PARAMS, kernel.byte_of(s, kernel.C_PARAMS) + 1)


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
    kernel.set_byte(s, kernel.C_PARAMS, read_members(stream))
    kernel.set_byte(s, kernel.C_RESULTS, read_members(stream))


def read_entry_name(stream):
    """The name of an entry, which is not made a name yet: its characters are kept in
    entry_name, the first kernel.MAX_NAME of them, as a name keeps them."""
    global entry_length
    length, _ = kernel.get(stream)
    entry_length = 0
    for i in range(0, length):
        ch, _ = kernel.get(stream)
        if entry_length < kernel.MAX_NAME:
            entry_name[entry_length] = ch
            entry_length += 1


def entry_name_begin():
    """Build the entry's name in the name heap (kernel.name_begin())."""
    kernel.name_begin()
    for i in range(0, entry_length):
        kernel.name_add(entry_name[i])


def read_entry_members(stream):
    """Read parameters or results into the entry's members. Returns how many."""
    global entry_members
    count, _ = kernel.get(stream)
    for i in range(0, count):
        if entry_members == MAX_ENTRY_MEMBERS:
            err.fatal(err.E_MEMBERS_FULL)
        entry_type[entry_members] = read_type(stream)
        register, _ = kernel.get(stream)
        entry_register[entry_members] = register
        entry_members += 1
    return count


# ---- What an import wants ----------------------------------------------------------------

def add_want(owner, name, flags):
    """A row: the import wants the entry `name` of the module called `owner`, as `flags` say;
    where the current token is, for error 102. A row that is there already is not added
    again, but a name a list gives twice is error 103."""
    global want_count
    spelling = kernel.name_hash(name)
    for i in range(0, want_count):
        if want_module[i] == owner and want_name[i] == name:
            if flags & want_flags[i] & W_LISTED != 0:
                err.fatal(err.E_LISTED_TWICE)
            want_flags[i] = want_flags[i] | flags
            return
    if want_count == MAX_WANTS:
        err.fatal(err.E_WANTS_FULL)
    want_module[want_count] = owner
    want_name[want_count] = name
    want_hash[want_count] = spelling
    want_flags[want_count] = flags
    want_line[want_count] = lex.line
    want_col[want_count] = lex.col
    want_count += 1


def listed(row):
    """True if `row` is one, and the importer's list gave it."""
    return row != NO_ROW and want_flags[row] & W_LISTED != 0


def not_exported(row):
    """Error 102, at the name the list gave."""
    err.position(want_line[row], want_col[row])
    err.fatal(err.E_NOT_EXPORTED)


def hidden(flags, how):
    """Symbol flags `flags`, with SF_HIDDEN unless `how` says the importer can name it."""
    if how & READ_SHOWN == 0:
        return flags | kernel.SF_HIDDEN
    return flags


def wanted(number, mark):
    """How the entry of module `number` whose name is being built is read (READ_SKIP,
    READ_FROZEN or READ_ROW, and READ_SHOWN): as the rows that name it say, else as the
    module is read. entry_row is the row, a listed one first, or NO_ROW. If `mark`, the rows
    are marked found. row_name is the row's name."""
    global entry_row, row_name
    entry_row = NO_ROW
    for i in range(0, want_count):
        if want_hash[i] == kernel.new_hash and want_module[i] == kernel.module_name[number] \
                and kernel.built_is(want_name[i]):
            if mark:
                want_flags[i] = want_flags[i] | W_FOUND
            if not listed(entry_row):
                entry_row = i
    if entry_row != NO_ROW:
        row_name = want_name[entry_row]
    how = READ_SKIP
    if module_read[number] & M_WHOLE != 0:
        how = READ_FROZEN
    if entry_row != NO_ROW:
        how = READ_ROW
    if module_read[number] & M_SHOWN != 0 or listed(entry_row):
        how = how | READ_SHOWN
    return how


def pending(number):
    """True if a row wants an entry of module `number`, read before, that it does not have yet.
    Those it has are found now, and those a list gives can be named (error 102 for a type not
    `pub` or a module of its interface)."""
    more = False
    for i in range(0, want_count):
        waiting = want_module[i] == kernel.module_name[number] and want_flags[i] & W_FOUND == 0
        name = want_name[i]
        if waiting:
            s, found = kernel.sym_find(number, name)
            if not found:
                more = True
            elif listed(i):
                kind = kernel.byte_of(s, kernel.C_KIND)
                if kind == kernel.K_MODULE or (kind == kernel.K_TYPE
                                               and kernel.byte_of(s, kernel.C_FLAGS) & kernel.SF_PUB == 0):
                    not_exported(i)
                kernel.set_byte(s, kernel.C_FLAGS, kernel.byte_of(s, kernel.C_FLAGS) & ~kernel.SF_HIDDEN)
            if found:
                want_flags[i] = want_flags[i] | W_FOUND
    return more


def check_found():
    """Error 102 at the first row the importer's list gave that no entry has."""
    for i in range(0, want_count):
        if want_flags[i] & (W_LISTED | W_FOUND) == W_LISTED:
            not_exported(i)


def whole_module(name):
    """True if `name` is that of a module in WHOLE_MODULES."""
    i = 0
    while i < len(WHOLE_MODULES):
        k = 0
        same = True
        while WHOLE_MODULES[i + k] != C_SPACE:
            if k >= kernel.name_length(name) or kernel.name_char(name, k) != WHOLE_MODULES[i + k]:
                same = False
            k += 1
        if same and k == kernel.name_length(name):
            return True
        i += k + 1
    return False


def new_module(name, how):
    """The next module number, for the module called `name`, read as `how` (M_WHOLE, M_SHOWN)
    says, and as a whole if the compiler calls its functions itself."""
    m = kernel.module_add(name)
    module_read[m] = how
    if whole_module(name):
        module_read[m] = how | M_WHOLE
    return m


# ---- Reading the entries -----------------------------------------------------------------

def freeze(scope, kind, flags, t, value, params, results):
    """The entry read becomes a frozen symbol of module `scope` (kernel.freeze())."""
    entry_name_begin()
    kernel.freeze(scope, kind, flags, t, value, params, results)
    for i in range(0, entry_members):
        kernel.freeze_member(entry_type[i], entry_register[i])


def enter(scope, how, again, kind, flags, t, value, params, results):
    """The function, constant or variable entry read, with these columns and its members, is
    read as `how` says (wanted()): a symbol at once with its row's name, a frozen entry, or
    nothing. `again`, an entry the module has already is only shown if `how` says so."""
    entry_name_begin()
    if again and kernel.built_loaded(scope, how & READ_SHOWN != 0):
        return
    flags = hidden(flags, how)
    if how & READ_ROW != 0:
        s = kernel.sym_thawed(scope, row_name, kind)
        kernel.set_byte(s, kernel.C_FLAGS, flags)
        kernel.set_byte(s, kernel.C_TYPE, t)
        kernel.set_word(s, kernel.C_VALUE, value)
        kernel.set_byte(s, kernel.C_PARAMS, params)
        kernel.set_byte(s, kernel.C_RESULTS, results)
        for i in range(0, entry_members):
            kernel.member_add(entry_type[i], entry_register[i])
    elif how & READ_FROZEN != 0:
        freeze(scope, kind, flags, t, value, params, results)


def read_function(stream, scope, again):
    """A function entry: frozen, unless it is `inline`, whose saved tokens are read now if it is
    wanted, or passed over."""
    global entry_members
    read_entry_name(stream)
    flags, _ = kernel.get(stream)
    if flags & LI_INLINE != 0:
        entry_name_begin()
        how = wanted(scope, True)
        entry_members = 0
        if how == READ_SKIP or again and kernel.built_loaded(scope, how & READ_SHOWN != 0):
            params = read_entry_members(stream)
            read_entry_members(stream)
            inline.skip(stream, params)
            return
        s = kernel.sym_add(scope, kernel.name_end(), kernel.K_FUNC)
        kernel.set_byte(s, kernel.C_FLAGS, hidden(kernel.SF_PUB | inline.SF_INLINE, how))
        read_signature(stream, s)
        inline.read(stream, s)
        return
    symbol_flags = kernel.SF_PUB
    value = 0
    if flags & LI_EXTERN != 0:
        symbol_flags = kernel.SF_PUB | kernel.SF_EXTERN
        value = kernel.get_word(stream)
    if flags & LI_ASM != 0:
        symbol_flags = kernel.SF_PUB | kernel.SF_ASM
    if flags & LI_RECURSIVE != 0:
        symbol_flags = kernel.SF_PUB | kernel.SF_RECURSIVE
    if flags & LI_INTERRUPT != 0:
        symbol_flags = kernel.SF_PUB | inline.SF_INTERRUPT
    entry_members = 0
    params = read_entry_members(stream)
    results = read_entry_members(stream)
    entry_name_begin()
    how = wanted(scope, True)
    enter(scope, how, again, kernel.K_FUNC, symbol_flags, 0, value, params, results)


def read_constant(stream, scope, in_region, again):
    """A constant entry; `in_region` for a table in a region, whose name follows its value."""
    global entry_members
    read_entry_name(stream)
    t = read_type(stream)
    entry_members = 0
    value = kernel.get_word(stream)
    entry_name_begin()
    how = wanted(scope, True)
    flags = kernel.SF_PUB
    if in_region:
        flags = kernel.SF_PUB | kernel.SF_IN
        value = region_name(stream, how)
    enter(scope, how, again, kernel.K_CONST, flags, t, value, 0, 0)


def region_name(stream, how):
    """The name of a region, after an entry read as `how` says: passed over if it is not read."""
    if how == READ_SKIP:
        inline.skip_name(stream)
        return 0
    return inline.read_name(stream)


def read_variable(stream, scope, again):
    global entry_members
    read_entry_name(stream)
    t = read_type(stream)
    placement, _ = kernel.get(stream)
    entry_name_begin()
    how = wanted(scope, True)
    symbol_flags = kernel.SF_PUB
    value = 0
    if placement == LI_AT:
        symbol_flags = kernel.SF_PUB | kernel.SF_AT
        value = kernel.get_word(stream)
    elif placement == LI_ZP:
        symbol_flags = kernel.SF_PUB | kernel.SF_ZP
    elif placement == LI_NOZP:
        symbol_flags = kernel.SF_PUB | kernel.SF_NOZP
    elif placement == LI_IN:
        symbol_flags = kernel.SF_PUB | kernel.SF_NOZP | kernel.SF_IN
        value = region_name(stream, how)
    elif placement != 0:
        err.fatal(err.E_BAD_INTERFACE)
    entry_members = 0
    enter(scope, how, again, kernel.K_VAR, symbol_flags, t, value, 0, 0)


def read_module_name(stream, number):
    """The module of a name in an LI_USES entry of module `number`'s interface: a string, or
    an empty one for that module itself."""
    length, _ = kernel.get(stream)
    if length == 0:
        return kernel.module_name[number]
    kernel.name_begin()
    for i in range(0, length):
        ch, _ = kernel.get(stream)
        kernel.name_add(ch)
    return kernel.name_end()


def read_uses(stream, number):
    """An LI_USES entry: if the inline function it is for is wanted, a row for each name its
    body names, so that the entries of this module and of the modules it imports are read
    for it. The entries come newest function first, so that a function another one names is
    wanted by the time its own entry is read."""
    read_entry_name(stream)
    entry_name_begin()
    how = wanted(number, False)
    count, _ = kernel.get(stream)
    for i in range(0, count):
        if how == READ_SKIP:
            inline.skip_name(stream)
            inline.skip_name(stream)
        else:
            owner = read_module_name(stream, number)
            add_want(owner, inline.read_name(stream), 0)


def imported_module(stream, scope, again):
    """An LI_MODULE entry: a module that the exported inline functions of module `scope` can
    name. It is imported too, if it is not already (or read again for the names the rows want
    of it), and is a name of that module's scope, which the expansions of its inline functions
    see and the importer's own code does not."""
    name = inline.read_name(stream)
    m = 1
    while m < kernel.module_count and kernel.module_name[m] != name:
        m += 1
    if m == kernel.module_count:
        m = new_module(name, 0)
        read_interface(m, False)
    elif pending(m):
        read_interface(m, True)
    if not again:
        kernel.set_word(kernel.sym_add(scope, name, kernel.K_MODULE), kernel.C_VALUE, m)


def open_interface(name):
    """The interface of the module called `name`, from the first directory that has one."""
    for i in range(0, directory_count):
        stream, ok = kernel.open_in(interface_path(directory[i], name))
        if ok:
            return stream
    err.fatal(err.E_NO_INTERFACE)
    return 0


def read_interface(number, again):
    """Declare what module number `number` exports, as symbols in the scope of that number: its
    types, and of the rest what the rows want (wanted()), or all of it. `again`: it was read
    before, and what it had then is not made again."""
    stream = open_interface(kernel.module_name[number])
    letter_l, _ = kernel.get(stream)
    letter_i, _ = kernel.get(stream)
    version, _ = kernel.get(stream)
    if letter_l != C_UPPER_L or letter_i != C_UPPER_I or version != LI_VERSION:
        err.fatal(err.E_BAD_INTERFACE)
    if inline.read_name(stream) != kernel.module_name[number]:
        err.fatal(err.E_BAD_INTERFACE)
    while True:
        kind, at_end = kernel.get(stream)
        if at_end or kind > LI_USES:
            err.fatal(err.E_BAD_INTERFACE)      # a file cut short has no LI_END
        if kind == LI_END:
            break
        if kind == LI_FUNC:
            read_function(stream, number, again)
        elif kind == LI_CONST or kind == LI_CONST_IN:
            read_constant(stream, number, kind == LI_CONST_IN, again)
        elif kind == LI_VAR:
            read_variable(stream, number, again)
        elif kind == LI_MODULE:
            imported_module(stream, number, again)
        elif kind == LI_USES:
            read_uses(stream, number)
        else:
            read_named_type(stream, number, kind, again)
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


def import_list(name):
    """"(" [ name { "," name } ] ")", after the module's name: a row for each name."""
    lex.next()
    if lex.tok != lex.T_RPAREN:
        while True:
            if lex.tok != lex.T_NAME:
                err.fatal(err.E_NAME_EXPECTED)
            add_want(name, lex.value, W_LISTED)
            lex.next()
            if lex.tok != lex.T_COMMA:
                break
            lex.next()
    lex.expect(lex.T_RPAREN, err.E_RPAREN_EXPECTED)


def import_line():
    """"import" name [ "(" [ name { "," name } ] ")" ] NL. The module's name becomes a symbol;
    what it exports is declared in a scope of its own and reached as name.member: all of it,
    or only what the list names (with what the inline functions listed need, which the
    importer cannot name). Each name listed must be one the module exports."""
    global want_count
    lex.next()
    if lex.tok != lex.T_NAME:
        err.fatal(err.E_NAME_EXPECTED)
    name = lex.value
    if name == kernel.module_name[0]:
        err.fatal(err.E_SELF_IMPORT)
    line = lex.line
    col = lex.col
    s = kernel.sym_add(kernel.SCOPE_MODULE, name, kernel.K_MODULE)
    lex.next()
    want_count = 0
    how = M_WHOLE | M_SHOWN
    if lex.tok == lex.T_LPAREN:
        kernel.set_byte(s, kernel.C_FLAGS, kernel.SF_LIST)
        how = 0
        import_list(name)
    err.position(line, col)
    # An interface read before may have brought the module in, for its inline functions
    # (imported_module()): that reading serves, and what it has is not made twice.
    m = 1
    while m < kernel.module_count and kernel.module_name[m] != name:
        m += 1
    if m == kernel.module_count:
        m = new_module(name, how)
        read_interface(m, False)
    elif how != 0:
        module_read[m] = module_read[m] | how
        read_interface(m, True)
    elif pending(m):
        read_interface(m, True)
    check_found()
    want_count = 0
    kernel.set_word(s, kernel.C_VALUE, m)
    out.imported(name)
    err.position(lex.line, lex.col)
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)


# ---- Functions ---------------------------------------------------------------------------

def function_symbol(flags):
    """The name after "func": declare it as a function with these flags. If it was declared
    `forward`, that symbol is the one, and what follows must repeat that declaration. Returns
    the symbol and whether it is new."""
    if lex.tok != lex.T_NAME:
        err.fatal(err.E_NAME_EXPECTED)
    s, found = kernel.sym_find(kernel.SCOPE_MODULE, lex.value)
    if found and kernel.byte_of(s, kernel.C_KIND) == kernel.K_FUNC and kernel.byte_of(s, kernel.C_FLAGS) & kernel.SF_FORWARD != 0 \
            and flags & kernel.SF_FORWARD == 0:
        if flags & (inline.SF_INLINE | inline.SF_INTERRUPT) != 0:
            err.fatal(err.E_ATTRIBUTES)
        if (kernel.byte_of(s, kernel.C_FLAGS) ^ flags) & kernel.SF_RECURSIVE != 0:
            err.fatal(err.E_FORWARD)
        kernel.set_byte(s, kernel.C_FLAGS, flags)
        lex.next()
        return s, False
    s = kernel.sym_add(kernel.SCOPE_MODULE, lex.value, kernel.K_FUNC)
    kernel.set_byte(s, kernel.C_FLAGS, flags)
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
    kernel.set_byte(s, kernel.C_PARAMS, register_parameters())
    kernel.set_byte(s, kernel.C_RESULTS, register_results())
    lex.expect(lex.T_AT, err.E_AT_EXPECTED)
    kernel.set_word(s, kernel.C_VALUE, expr.constant_number())
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)


def asm_function_declaration(flags):
    """"asm" regHead NL { asmLine NL } "end" NL: a function whose body is assembly, with its
    parameters and results in registers and no slots. It is called like an `extern` function,
    but through its symbol, with a CALL record."""
    lex.next()
    lex.expect(lex.T_FUNC, err.E_FUNC_EXPECTED)
    s, _ = function_symbol(flags | kernel.SF_ASM)
    lex.expect(lex.T_LPAREN, err.E_LPAREN_EXPECTED)
    kernel.set_byte(s, kernel.C_PARAMS, register_parameters())
    kernel.set_byte(s, kernel.C_RESULTS, register_results())
    kernel.scope_begin()                # the names of its labels go when it ends
    gen.function_begin(reg.object_symbol(s))
    asmblock.function_body()
    gen.function_end(object_flags(s) | out.FUNC_REGISTERS)
    kernel.scope_end()
    lex.next()
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)


def object_flags(s):
    """The flags of function `s` as its FUNC record has them."""
    flags = 0
    if kernel.byte_of(s, kernel.C_FLAGS) & kernel.SF_PUB != 0:
        flags = out.FUNC_EXPORTED
    if kernel.byte_of(s, kernel.C_FLAGS) & kernel.SF_RECURSIVE != 0:
        flags = flags | out.FUNC_RECURSIVE
    if kernel.byte_of(s, kernel.C_FLAGS) & inline.SF_INTERRUPT != 0:
        flags = flags | out.FUNC_INTERRUPT
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
    elif index >= kernel.byte_of(s, kernel.C_PARAMS) + kernel.byte_of(s, kernel.C_RESULTS) \
            or kernel.member_type_of(kernel.word_of(s, kernel.C_MEMBERS) + index) != t \
            or kernel.member_value_of(kernel.word_of(s, kernel.C_MEMBERS) + index) != where:
        err.position(line, col)
        err.fatal(err.E_FORWARD)
    return t


def parameters(s, fresh):
    """[ param { "," param } ] ")", after the "(". param = name ":" type. Each is a slot of
    the frame, in order, and a local name. Returns how many."""
    count = 0
    if lex.tok != lex.T_RPAREN:
        while True:
            name = parts.new_name(kernel.SCOPE_LOCAL)
            lex.expect(lex.T_COLON, err.E_COLON_EXPECTED)
            t = member(s, fresh, count, gen.REG_NONE)
            p = kernel.sym_add(kernel.SCOPE_LOCAL, name, kernel.K_LOCAL)
            kernel.set_byte(p, kernel.C_TYPE, t)
            kernel.set_word(p, kernel.C_VALUE, reg.new_slot(typetab.size(t), reg.CLASS_EITHER, reg.SLOT_PARAMETER,
                                               name))
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
        kernel.set_byte(s, kernel.C_PARAMS, count)
    elif count != kernel.byte_of(s, kernel.C_PARAMS):
        err.fatal(err.E_FORWARD)
    count = results(s, fresh, count)
    if fresh:
        kernel.set_byte(s, kernel.C_RESULTS, count)
    elif count != kernel.byte_of(s, kernel.C_RESULTS):
        err.fatal(err.E_FORWARD)
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)


def lasting_variables(first, scope):
    """Write the VAR record of each variable of `scope` from symbol `first` on that lives for
    the whole program. Its weight is complete: nothing that follows can use it."""
    for s in range(first, kernel.sym_count):
        if kernel.byte_of(s, kernel.C_KIND) == kernel.K_VAR and kernel.byte_of(s, kernel.C_SCOPE) == scope \
                and kernel.byte_of(s, kernel.C_FLAGS) & kernel.SF_AT == 0:
            if kernel.byte_of(s, kernel.C_FLAGS) & kernel.SF_IN != 0:
                out.region(kernel.word_of(s, kernel.C_VALUE))
            out.variable(kernel.word_of(s, kernel.C_OBJ), typetab.size(kernel.byte_of(s, kernel.C_TYPE)),
                         parts.zp_class(kernel.byte_of(s, kernel.C_FLAGS)), kernel.byte_of(s, kernel.C_WEIGHT))


def function_declaration(flags):
    """funcDecl = funcHead NL body "end" NL, or "forward" funcHead NL if `flags` say so. An
    interrupt function has no parameters and no results (reported at its name), and entry
    and exit code."""
    lex.next()
    line = lex.line
    col = lex.col
    s, fresh = function_symbol(flags)
    # The scope begins once the function's own name is declared and the token after it has
    # been read: every name made from here on is a parameter's or a local's.
    kernel.scope_begin()
    gen.function_begin(reg.object_symbol(s))
    gen.saves_frame = kernel.byte_of(s, kernel.C_FLAGS) & kernel.SF_RECURSIVE != 0
    head(s, fresh)
    if flags & kernel.SF_FORWARD != 0:
        kernel.scope_end()
        return
    if flags & inline.SF_INTERRUPT != 0:
        if kernel.byte_of(s, kernel.C_PARAMS) + kernel.byte_of(s, kernel.C_RESULTS) != 0:
            err.position(line, col)
            err.fatal(err.E_INTERRUPT_HEAD)
        gen.interrupt_entry()
    gen.receive(s)
    expr.function_body(s)
    if lex.tok != lex.T_END:
        err.fatal(err.E_END_EXPECTED)
    gen.function_end(object_flags(s))
    lasting_variables(kernel.local_base, kernel.SCOPE_LOCAL)
    # The scope ends before "end" is passed over, so that no token read after it can be
    # taken for one of the function's own names.
    kernel.scope_end()
    lex.next()
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)


def inline_declaration(flags):
    """"inline" funcHead NL body "end" NL, from "func" on. The body is not compiled: INLINE
    saves its tokens, which EXPR replays at each call. The names the declaration made are kept
    for the whole module, because the saved tokens use them; its symbols go as a function's do."""
    lex.next()
    s, fresh = function_symbol(flags)
    kernel.scope_begin()
    reg.begin(kernel.NO_OBJ)
    head(s, fresh)
    inline.save(s)
    kernel.local_names = kernel.name_top
    kernel.scope_end()
    lex.next()
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)


def attributed_declaration(flags):
    """"inline" or "interrupt", then funcHead NL body "end" NL. Each attribute goes with
    neither the other, nor `recursive`, nor `asm`."""
    if lex.tok == lex.T_INLINE:
        flags = flags | inline.SF_INLINE
    else:
        flags = flags | inline.SF_INTERRUPT
    lex.next()
    if lex.tok == lex.T_INLINE or lex.tok == lex.T_INTERRUPT or lex.tok == lex.T_RECURSIVE \
            or lex.tok == lex.T_ASM:
        err.fatal(err.E_ATTRIBUTES)
    if lex.tok != lex.T_FUNC:
        err.fatal(err.E_FUNC_EXPECTED)
    if flags & inline.SF_INLINE != 0:
        inline_declaration(flags)
    else:
        function_declaration(flags)


# ---- Constants, and what the end of the module writes ------------------------------------

def constant_declaration(flags):
    """constDecl = "const" name [ ":" type ] "=" initialiser NL. A constant of an array type,
    or one that is a string, is a table: constant data with the constant's name."""
    lex.next()
    name = parts.new_name(kernel.SCOPE_MODULE)
    t = typetab.NO_TYPE
    if lex.tok == lex.T_COLON:
        lex.next()
        line = lex.line
        col = lex.col
        t = expr.type_spec()
        err.position(line, col)
        parts.layout(t)
    region = 0
    if lex.tok == lex.T_IN:
        region = parts.region_name()
    lex.expect(lex.T_ASSIGN, err.E_SYNTAX)
    parts.no_record(t)
    if t == typetab.NO_TYPE and lex.tok == lex.T_STRING:
        t = typetab.array_of(typetab.BYTE_TYPE, lex.string_length + 1, False)
    if typetab.is_array(t):
        symbol = out.symbol(out.SYM_DATA, kernel.module_name[0], 0, name)
        expr.data_region = region
        expr.table_data(t, symbol)
        expr.data_region = 0
        s = kernel.sym_add(kernel.SCOPE_MODULE, name, kernel.K_CONST)
        kernel.set_byte(s, kernel.C_FLAGS, flags)
        kernel.set_byte(s, kernel.C_TYPE, t)
        kernel.set_word(s, kernel.C_OBJ, symbol)
        if region != 0:
            kernel.set_byte(s, kernel.C_FLAGS, flags | kernel.SF_IN)
            kernel.set_word(s, kernel.C_VALUE, region)
        lex.expect(lex.T_NL, err.E_NL_EXPECTED)
        return
    if region != 0:
        parts.not_in_region()
    line = lex.line
    col = lex.col
    expr.constant(t)
    if reg.op_kind[reg.depth - 1] != reg.O_CONST:
        err.position(line, col)
        err.fatal(err.E_NOT_CONST)
    s = kernel.sym_add(kernel.SCOPE_MODULE, name, kernel.K_CONST)
    kernel.set_byte(s, kernel.C_FLAGS, flags)
    kernel.set_byte(s, kernel.C_TYPE, reg.op_type[reg.depth - 1])
    kernel.set_word(s, kernel.C_VALUE, reg.op_value[reg.depth - 1])
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
        if kernel.byte_of(s, kernel.C_SCOPE) == kernel.SCOPE_MODULE and kernel.byte_of(s, kernel.C_KIND) == kernel.K_FUNC \
                and kernel.byte_of(s, kernel.C_FLAGS) & kernel.SF_FORWARD != 0:
            err.fatal(err.E_NO_BODY)


def type_symbol(name, flags):
    s = kernel.sym_add(kernel.SCOPE_MODULE, name, kernel.K_TYPE)
    kernel.set_byte(s, kernel.C_FLAGS, flags)
    return s


def record_type(s):
    """"record" NL { name ":" type NL } "end", for the type that `s` declares. Its symbol and
    type exist before the fields are read, so a field can point to the record."""
    t = typetab.declared(typetab.FORM_RECORD, s)
    kernel.set_byte(s, kernel.C_TYPE, t)
    lex.next()
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)
    while lex.tok != lex.T_END:
        name = parts.new_name(kernel.SCOPE_FIELDS + t)
        lex.expect(lex.T_COLON, err.E_COLON_EXPECTED)
        line = lex.line
        col = lex.col
        f = expr.type_spec()
        err.position(line, col)
        parts.layout(f)
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
    kernel.set_byte(s, kernel.C_TYPE, t)
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
    kernel.set_byte(s, kernel.C_PARAMS, count)
    kernel.set_byte(s, kernel.C_RESULTS, results(s, True, count))


def type_declaration(flags):
    """typeDecl = "type" name "=" ( type | recordType | funcType ) NL."""
    lex.next()
    name = parts.new_name(kernel.SCOPE_MODULE)
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
        parts.layout(t)
        kernel.set_byte(type_symbol(name, flags), kernel.C_TYPE, t)
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)


def enum_declaration(flags):
    """enumDecl = "enum" name NL { name [ "=" constExpr ] NL } "end" NL. The constants are
    numbered on from the one before, from 0; each must fit a byte."""
    lex.next()
    s = type_symbol(parts.new_name(kernel.SCOPE_MODULE), flags)
    t = typetab.declared(typetab.FORM_ENUM, s)
    kernel.set_byte(s, kernel.C_TYPE, t)
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)
    value = 0
    while lex.tok != lex.T_END:
        line = lex.line
        col = lex.col
        name = parts.new_name(kernel.SCOPE_MODULE)
        if lex.tok == lex.T_ASSIGN:
            lex.next()
            line = lex.line
            col = lex.col
            value = expr.constant_number()
        if value > 0xFF:
            err.position(line, col)
            err.fatal(err.E_RANGE)
        c = kernel.sym_add(kernel.SCOPE_MODULE, name, kernel.K_CONST)
        kernel.set_byte(c, kernel.C_FLAGS, flags)
        kernel.set_byte(c, kernel.C_TYPE, t)
        kernel.set_word(c, kernel.C_VALUE, value)
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
        if lex.tok == lex.T_INLINE or lex.tok == lex.T_INTERRUPT:
            err.fatal(err.E_ATTRIBUTES)
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
    elif lex.tok == lex.T_INLINE or lex.tok == lex.T_INTERRUPT:
        attributed_declaration(flags)
    elif lex.tok == lex.T_CONST:
        constant_declaration(flags)
    elif lex.tok == lex.T_TYPE:
        type_declaration(flags)
    elif lex.tok == lex.T_ENUM:
        enum_declaration(flags)
    elif lex.tok == lex.T_VAR:
        expr.variable(flags, expr.LEVEL_MODULE)
        lex.expect(lex.T_NL, err.E_NL_EXPECTED)
    elif lex.tok == lex.T_HASH_IF:
        expr.directive()
        lex.expect(lex.T_NL, err.E_NL_EXPECTED)
    elif lex.tok == lex.T_STATIC:
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
