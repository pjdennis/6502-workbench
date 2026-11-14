"""Names: which symbols are found by name, what each object file's symbol numbers stand for,
and names read again from the files.

A symbol needs to be found by name only if more than one SYM record names it: a record of
another file, or a second record of the same file. Every other symbol is named by one record
and is its file's own. The first reading of all (mark_all) is quiet and holds a hash of each
name: it marks, in a table of 8192 bits, the hash of every name some file has a SYM record for
and does not define, every pointer class, and every name that two definitions share. While the
files are then read for the tables (lk_scan), a marked name is kept in a heap and found through
chains, and an unmarked one makes a new symbol and is not kept. A false match only keeps a name
that need not have been: names that are kept are compared in full. Heap, chains and marks are
in lk_tab.work, and nothing holds a name once the files are read.

While the files are read every symbol has a number (lk_sym.new_number) and two words at the top
of the work area: what it stands for so far, lk_sym.UNDEF and its number until something defines
it and then the reference of what does (bind, now); and its first call + 1 if it is a function
or a class, the weight given to it so far if it is a variable, with X_INIT and X_MAIN above
(more). Once the files are read, resolve() replaces each number by what it stands for.

`local` keeps, for every object file, the symbol each of its numbers stands for, so later
readings of a file need no names. A name that is written, in an error message or the map, is
read from the first object file that has a SYM record for the symbol (error_name), or by a
reading of each file that holds the names of that file (lk_map).
"""
import env
import lk_envf
import lk_err
import lk_file
import lk_rec
import lk_sym
import lk_tab

MAX_OBJECTS = 40
MAX_LOCALS = 4000                   # SYM records in all object files together

object_count = 0
obj_first = [0] * (MAX_OBJECTS + 1) # row in `local` of each object's symbol 0
obj_fn = [0] * (MAX_OBJECTS + 1)    # row in lk_tab.fn_ of each object's first function
obj_def = [0] * (MAX_OBJECTS + 1)   # row in lk_tab.def_ of each object's first definition
local = [0] * MAX_LOCALS
local_count = 0

# While the files are read for the tables: lk_tab.work, in words, from MARKS up (lk_scan's
# waiting weights are below it).
MARKS = 256                         # 8192 bits: the names to keep
HEADS = MARKS + 512                 # 512 chains of kept names
HEAP = HEADS + 512                  # the heap, up to the symbols' words at the top
DEFS = HEAP                         # mark_all: 32768 bits, the names some file defines
HEAP_START = 2 * HEAP               # in bytes
HEAP_END = 2 * lk_tab.WORK_SIZE     # without the symbols' words
ENTRY = 5                           # a kept name: next in its chain + 1 (2), symbol (2),
                                    # length (1), then the characters
X_LOW = 0x0FFF                      # in a symbol's second word: a variable's weight so far
X_FSTART = 0x1000                   # named FARCALL.start, the far-call module's (lk_envf.farcall)
X_FCALL = 0x2000                    # named FARCALL.call
X_INIT = 0x4000                     # a function named `module.$init`
X_MAIN = 0x8000                     # named MAINMODULE.main

# mark_all: what each `local` entry of the file being read holds.
L_HASH = 0x7FFF
L_DEFINED = 0x8000

heap_top = HEAP_START
pending = 0                         # length of the name being read, at heap_top + ENTRY
pend_hash = 0                       # its hash so far
main_length = 0                     # MAINMODULE.main is at HEAP_START
main_sym = lk_tab.NONE              # what it stands for, once something defines it
fc_call = lk_tab.NONE               # what FARCALL.call and FARCALL.start stand for, once defined
fc_start = lk_tab.NONE

MAIN_SUFFIX = b".main"
INIT_SUFFIX = b".$init"
CALL_SUFFIX = b".call"
START_SUFFIX = b".start"


# ---- bytes and bits in the work area

def get_b(pos):
    """The byte at byte offset `pos` of the work area."""
    if (pos & 1) != 0:
        return lk_tab.work[pos >> 1] >> 8
    return lk_tab.work[pos >> 1] & 0xFF


def put_b(pos, value8):
    i = pos >> 1
    if (pos & 1) != 0:
        lk_tab.work[i] = (lk_tab.work[i] & 0xFF) | (value8 << 8)
    else:
        lk_tab.work[i] = (lk_tab.work[i] & 0xFF00) | value8


