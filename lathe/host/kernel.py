"""The kernel: what every phase of the compiler needs.

Owns
- the text memory: the part of env.mem that holds what the system must see as zero-terminated
  text (the program's arguments and the name of the file being opened);
- the token memory: another part of env.mem, where INLINE keeps its saved tokens, read and
  written only through token_byte() and set_token_byte() and memory streams (it is in a data
  bank when the compiler is banked: lathe/docs/configurations.md, step 10);
- streams: bytes read or written in order, from a file or from memory, so that no phase knows
  which it has;
- the name heap: every name is stored once and is known everywhere by its offset there;
- the symbol table: one column per attribute, indexed by symbol number. Module-level symbols
  come first; the symbols of the function being compiled lie above them and are released when
  it ends. What the columns mean for each kind of symbol is DECL's business; the other modules
  reach them only through byte_of(), word_of(), set_byte(), set_word(), member_type_of() and
  member_value_of();
- the frozen symbols: the functions, constants and variables an imported module exports, kept
  in the name heap in a compact form and made symbols (thawed) only when the importer names
  one. Thawed symbols are numbered down from the top of the table and are never released.

Reports errors through err.py, which is the kernel's other half.
"""
import env
import err

# ---- Text memory -------------------------------------------------------------------------

TEXT_BASE = 0x0100          # not 0: a pointer of 0 means "none"
TEXT_SIZE = 0x0800          # bytes of text memory
TEXT_END = TEXT_BASE + TEXT_SIZE   # (the checks below add TEXT_SIZE, which the small build's tests lower)
PATH_SIZE = 256
TOKEN_BASE = 0x1100         # the token memory, after the text memory however large that is made
TOKEN_SIZE = 0x0800         # bytes of token memory: at least inline.SAVED_SIZE

text_top = TEXT_BASE
path = 0                    # the file name being built, PATH_SIZE bytes
path_length = 0


def text_reserve(size):
    """Pointer to `size` bytes of text memory that stay reserved."""
    global text_top
    if text_top + size > TEXT_BASE + TEXT_SIZE:
        err.fatal(err.E_TEXT_FULL)
    start = text_top
    text_top += size
    return start


def token_start():
    """Pointer to the token memory."""
    return TOKEN_BASE


def token_byte(p):
    """The byte of token memory at `p`."""
    return env.mem[p]


def set_token_byte(p, value):
    env.mem[p] = value


def keep_argument(i):
    """Pointer to program argument `i`, copied into text memory."""
    global text_top
    start = text_top
    length = env.arg_copy(i, start)
    if start + length + 1 > TEXT_BASE + TEXT_SIZE:
        err.fatal(err.E_TEXT_FULL)
    text_top += length + 1
    return start


def path_begin():
    global path_length
    path_length = 0


def path_add(ch):
    global path_length
    if path_length + 1 >= PATH_SIZE:        # one byte is kept for the zero at the end
        err.fatal(err.E_PATH_LONG)
    env.mem[path + path_length] = ch
    path_length += 1


def path_add_text(text):
    while env.mem[text] != 0:
        path_add(env.mem[text])
        text += 1


def path_add_name(name):
    for i in range(0, name_length(name)):
        path_add(name_char(name, i))


def path_end():
    """Pointer to the finished file name."""
    env.mem[path + path_length] = 0
    return path


# ---- Streams -----------------------------------------------------------------------------

MAX_STREAMS = 10
STREAM_FREE = 0
STREAM_IN = 1               # a file being read
STREAM_OUT = 2              # a file being written
STREAM_MEMORY = 3           # bytes of env.mem being read
STREAM_ENDED = 4            # a file being read whose end has been read: the machine would give
                            # its first byte again (the emulator rewinds a file at its end)

stream_kind = bytearray(MAX_STREAMS)
stream_handle = bytearray(MAX_STREAMS)       # the system's handle of a file
stream_next = [0] * MAX_STREAMS         # memory: pointer to the next byte; a file being read:
                                        # how many bytes have been read (decl.read_interface())
stream_limit = [0] * MAX_STREAMS        # memory: pointer past the last byte


