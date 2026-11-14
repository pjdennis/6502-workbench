"""Global symbols: every `module.name` the object files define or refer to, found by name.

A symbol is a row of the sym_ columns. Names live in `heap`, each as a length byte and its
characters, and are found through a hash table of chains. A name is first collected as the
pending name, just above the top of the heap, so that looking up a name already known costs no
heap space.

What the columns hold:

    kind          sym_a                 sym_b                       sym_f, sym_w
    function      row in lk_tab.fn_     first call (lk_tab.edge_)   -
    class         row in lk_tab.cls_    first call                  -
    variable      address               size                        V_ flags, weight
    constant data address               size                        -
"""
import env
import lk_err

HEAP_SIZE = 16384
MAX_SYMS = 2048
HASH_SIZE = 256                     # a power of two

FUNCTION = 1
VARIABLE = 2
CONSTANT = 3
CLASS = 4
KIND_MASK = 0x07                         # mask for the kind in sym_kind
DEFINED = 0x80                      # some object file defines the symbol

V_CLASS = 0x03                      # sym_f of a variable: its zero page class,
V_ZP = 0x80                         # and whether the linker put it in zero page

heap = bytearray(HEAP_SIZE)
heap_top = 0
pending = 0                         # length of the pending name at heap[heap_top + 1]

count = 0
sym_name = [0] * MAX_SYMS           # where in the heap
sym_next = [0] * MAX_SYMS           # next symbol with the same hash + 1, or 0
sym_kind = bytearray(MAX_SYMS)
sym_a = [0] * MAX_SYMS
sym_b = [0] * MAX_SYMS
sym_f = bytearray(MAX_SYMS)
sym_w = bytearray(MAX_SYMS)
hash_head = [0] * HASH_SIZE         # first symbol of the chain + 1, or 0


def name_begin():
    """Start collecting a name."""
    global pending
    pending = 0


def name_add(c):
    """Add one character to the pending name."""
    global pending
    if pending == 255 or heap_top + pending + 2 > HEAP_SIZE:
        lk_err.fail(lk_err.E_NAMES)
    heap[heap_top + 1 + pending] = c
    pending += 1


def name_keep():
    """Make the pending name permanent. Returns where it is in the heap."""
    global heap_top
    pos = heap_top
    heap[pos] = pending
    heap_top = pos + pending + 1
    return pos


def name_hash():
    """Hash of the pending name: an index into hash_head."""
    h = 0
    for i in range(0, pending):
        h = (h * 31 + heap[heap_top + 1 + i]) & 0xFFFF
    return (h ^ (h >> 8)) & (HASH_SIZE - 1)


def name_is(pos):
    """True if the pending name equals the name at `pos` in the heap."""
    if heap[pos] != pending:
        return False
    for i in range(1, pending + 1):
        if heap[pos + i] != heap[heap_top + i]:
            return False
    return True


def find():
    """The symbol with the pending name, and whether there is one."""
    s = hash_head[name_hash()]
    while s != 0:
        if name_is(sym_name[s - 1]):
            return s - 1, True
        s = sym_next[s - 1]
    return 0, False


def intern(kind):
    """The symbol with the pending name, made if new. Its kind must be `kind`."""
    global count
    s, found = find()
    if found:
        if (sym_kind[s] & KIND_MASK) != kind:
            fail(lk_err.E_KIND, s)
        return s
    if count == MAX_SYMS:
        lk_err.fail(lk_err.E_SYMBOLS)
    s = count
    count += 1
    h = name_hash()
    sym_name[s] = name_keep()
    sym_next[s] = hash_head[h]
    hash_head[h] = s + 1
    sym_kind[s] = kind
    return s


def kind_of(s):
    return sym_kind[s] & KIND_MASK


def is_defined(s):
    return (sym_kind[s] & DEFINED) != 0


def write_name(handle, s):
    """The name of symbol s, to a file."""
    write_text(handle, sym_name[s])


def write_text(handle, pos):
    """The name kept at `pos` in the heap, to a file."""
    for i in range(1, heap[pos] + 1):
        env.write(handle, heap[pos + i])


def write_pending(handle):
    """The pending name, to a file."""
    for i in range(1, pending + 1):
        env.write(handle, heap[heap_top + i])


def error_name(s):
    """The name of symbol s, as part of an error message."""
    pos = sym_name[s]
    for i in range(1, heap[pos] + 1):
        lk_err.put(heap[pos + i])


def error_pending():
    """The pending name, as part of an error message."""
    for i in range(1, pending + 1):
        lk_err.put(heap[heap_top + i])


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