def get_bit(table, n):
    """Bit n of the bit table at word `table` of the work area."""
    return (lk_tab.work[table + (n >> 4)] & (1 << (n & 15))) != 0


def set_bit(table, n):
    lk_tab.work[table + (n >> 4)] |= 1 << (n & 15)


def step(h, c):
    """The hash of a name so far, h, and its next character c."""
    return (h * 31 + c) & 0xFFFF


def global_sym(obj, number):
    """The symbol that object file obj calls `number`."""
    if number >= obj_first[obj + 1] - obj_first[obj]:
        lk_file.fail(lk_err.E_DAMAGED, lk_file.ARG_OBJECT + obj)
    return local[obj_first[obj] + number]


# ---- the names to keep

def mark_object(obj):
    """Mark what object file obj makes worth keeping. `local` holds, for each of its SYM
    records, the hash of its name and whether the file defines it."""
    if not lk_rec.open_quiet(obj):
        return
    if lk_rec.advance() != lk_rec.R_MOD or lk_rec.get_byte() != lk_rec.VERSION:
        lk_rec.close()
        return
    count = 0
    kind = lk_rec.advance()
    while kind != lk_rec.R_END:
        if kind == lk_rec.R_SYM:
            sym_kind = lk_rec.get_byte()
            size = lk_rec.get_byte()
            h = 0
            for i in range(0, size):
                h = step(h, lk_rec.get_byte())
            if count < MAX_LOCALS:
                local[count] = h & L_HASH
                # A pointer class is described by every file that uses it, defined by none.
                if sym_kind == lk_sym.CLASS:
                    set_bit(MARKS, h & 0x1FFF)
                count += 1
        elif kind == lk_rec.R_FUNC or kind == lk_rec.R_VAR or kind == lk_rec.R_DATA:
            n = lk_rec.get_word()
            if n < count:
                local[n] |= L_DEFINED
        kind = lk_rec.advance()
    lk_rec.close()
    for i in range(0, count):
        h = local[i] & L_HASH
        if (local[i] & L_DEFINED) == 0 or get_bit(DEFS, h):
            set_bit(MARKS, h & 0x1FFF)
        else:
            set_bit(DEFS, h)


def mark_all():
    """The first reading of every object file, which marks the names to keep."""
    for i in range(0, 512):
        lk_tab.work[MARKS + i] = 0
    for i in range(0, 2048):
        lk_tab.work[DEFS + i] = 0
    for obj in range(0, object_count):
        mark_object(obj)


def begin():
    """Before the tables are read: no name kept yet, and MAINMODULE.main to look out for."""
    global heap_top, main_length, main_sym, fc_call, fc_start
    for i in range(0, 512):
        lk_tab.work[HEADS + i] = 0
    main_length = lk_file.arg_length(lk_file.ARG_MAIN)
    for i in range(0, main_length):
        c = env.mem[lk_file.PATH + i]
        if c >= 65 and c <= 90:
            c += 32
        put_b(HEAP_START + i, c)
    for i in range(0, len(MAIN_SUFFIX)):
        put_b(HEAP_START + main_length + i, MAIN_SUFFIX[i])
    main_length += len(MAIN_SUFFIX)
    heap_top = HEAP_START + main_length
    main_sym = lk_tab.NONE
    fc_call = lk_tab.NONE
    fc_start = lk_tab.NONE


# ---- the name being read

def name_begin():
    """Start collecting a name."""
    global pending, pend_hash
    pending = 0
    pend_hash = 0


def heap_limit():
    """Where the heap must end: below the words of the symbols so far."""
    return HEAP_END - 4 * lk_sym.count


def name_add(c):
    """Add one character to the pending name."""
    global pending, pend_hash
    if pending == 255 or heap_top + ENTRY + pending + 1 > heap_limit():
        lk_err.fail(lk_err.E_NAMES)
    put_b(heap_top + ENTRY + pending, c)
    pending += 1
    pend_hash = step(pend_hash, c)


def pending_char(i):
    return get_b(heap_top + ENTRY + i)


def name_is(pos):
    """True if the pending name equals the kept name at `pos`."""
    if get_b(pos + 4) != pending:
        return False
    for i in range(0, pending):
        if get_b(pos + ENTRY + i) != pending_char(i):
            return False
    return True