def stream_new(kind):
    for s in range(0, MAX_STREAMS):
        if stream_kind[s] == STREAM_FREE:
            stream_kind[s] = kind
            return s
    err.fatal(err.E_STREAMS_FULL)
    return 0


def open_file(name, kind):
    if kind == STREAM_IN:
        handle = env.open_in(name)
    else:
        handle = env.open_out(name)
    if handle == 0:
        return 0, False
    s = stream_new(kind)
    stream_handle[s] = handle
    stream_next[s] = 0
    return s, True


def open_in(name):
    """Open the file whose name is at `name` for reading. Returns the stream and True, or False."""
    return open_file(name, STREAM_IN)


def open_out(name):
    """Create the file whose name is at `name`. Returns the stream and True, or False."""
    return open_file(name, STREAM_OUT)


def open_memory(start, limit):
    """A stream that reads env.mem from `start` up to but not including `limit`."""
    s = stream_new(STREAM_MEMORY)
    stream_next[s] = start
    stream_limit[s] = limit
    return s


def close(s):
    if stream_kind[s] != STREAM_MEMORY:
        env.close(stream_handle[s])
    stream_kind[s] = STREAM_FREE


def get(s):
    """The stream's next byte and False, or 0 and True at its end."""
    if stream_kind[s] == STREAM_MEMORY:
        if stream_next[s] == stream_limit[s]:
            return 0, True
        stream_next[s] += 1
        return env.mem[stream_next[s] - 1], False
    if stream_kind[s] == STREAM_ENDED:
        return 0, True
    b, at_end = env.read(stream_handle[s])
    stream_next[s] += 1
    if at_end:
        stream_kind[s] = STREAM_ENDED
    return b, at_end


def get_word(s):
    """The next two bytes as a number. Bytes past the end read as zero."""
    low, _ = get(s)
    high, _ = get(s)
    return low | (high << 8)


def put(s, value):
    """Write one byte."""
    env.write(stream_handle[s], value)


def put_word(s, value):
    """Write a number as two bytes, low byte first."""
    put(s, value & 0xFF)
    put(s, (value >> 8) & 0xFF)


def put_name(s, name):
    """Write a name as a string: its length, then its characters."""
    put(s, name_length(name))
    for i in range(0, name_length(name)):
        put(s, name_char(name, i))


# ---- The name heap -----------------------------------------------------------------------
#
# An entry is: link to the next name in the same hash bucket (2 bytes), the newest symbol
# with this name (2), a token number (1), the length (1), the characters. A name is known
# by the offset of its entry; 0 is no name.
#
# A name is built in place above the heap's top, one character at a time, and only kept if
# it is new, so looking a name up copies nothing.

NAME_HEAP_SIZE = 9216
NAME_BUCKETS = 64           # a power of two
MAX_NAME = 31               # significant characters

N_LINK = 0
N_SYMBOL = 2
N_TOKEN = 4
N_LENGTH = 5
N_TEXT = 6

names = bytearray(NAME_HEAP_SIZE)
name_bucket = [0] * NAME_BUCKETS
name_top = 1
new_length = 0
new_hash = 0


def name_word(offset):
    return names[offset] | (names[offset + 1] << 8)


def name_set_word(offset, value):
    names[offset] = value & 0xFF
    names[offset + 1] = (value >> 8) & 0xFF


def name_begin():
    """Start building a name."""
    global new_length, new_hash
    if name_top + N_TEXT + MAX_NAME > NAME_HEAP_SIZE:
        err.fatal(err.E_NAMES_FULL)
    new_length = 0
    new_hash = 0


def name_add(ch):
    """Add a character to the name being built. Characters after the 31st are dropped."""
    global new_length, new_hash
    if new_length < MAX_NAME:
        names[name_top + N_TEXT + new_length] = ch
        new_length += 1
        new_hash = (((new_hash << 1) | (new_hash >> 7)) ^ ch) & 0xFF


def name_is_new(n):
    """True unless entry `n` spells the name being built."""
    if names[n + N_LENGTH] != new_length:
        return True
    for i in range(0, new_length):
        if names[n + N_TEXT + i] != names[name_top + N_TEXT + i]:
            return True
    return False


