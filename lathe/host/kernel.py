"""The kernel: what every phase of the compiler needs.

Owns
- the text memory: the part of env.mem that holds what the system must see as zero-terminated
  text (the program's arguments and the name of the file being opened);
- streams: bytes read or written in order, from a file or from memory, so that no phase knows
  which it has;
- the name heap: every name is stored once and is known everywhere by its offset there;
- the symbol table: one column per attribute, indexed by symbol number. Module-level symbols
  come first; the symbols of the function being compiled lie above them and are released when
  it ends. What the columns mean for each kind of symbol is DECL's business.

Reports errors through err.py, which is the kernel's other half.
"""
import env
import err

# ---- Text memory -------------------------------------------------------------------------

TEXT_BASE = 0x0100          # not 0: a pointer of 0 means "none"
TEXT_END = 0x4000
PATH_SIZE = 256

text_top = TEXT_BASE
path = 0                    # the file name being built, PATH_SIZE bytes
path_length = 0


def text_reserve(size):
    """Pointer to `size` bytes of text memory that stay reserved."""
    global text_top
    if text_top + size > TEXT_END:
        err.fatal(err.E_TEXT_FULL)
    start = text_top
    text_top += size
    return start


def keep_argument(i):
    """Pointer to program argument `i`, copied into text memory."""
    global text_top
    start = text_top
    length = env.arg_copy(i, start)
    if start + length + 1 > TEXT_END:
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

MAX_STREAMS = 6
STREAM_FREE = 0
STREAM_IN = 1               # a file being read
STREAM_OUT = 2              # a file being written
STREAM_MEMORY = 3           # bytes of env.mem being read

stream_kind = [0] * MAX_STREAMS
stream_handle = [0] * MAX_STREAMS       # the system's handle of a file
stream_next = [0] * MAX_STREAMS         # memory: pointer to the next byte
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
    return env.read(stream_handle[s])


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

NAME_HEAP_SIZE = 8192
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

MAX_SYMS = 512
MAX_MEMBERS = 1024
MAX_MODULES = 16            # the module being compiled and those it imports

NO_SYM = 0xFFFF
NO_OBJ = 0xFFFF

SCOPE_MODULE = 0            # the module being compiled; 1 and up are imported modules
SCOPE_PREDECLARED = 0xFE    # what the language itself declares
SCOPE_LOCAL = 0xFF          # the function being compiled

K_MODULE = 1                # value: the module's number
K_FUNC = 2                  # members: parameters, then results; value: address if extern
K_CONST = 3                 # type and value

SF_PUB = 1                  # exported
SF_EXTERN = 2               # a routine at a fixed address, parameters and results in registers

sym_name = [0] * MAX_SYMS
sym_scope = [0] * MAX_SYMS
sym_kind = [0] * MAX_SYMS
sym_flags = [0] * MAX_SYMS
sym_type = [0] * MAX_SYMS
sym_value = [0] * MAX_SYMS
sym_obj = [0] * MAX_SYMS        # its number in the object file, NO_OBJ until it is used there
sym_members = [0] * MAX_SYMS    # the first of its members
sym_params = [0] * MAX_SYMS     # how many members are parameters
sym_results = [0] * MAX_SYMS    # how many more are results
sym_link = [0] * MAX_SYMS       # the next older symbol with the same name
sym_count = 0
local_base = 0                  # the first symbol of the function being compiled
local_names = 0                 # name_top when that function began

member_type = [0] * MAX_MEMBERS
member_value = [0] * MAX_MEMBERS    # a parameter's or result's register
member_count = 0

module_name = [0] * MAX_MODULES
module_count = 0


def sym_find(scope, name):
    """The symbol called `name` in exactly this scope, and whether there is one."""
    s = name_word(name + N_SYMBOL)
    while s != NO_SYM and sym_scope[s] != scope:
        s = sym_link[s]
    return s, s != NO_SYM


def sym_lookup(name):
    """What a plain `name` means here: a local, else a module-level symbol, else a predeclared
    one. Symbols of imported modules are skipped: those are written module.name."""
    s = name_word(name + N_SYMBOL)
    while s != NO_SYM and sym_scope[s] != SCOPE_LOCAL and sym_scope[s] != SCOPE_MODULE \
            and sym_scope[s] != SCOPE_PREDECLARED:
        s = sym_link[s]
    return s, s != NO_SYM


def sym_add(scope, name, kind):
    """Declare `name` in `scope`. The other columns start empty."""
    global sym_count
    _, found = sym_find(scope, name)
    if found:
        err.fatal(err.E_DUPLICATE)
    if sym_count == MAX_SYMS:
        err.fatal(err.E_SYMS_FULL)
    s = sym_count
    sym_count += 1
    sym_name[s] = name
    sym_scope[s] = scope
    sym_kind[s] = kind
    sym_flags[s] = 0
    sym_type[s] = 0
    sym_value[s] = 0
    sym_obj[s] = NO_OBJ
    sym_members[s] = member_count
    sym_params[s] = 0
    sym_results[s] = 0
    sym_link[s] = name_word(name + N_SYMBOL)
    name_set_word(name + N_SYMBOL, s)
    return s


def scope_begin():
    """A function begins: symbols and names made from now on are its own."""
    global local_base, local_names
    local_base = sym_count
    local_names = name_top


def scope_end():
    """The function ends: release its symbols and the names only it used."""
    global sym_count
    while sym_count > local_base:
        sym_count -= 1
        # Symbols are released newest first, so each is the first on its name's chain.
        name_set_word(sym_name[sym_count] + N_SYMBOL, sym_link[sym_count])
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
    global text_top, path, name_top, sym_count, local_base, local_names, member_count, module_count
    text_top = TEXT_BASE
    path = text_reserve(PATH_SIZE)
    for s in range(0, MAX_STREAMS):
        stream_kind[s] = STREAM_FREE
    for bucket in range(0, NAME_BUCKETS):
        name_bucket[bucket] = 0
    name_top = 1
    sym_count = 0
    local_base = 0
    local_names = name_top
    member_count = 0
    module_count = 0