def is_main():
    if pending != main_length:
        return False
    for i in range(0, pending):
        if pending_char(i) != get_b(HEAP_START + i):
            return False
    return True


def is_init():
    """True if the pending name ends in `.$init`."""
    size = len(INIT_SUFFIX)
    if pending < size:
        return False
    for i in range(0, size):
        if pending_char(pending - size + i) != INIT_SUFFIX[i]:
            return False
    return True


def is_farcall(suffix):
    """True if the pending name is the far-call module's name followed by `suffix`."""
    f = lk_envf.farcall
    if f == 0:
        return False
    size = lk_envf.text[f - 1]
    if pending != size + len(suffix):
        return False
    for i in range(0, size):
        if pending_char(i) != lk_envf.text[f + i]:
            return False
    for i in range(0, len(suffix)):
        if pending_char(size + i) != suffix[i]:
            return False
    return True


def chain():
    """The chain of the pending name: an index into HEADS."""
    return (pend_hash ^ (pend_hash >> 7)) & 0x1FF


def find():
    """The kept symbol with the pending name, and whether there is one."""
    e = lk_tab.work[HEADS + chain()]
    while e != 0:
        if name_is(e - 1):
            return get_b(e + 1) | (get_b(e + 2) << 8), True
        e = get_b(e - 1) | (get_b(e) << 8)
    return 0, False


def symbol(kind):
    """The symbol a SYM record of this kind with the pending name stands for, made if new."""
    global heap_top
    keep = kind == lk_sym.CLASS or get_bit(MARKS, pend_hash & 0x1FFF)
    if keep:
        s, found = find()
        if found:
            if lk_sym.kind_of(s) != kind:
                fail_pending(lk_err.E_KIND)
            return s
    flags = 0
    if kind == lk_sym.FUNCTION and is_init():
        flags = X_INIT
    if kind == lk_sym.FUNCTION and is_farcall(CALL_SUFFIX):
        flags = X_FCALL
    if kind == lk_sym.FUNCTION and is_farcall(START_SUFFIX):
        flags = X_FSTART
    if is_main():
        flags |= X_MAIN
    s = lk_sym.ref(kind, lk_sym.UNDEF | lk_sym.new_number())
    # The symbol's words come off the top of the heap, which must still hold the name.
    if heap_top + ENTRY + pending > heap_limit():
        lk_err.fail(lk_err.E_NAMES)
    lk_tab.work[ref_at(s)] = s
    lk_tab.work[ref_at(s) - 1] = flags
    if keep:
        pos = heap_top
        h = chain()
        put_b(pos, lk_tab.work[HEADS + h] & 0xFF)
        put_b(pos + 1, lk_tab.work[HEADS + h] >> 8)
        put_b(pos + 2, s & 0xFF)
        put_b(pos + 3, s >> 8)
        put_b(pos + 4, pending)
        lk_tab.work[HEADS + h] = pos + 1
        heap_top = pos + ENTRY + pending
    return s


# ---- the symbols while the files are read

def ref_at(s):
    """Where in the work area the first word of the symbol numbered in s is; its second word
    is just below."""
    return lk_tab.WORK_SIZE - 1 - 2 * lk_sym.row_of(s)


def now(s):
    """What symbol s stands for so far."""
    return lk_tab.work[ref_at(s)]


def bind(s, r):
    """Symbol s is defined: it stands for r."""
    global main_sym, fc_call, fc_start
    lk_tab.work[ref_at(s)] = r
    if (lk_tab.work[ref_at(s) - 1] & X_MAIN) != 0:
        main_sym = r
    if (lk_tab.work[ref_at(s) - 1] & X_FCALL) != 0:
        fc_call = r
    if (lk_tab.work[ref_at(s) - 1] & X_FSTART) != 0:
        fc_start = r


def more(s):
    """The weight given to variable s so far."""
    return lk_tab.work[ref_at(s) - 1] & X_LOW


def set_more(s, value):
    lk_tab.work[ref_at(s) - 1] = (lk_tab.work[ref_at(s) - 1] & (0xFFFF ^ X_LOW)) | value


def is_init_sym(s):
    return (lk_tab.work[ref_at(s) - 1] & X_INIT) != 0