def name_end():
    """Finish the name being built. Returns the name, the same one for the same spelling."""
    global name_top
    bucket = new_hash & (NAME_BUCKETS - 1)
    n = name_bucket[bucket]
    while n != 0 and name_is_new(n):
        n = name_word(n + N_LINK)
    if n != 0:
        return n
    n = name_top
    name_set_word(n + N_LINK, name_bucket[bucket])
    name_set_word(n + N_SYMBOL, NO_SYM)
    names[n + N_TOKEN] = 0
    names[n + N_LENGTH] = new_length
    name_bucket[bucket] = n
    name_top += N_TEXT + new_length
    return n


def name_length(n):
    return names[n + N_LENGTH]


def name_char(n, i):
    return names[n + N_TEXT + i]


def name_token(n):
    """The token number LEX gave this name: its keyword, or 0 for an ordinary name."""
    return names[n + N_TOKEN]


def name_set_token(n, token):
    names[n + N_TOKEN] = token


def names_release(mark):
    """Forget every name made since name_top was `mark`. None may still have a symbol."""
    global name_top
    for bucket in range(0, NAME_BUCKETS):
        n = name_bucket[bucket]
        while n >= mark:                    # the newest names are first in each bucket
            n = name_word(n + N_LINK)
        name_bucket[bucket] = n
    name_top = mark


# ---- The symbol table --------------------------------------------------------------------
#
# Symbols with the same name are chained from the name, newest first, so a name leads
# straight to its symbols and the table needs no hash of its own. The chains are short:
# one symbol per module that has the name, and the local that hides it.

MAX_SYMS = 560
MAX_MEMBERS = 432
MAX_MODULES = 16            # the module being compiled and those it imports

NO_SYM = 0xFFFF
NO_OBJ = 0xFFFF

SCOPE_MODULE = 0            # the module being compiled; 1 and up are imported modules
SCOPE_FIELDS = 0x40         # plus a record type's number: the scope of that record's fields
SCOPE_PREDECLARED = 0xFE    # what the language itself declares
SCOPE_LOCAL = 0xFF          # the function being compiled

K_MODULE = 1                # value: the module's number
K_FUNC = 2                  # members: parameters, then results; value: address if extern
K_CONST = 3                 # type and value
K_VAR = 4                   # a variable that lives for the whole program; value: address if SF_AT
K_LOCAL = 5                 # a parameter or local of the function being compiled; value: its slot
K_BUILTIN = 6               # a function the language declares; value: which one
K_TYPE = 7                  # a named type: type; a function type's also has members, as K_FUNC
K_FIELD = 8                 # a field of a record: type, and value: its offset in the record

SF_PUB = 1                  # exported
SF_EXTERN = 2               # a routine at a fixed address, parameters and results in registers
SF_FORWARD = 4              # a function declared `forward` whose body has not come yet
SF_AT = 8                   # a variable at a fixed address
SF_ZP = 16                  # a variable declared `zp`
SF_NOZP = 32                # a variable declared `nozp`
SF_ASM = 64                 # an `asm` function: parameters and results in registers, no slots
SF_ROWS = 128               # a variable declared `rows` (while its declaration is read)
SF_RECURSIVE = 128          # a function declared `recursive` (the bit SF_ROWS has on a variable)
SF_IN = 2                   # a variable or constant table `in REGION` (provisional, 2026-11-14):
                            # its value is the region's name (the bit SF_EXTERN has on a function)
SF_HIDDEN = 4               # an imported symbol the importer's list does not name: only the bodies
                            # of inline functions use it (the bit SF_FORWARD has, which no
                            # imported symbol has)
SF_LIST = 4                 # a module's symbol: its `import` has a list (the same bit)