def retarget(e):
    """Call e calls what the symbol it names stands for."""
    target = lk_sym.edge_bits(now(lk_tab.edge_sym(e)))
    lk_tab.edge_word[e] = (lk_tab.edge_word[e] & (0xFFFF ^ lk_tab.SYM_BITS)) | target


def resolve():
    """Once the files are read: every symbol number is replaced by what it stands for, in
    `local`, the calls and the members."""
    for i in range(0, local_count):
        local[i] = now(local[i])
    for e in range(0, lk_tab.edge_count):
        retarget(e)
    for i in range(0, lk_tab.waiting):
        e = lk_tab.MAX_EDGES - 1 - 2 * i
        lk_tab.edge_word[e] = now(lk_tab.edge_word[e])
        retarget(e - 1)
    for i in range(0, lk_tab.memb_count):
        lk_tab.memb_class[i] = now(lk_tab.memb_class[i])
        lk_tab.memb_func[i] = now(lk_tab.memb_func[i])


# ---- names read again from the files

found_obj = 0                       # find_local: the object file it found


def find_local(s):
    """The number of the first SYM record for symbol s in any object file, which is file
    found_obj."""
    global found_obj
    for obj in range(0, object_count):
        for i in range(obj_first[obj], obj_first[obj + 1]):
            if local[i] == s:
                found_obj = obj
                return i - obj_first[obj]
    found_obj = 0
    return 0


def to_name(obj, n):
    """Read object file obj up to its SYM record number n, and its name up to the characters.
    Returns the length of the name, which the stream reads next."""
    lk_rec.open_object(obj)
    seen = 0
    kind = lk_rec.advance()
    while kind != lk_rec.R_END:
        if kind == lk_rec.R_SYM:
            if seen == n:
                lk_rec.get_byte()
                return lk_rec.get_byte()
            seen += 1
        kind = lk_rec.advance()
    return 0


def error_name(s):
    """The name of symbol s, as part of an error message."""
    n = find_local(s)
    size = to_name(found_obj, n)
    for i in range(0, size):
        lk_err.put(lk_rec.get_byte())


def error_pending():
    """The pending name, as part of an error message."""
    for i in range(0, pending):
        lk_err.put(pending_char(i))


def error_node(n):
    """The name of a node, as the map shows it, as part of an error message."""
    error_name(lk_tab.node_sym(n))
    if lk_tab.is_extra_copy(n):
        lk_err.put(64)
        lk_err.put_number(lk_tab.ctx_of(n))


def fail(n, s):
    """Report error n about symbol s."""
    lk_err.begin(n)
    lk_err.colon()
    error_name(s)
    lk_err.finish()


def fail_in(n, s, where):
    """Report error n about symbol s, met in function `where`."""
    lk_err.begin(n)
    lk_err.colon()
    error_name(s)
    lk_err.comma()
    error_name(where)
    lk_err.finish()


def fail_pending(n):
    """Report error n about the symbol with the pending name."""
    lk_err.begin(n)
    lk_err.colon()
    error_pending()
    lk_err.finish()


# ---- names held while a file is read for the map

buf_top = 0                         # where the next name goes, in bytes of the work area
buf_end = 0


def buf_begin(start, limit):
    """Hold names from byte `start` of the work area, below byte `limit`."""
    global buf_top, buf_end
    buf_top = start
    buf_end = limit


def buf_keep():
    """Hold the string the record has next. Returns where it is held."""
    global buf_top
    size = lk_rec.get_byte()
    if buf_top + size + 1 > buf_end:
        lk_err.fail(lk_err.E_NAMES)
    pos = buf_top
    put_b(pos, size)
    for i in range(1, size + 1):
        put_b(pos + i, lk_rec.get_byte())
    buf_top = pos + size + 1
    return pos


def keep_at(pos):
    """Hold the string the record has next at byte `pos` of the work area, which has room for
    256 bytes."""
    size = lk_rec.get_byte()
    put_b(pos, size)
    for i in range(1, size + 1):
        put_b(pos + i, lk_rec.get_byte())


def write_held(handle, pos):
    """The name held at `pos`, to a file."""
    for i in range(1, get_b(pos) + 1):
        env.write(handle, get_b(pos + i))