# A symbol's columns: the byte columns one after another in sym_bytes, the word columns in
# sym_words, each MAX_SYMS rows; byte_of(), word_of(), set_byte() and set_word() reach them by
# number (C_*) for the other modules.
C_SCOPE = 0                     # the byte columns
C_KIND = 1
C_FLAGS = 2
C_TYPE = 3                      # a type number: typetab has MAX_TYPES = 64
C_WEIGHT = 4                    # a variable: how much it gains from zero page (docs/codegen.md)
C_PARAMS = 5                    # how many members are parameters
C_RESULTS = 6                   # how many more are results
BYTE_COLUMNS = 7
C_NAME = 0                      # the word columns
C_VALUE = 1
C_OBJ = 2                       # its number in the object file, NO_OBJ until it is used there
C_MEMBERS = 3                   # the first of its members
C_LINK = 4                      # the next older symbol with the same name
WORD_COLUMNS = 5
SCOPE_AT = C_SCOPE * MAX_SYMS   # where each column starts
KIND_AT = C_KIND * MAX_SYMS
FLAGS_AT = C_FLAGS * MAX_SYMS
TYPE_AT = C_TYPE * MAX_SYMS
WEIGHT_AT = C_WEIGHT * MAX_SYMS
PARAMS_AT = C_PARAMS * MAX_SYMS
RESULTS_AT = C_RESULTS * MAX_SYMS
NAME_AT = C_NAME * MAX_SYMS
VALUE_AT = C_VALUE * MAX_SYMS
OBJ_AT = C_OBJ * MAX_SYMS
MEMBERS_AT = C_MEMBERS * MAX_SYMS
LINK_AT = C_LINK * MAX_SYMS
SYM_BYTE_SIZE = BYTE_COLUMNS * MAX_SYMS
SYM_WORD_SIZE = WORD_COLUMNS * MAX_SYMS

sym_bytes = bytearray(SYM_BYTE_SIZE)
sym_words = [0] * SYM_WORD_SIZE
byte_base = [0] * BYTE_COLUMNS  # where each byte column starts in sym_bytes (init())
word_base = [0] * WORD_COLUMNS
sym_count = 0
thaw_top = MAX_SYMS             # the lowest thawed symbol: they lie from here to MAX_SYMS - 1
local_base = 0                  # the first symbol of the function being compiled
local_names = 0                 # name_top when that function began

member_type = bytearray(MAX_MEMBERS)
member_value = bytearray(MAX_MEMBERS)    # a parameter's or result's register
member_count = 0

module_name = [0] * MAX_MODULES
module_count = 0


# ---- The columns, for the other modules --------------------------------------------------
#
# Other modules read and write the columns of a symbol and of a member only through these
# functions: in the twin the columns are in the region SYMS (docs/architecture.md, "What stays
# in memory"), used only inside blocks of kernel's.

def byte_of(s, column):
    """Byte column `column` (C_SCOPE to C_RESULTS) of symbol `s`."""
    return sym_bytes[byte_base[column] + s]


def word_of(s, column):
    """Word column `column` (C_NAME to C_LINK) of symbol `s`."""
    return sym_words[word_base[column] + s]


def set_byte(s, column, value):
    sym_bytes[byte_base[column] + s] = value


def set_word(s, column, value):
    sym_words[word_base[column] + s] = value


def member_type_of(m):
    """Member `m`'s type."""
    return member_type[m]


def member_value_of(m):
    """Member `m`'s register."""
    return member_value[m]


def chain_walk(scope, s):
    """The symbol of `scope` on the chain that starts at symbol `s`, or NO_SYM."""
    while s != NO_SYM and sym_bytes[SCOPE_AT + s] != scope:
        s = sym_words[LINK_AT + s]
    return s


def chain_find(scope, name):
    """The symbol of `scope` on the chain of name entry `name`, or NO_SYM."""
    return chain_walk(scope, name_word(name + N_SYMBOL))


def sym_find(scope, name):
    """The symbol called `name` in exactly this scope, and whether there is one. A frozen
    symbol of an imported module is thawed: from then on it is a symbol like another."""
    s = chain_find(scope, name)
    if s != NO_SYM or scope == SCOPE_MODULE or scope >= SCOPE_FIELDS:
        return s, s != NO_SYM
    # Thawed already, on the chain of another entry with the same spelling (thaw())?
    oldest = name
    n = name_bucket[spelling_hash(name) & (NAME_BUCKETS - 1)]
    while n != 0:
        if n != name and same_spelling(n, name):
            s = chain_find(scope, n)
            if s != NO_SYM:
                return s, True
            if n < oldest:
                oldest = n
        n = name_word(n + N_LINK)
    before = 0
    f = module_frozen[scope]
    while f != 0 and not same_spelling(f, name):
        before = f
        f = name_word(f + N_LINK)
    if f == 0:
        return NO_SYM, False
    if before == 0:
        module_frozen[scope] = name_word(f + N_LINK)
    else:
        name_set_word(before + N_LINK, name_word(f + N_LINK))
    return thaw(scope, f, oldest), True


def module_find(m, name):
    """The symbol `name` of the module that module symbol `m` stands for, and whether there is
    one: what `m.name` means. Through an `import` with a list (SF_LIST), only what the list
    names can be named (error 101): not what the bodies of inline functions alone need."""
    listed = byte_of(m, C_FLAGS) & SF_LIST != 0
    s, found = sym_find(word_of(m, C_VALUE), name)
    if listed and (not found or byte_of(s, C_FLAGS) & SF_HIDDEN != 0):
        err.fatal(err.E_NOT_LISTED)
    return s, found


def name_symbol(name):
    """The newest symbol called `name`, or NO_SYM: the first on its chain (sym_link)."""
    return name_word(name + N_SYMBOL)


def name_set_symbol(name, s):
    """Make `s` the first symbol on the chain of `name`."""
    name_set_word(name + N_SYMBOL, s)


def sym_lookup(name):
    """What a plain `name` means here: a local, else a module-level symbol, else a predeclared
    one. Symbols of imported modules are skipped: those are written module.name."""
    s = name_word(name + N_SYMBOL)
    while s != NO_SYM:
        scope = byte_of(s, C_SCOPE)
        if scope == SCOPE_LOCAL or scope == SCOPE_MODULE or scope == SCOPE_PREDECLARED:
            break
        s = word_of(s, C_LINK)
    return s, s != NO_SYM


def sym_new(s, scope, name, kind):
    """Make `s` the symbol called `name` in `scope`, the newest on its name's chain. The other
    columns start empty."""
    set_word(s, C_LINK, name_symbol(name))
    name_set_symbol(name, s)
    set_word(s, C_NAME, name)
    set_byte(s, C_SCOPE, scope)
    set_byte(s, C_KIND, kind)
    for c in range(C_FLAGS, BYTE_COLUMNS):
        set_byte(s, c, 0)
    set_word(s, C_VALUE, 0)
    set_word(s, C_OBJ, NO_OBJ)
    set_word(s, C_MEMBERS, member_count)


def sym_add(scope, name, kind):
    """Declare `name` in `scope`. The other columns start empty."""
    global sym_count
    _, found = sym_find(scope, name)
    if found:
        err.fatal(err.E_DUPLICATE)
    if sym_count == thaw_top:
        err.fatal(err.E_SYMS_FULL)
    sym_count += 1
    sym_new(sym_count - 1, scope, name, kind)
    return sym_count - 1


# ---- Frozen symbols ----------------------------------------------------------------------
#
# What an imported module exports, but for its types and its inline functions, is not entered
# in the symbol table when the interface is read: each function, constant and variable is a
# frozen entry in the name heap, on a list of its module's (module_frozen). An entry has the
# form of a name entry that is not yet in its hash bucket: its link is the next entry of the
# list, and where a name has its symbol and its token the entry has the symbol's kind, flags
# and type. After the name's characters come its value (2), and for a function its parameters,
# its results and for each member its type and its register. sym_find() thaws an entry when the
# importer first names it: the entry becomes the symbol's name, in its bucket.

F_KIND = 2                  # from the start of the entry
F_FLAGS = 3
F_TYPE = 4
F_VALUE = 0                 # from the end of the name's characters
F_SIZE = 2                  # what a constant or a variable has there
F_PARAMS = 2                # a function's
F_RESULTS = 3
F_MEMBERS = 4               # the size of what a function has there before its members

module_frozen = [0] * MAX_MODULES     # each module's first frozen entry, or 0


def spelling_hash(n):
    """The hash name_add() gives the spelling of entry `n`."""
    h = 0
    for i in range(0, names[n + N_LENGTH]):
        h = (((h << 1) | (h >> 7)) ^ names[n + N_TEXT + i]) & 0xFF
    return h


def same_spelling(a, b):
    """True if name entries `a` and `b` spell the same name."""
    if names[a + N_LENGTH] != names[b + N_LENGTH]:
        return False
    for i in range(0, names[a + N_LENGTH]):
        if names[a + N_TEXT + i] != names[b + N_TEXT + i]:
            return False
    return True


def built_symbol(scope):
    """The symbol of `scope` whose name spells the name being built (name_begin(), name_add()),
    or NO_SYM. A frozen entry is not looked at, and nothing is thawed."""
    n = name_bucket[new_hash & (NAME_BUCKETS - 1)]
    while n != 0:
        if not name_is_new(n):
            s = chain_find(scope, n)
            if s != NO_SYM:
                return s
        n = name_word(n + N_LINK)
    return NO_SYM


def built_frozen(scope):
    """The frozen entry of imported module `scope` that spells the name being built, or 0."""
    n = module_frozen[scope]
    while n != 0 and name_is_new(n):
        n = name_word(n + N_LINK)
    return n


def built_is(n):
    """True if name entry `n` spells the name being built."""
    return not name_is_new(n)


def name_hash(n):
    """The hash of name entry `n`'s spelling, as new_hash is of the name being built."""
    return spelling_hash(n)


def built_loaded(scope, show):
    """True if imported module `scope` has a symbol or a frozen entry that spells the name being
    built. If `show`, the importer can name it from now on (SF_HIDDEN is cleared)."""
    s = built_symbol(scope)
    if s != NO_SYM:
        if show:
            set_byte(s, C_FLAGS, byte_of(s, C_FLAGS) & ~SF_HIDDEN)
        return True
    f = built_frozen(scope)
    if f == 0:
        return False
    if show:
        names[f + F_FLAGS] = names[f + F_FLAGS] & ~SF_HIDDEN
    return True


def sym_thawed(scope, name, kind):
    """Declare `name` in imported module `scope` as a thawed symbol, numbered from the top of
    the table: an entry an import list names, whose name the list has made already, is made a
    symbol at once instead of a frozen entry. The other columns start empty. A name the module
    already has is error 41."""
    global thaw_top
    _, found = sym_find(scope, name)
    if found:
        err.fatal(err.E_DUPLICATE)
    if thaw_top == sym_count:
        err.fatal(err.E_SYMS_FULL)
    thaw_top -= 1
    sym_new(thaw_top, scope, name, kind)
    return thaw_top


def freeze(scope, kind, flags, t, value, params, results):
    """Make the name being built (name_begin(), name_add()) a frozen symbol of imported module
    `scope` with these columns. Its members follow, with freeze_member(). A name the module
    already has is error 41, as sym_add() would give."""
    global name_top
    size = F_SIZE
    if kind == K_FUNC:
        size = F_MEMBERS + 2 * (params + results)
    if name_top + N_TEXT + new_length + size > NAME_HEAP_SIZE:
        err.fatal(err.E_NAMES_FULL)
    if built_symbol(scope) != NO_SYM or built_frozen(scope) != 0:
        err.fatal(err.E_DUPLICATE)
    n = name_top
    name_set_word(n + N_LINK, module_frozen[scope])
    names[n + F_KIND] = kind
    names[n + F_FLAGS] = flags
    names[n + F_TYPE] = t
    names[n + N_LENGTH] = new_length
    module_frozen[scope] = n
    p = n + N_TEXT + new_length
    name_set_word(p + F_VALUE, value)
    name_top = p + F_SIZE
    if kind == K_FUNC:
        names[p + F_PARAMS] = params
        names[p + F_RESULTS] = results
        name_top = p + F_MEMBERS


def freeze_member(t, value):
    """The next member of the newest frozen symbol."""
    global name_top
    names[name_top] = t
    names[name_top + 1] = value
    name_top += 2


def thaw(scope, f, oldest):
    """Make frozen entry `f`, taken off its module's list, a symbol of `scope`, numbered from
    the top of the table. `oldest` is the oldest name of its spelling (sym_find()). If that is
    older than the entry (made before the import was read: by an import list, an interface read
    before, or the module itself), it stays the name and the symbol goes on its chain: the
    entry put in its bucket would be ahead of it, and the lexer would give the entry for the
    spelling. Otherwise the entry becomes the name, in its bucket, in its place by age, so that
    names_release() still finds the newest names first."""
    global thaw_top
    if thaw_top == sym_count:
        err.fatal(err.E_SYMS_FULL)
    thaw_top -= 1
    s = thaw_top
    p = f + N_TEXT + names[f + N_LENGTH]
    kind = names[f + F_KIND]                # read before the entry is made a name
    flags = names[f + F_FLAGS]
    t = names[f + F_TYPE]
    value = name_word(p + F_VALUE)
    params = 0
    results = 0
    if kind == K_FUNC:
        params = names[p + F_PARAMS]
        results = names[p + F_RESULTS]
    name = oldest
    if oldest > f:
        name = f
        name_set_word(f + N_SYMBOL, NO_SYM)
        names[f + N_TOKEN] = 0
    sym_new(s, scope, name, kind)
    set_byte(s, C_FLAGS, flags)
    set_byte(s, C_TYPE, t)
    set_word(s, C_VALUE, value)
    set_byte(s, C_PARAMS, params)
    set_byte(s, C_RESULTS, results)
    for i in range(0, params + results):
        member_add(names[p + F_MEMBERS + 2 * i], names[p + F_MEMBERS + 2 * i + 1])
    if oldest < f:
        return s
    bucket = spelling_hash(f) & (NAME_BUCKETS - 1)
    n = name_bucket[bucket]
    if n < f:
        name_set_word(f + N_LINK, n)
        name_bucket[bucket] = f
        return s
    while name_word(n + N_LINK) > f:
        n = name_word(n + N_LINK)
    name_set_word(f + N_LINK, name_word(n + N_LINK))
    name_set_word(n + N_LINK, f)
    return s


def scope_begin():
    """A function begins: symbols and names made from now on are its own."""
    global local_base, local_names
    local_base = sym_count
    local_names = name_top


def sym_release(base):
    """Release the symbols from `base` up. Their names stay."""
    global sym_count
    while sym_count > base:
        sym_count -= 1
        # Symbols are released newest first, so each is the first on its name's chain.
        name_set_symbol(word_of(sym_count, C_NAME), word_of(sym_count, C_LINK))


def scope_end():
    """The function ends: release its symbols and the names only it used."""
    sym_release(local_base)
    names_release(local_names)


def member_add(t, value):
    """Add a member to the newest symbol. Returns the member's number."""
    global member_count
    if member_count == MAX_MEMBERS:
        err.fatal(err.E_MEMBERS_FULL)
    member_type[member_count] = t
    member_value[member_count] = value
    member_count += 1
    return member_count - 1


def module_add(name):
    """Give the next module number to the module called `name`."""
    global module_count
    if module_count == MAX_MODULES:
        err.fatal(err.E_MODULES_FULL)
    module_name[module_count] = name
    module_count += 1
    return module_count - 1


def init():
    global text_top, path, name_top, sym_count, thaw_top, local_base, local_names, member_count, \
        module_count
    text_top = TEXT_BASE
    path = text_reserve(PATH_SIZE)
    for s in range(0, MAX_STREAMS):
        stream_kind[s] = STREAM_FREE
    for bucket in range(0, NAME_BUCKETS):
        name_bucket[bucket] = 0
    name_top = 1
    sym_count = 0
    thaw_top = MAX_SYMS
    local_base = 0
    local_names = name_top
    for m in range(0, MAX_MODULES):
        module_frozen[m] = 0
    member_count = 0
    module_count = 0
    byte_base[C_SCOPE] = SCOPE_AT
    byte_base[C_KIND] = KIND_AT
    byte_base[C_FLAGS] = FLAGS_AT
    byte_base[C_TYPE] = TYPE_AT
    byte_base[C_WEIGHT] = WEIGHT_AT
    byte_base[C_PARAMS] = PARAMS_AT
    byte_base[C_RESULTS] = RESULTS_AT
    word_base[C_NAME] = NAME_AT
    word_base[C_VALUE] = VALUE_AT
    word_base[C_OBJ] = OBJ_AT
    word_base[C_MEMBERS] = MEMBERS_AT
    word_base[C_LINK] = LINK_AT
