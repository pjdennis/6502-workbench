"""The program being linked, as tables: functions, slots, pointer classes, calls, and the copies
of functions the linker places.

    fn_     one row per function an object file defines, in object order then record order,
            which is also the order functions are placed in.
    slot_   the slots of all functions; a function's slots are a run of rows.
    cls_    one row per pointer class symbol. Classes that share a member are merged: cls_rep
            leads to the class that stands for the set, and only that row is used afterwards.
    cp_     the parameters of the classes: the slots of a class's shared block.
    memb_   which functions have their address taken as which class.
    edge_   calls. The calls of a function or class are a chain starting at its symbol's sym_b.
    node_   what gets storage: one row per copy of a kept function (a function has one copy
            for each context that reaches it, in a run of rows in context order) and one row
            per live class, for its block.
    ctx_    contexts: 0 is the main program, the others one interrupt function each.
    def_    variables and constant data in the order they are defined.

A call is kept as an edge between symbols, not between copies: the copies an edge joins are
worked out when the edge is followed (lk_graph.edge_node), because every copy of a function
makes the same calls.
"""
import lk_err
import lk_sym

MAX_FUNCS = 1024
MAX_SLOTS = 8192
MAX_CLASSES = 64
MAX_CPARAMS = 256
MAX_MEMBERS = 256
MAX_EDGES = 8192
MAX_NODES = 1280
MAX_CONTEXTS = 8                    # a context is a bit in a byte
MAX_DEFS = 1024
NONE = 0xFFFF

# FUNC record flags.
F_RECURSIVE = 1
F_INTERRUPT = 2

# edge_flags.
E_NOSAVE = 1                        # some call on this edge does not save the caller's frame
E_PENDING = 2                       # not a call: the target ran while the source's arguments waited
E_VIA = 4                           # to a class block, for a direct call of one of its members

# slot_info and cp_info.
S_CLASS = 0x03                      # zero page class: 0 must, 1 either, 2 never
S_KIND = 0x0C                       # slot kind, shifted: 0 parameter, 1 local, 2 temporary
S_KIND_SHIFT = 2
S_ZP = 0x80                         # the linker put it in zero page

fn_count = 0
fn_sym = [0] * MAX_FUNCS
fn_flags = bytearray(MAX_FUNCS)
fn_ctx = bytearray(MAX_FUNCS)       # one bit per context that reaches the function; 0 = dropped
fn_slot = [0] * MAX_FUNCS           # first row in slot_
fn_nslots = bytearray(MAX_FUNCS)
fn_class = bytearray(MAX_FUNCS)     # a class the function is a member of + 1, or 0
fn_node = [0] * MAX_FUNCS           # the first of its copies

slot_count = 0
slot_size = [0] * MAX_SLOTS
slot_info = bytearray(MAX_SLOTS)
slot_weight = bytearray(MAX_SLOTS)

cls_count = 0
cls_sym = [0] * MAX_CLASSES
cls_rep = bytearray(MAX_CLASSES)
cls_reach = bytearray(MAX_CLASSES)  # one bit per context that calls through the class
cls_ctx = bytearray(MAX_CLASSES)    # the one context that does, when cls_reach is not 0
cls_np = bytearray(MAX_CLASSES)     # number of parameters
cls_par = [0] * MAX_CLASSES         # first row in cp_
cls_node = [0] * MAX_CLASSES
cls_namer = [0] * MAX_CLASSES       # the member whose parameter names the map shows + 1, or 0

cp_count = 0
cp_size = [0] * MAX_CPARAMS
cp_info = bytearray(MAX_CPARAMS)
cp_weight = bytearray(MAX_CPARAMS)
cp_addr = [0] * MAX_CPARAMS
cp_name = [0] * MAX_CPARAMS         # where in the name heap + 1, or 0

memb_count = 0
memb_class = [0] * MAX_MEMBERS      # symbols
memb_func = [0] * MAX_MEMBERS

edge_count = 0
edge_to = [0] * MAX_EDGES           # symbol called
edge_next = [0] * MAX_EDGES         # next edge of the same caller + 1, or 0
edge_flags = bytearray(MAX_EDGES)

node_count = 0
node_own = [0] * MAX_NODES          # a row in fn_, or NODE_CLASS + a row in cls_
node_ctx = bytearray(MAX_NODES)
node_scc = [0] * MAX_NODES          # nodes on one cycle of calls have the same number
node_zsize = [0] * MAX_NODES        # bytes of zero page its frame or block needs
node_zbase = [0] * MAX_NODES        # where its zero page bytes start
node_mbase = [0] * MAX_NODES        # where its main memory bytes start
node_addr = [0] * MAX_NODES         # where a function copy's code is placed
node_len = [0] * MAX_NODES          # the size of that code after shrinking
CLASS_NODE = 0x8000

ctx_count = 0

def_count = 0
def_sym = [0] * MAX_DEFS

overflow = False                    # set when add16 could not hold its result


def add16(a, b):
    """a + b, or $FFFF with `overflow` set if that does not fit in 16 bits."""
    global overflow
    if b > 0xFFFF - a:
        overflow = True
        return 0xFFFF
    return a + b


def new_func(sym, flags):
    global fn_count
    if fn_count == MAX_FUNCS:
        lk_err.fail(lk_err.E_FUNCTIONS)
    f = fn_count
    fn_count += 1
    fn_sym[f] = sym
    fn_flags[f] = flags
    fn_slot[f] = slot_count
    return f


def new_slot(f, size, info, weight):
    """Add the next slot of function f, the function defined last."""
    global slot_count
    if slot_count == MAX_SLOTS:
        lk_err.fail(lk_err.E_SLOTS)
    slot_size[slot_count] = size
    slot_info[slot_count] = info
    slot_weight[slot_count] = weight
    slot_count += 1
    fn_nslots[f] += 1


def new_class(sym, np):
    """Add a class with np parameters whose rows in cp_ follow."""
    global cls_count
    if cls_count == MAX_CLASSES or cp_count + np > MAX_CPARAMS:
        lk_err.fail(lk_err.E_CLASSES)
    k = cls_count
    cls_count += 1
    cls_sym[k] = sym
    cls_rep[k] = k
    cls_np[k] = np
    cls_par[k] = cp_count
    return k


def new_cparam(size):
    global cp_count
    cp_size[cp_count] = size
    cp_info[cp_count] = 1           # "either", until the members say otherwise
    cp_count += 1


def new_member(class_sym, func_sym):
    global memb_count
    if memb_count == MAX_MEMBERS:
        lk_err.fail(lk_err.E_MEMBERS)
    memb_class[memb_count] = class_sym
    memb_func[memb_count] = func_sym
    memb_count += 1


def new_def(sym):
    global def_count
    if def_count == MAX_DEFS:
        lk_err.fail(lk_err.E_DEFS)
    def_sym[def_count] = sym
    def_count += 1


def class_of(k):
    """The class that stands for class k after merging."""
    while cls_rep[k] != k:
        k = cls_rep[k]
    return k


def add_edge(source, target, flags):
    """Record that symbol `source` calls symbol `target`.

    Calls of the same kind between the same two symbols are one edge, which does not save the
    caller's frame if any of them does not."""
    global edge_count
    kind = flags & (E_PENDING | E_VIA)
    e = lk_sym.sym_b[source]
    while e != 0:
        if edge_to[e - 1] == target and (edge_flags[e - 1] & (E_PENDING | E_VIA)) == kind:
            edge_flags[e - 1] |= flags
            return
        e = edge_next[e - 1]
    if edge_count == MAX_EDGES:
        lk_err.fail(lk_err.E_CALLS)
    edge_to[edge_count] = target
    edge_flags[edge_count] = flags
    edge_next[edge_count] = lk_sym.sym_b[source]
    edge_count += 1
    lk_sym.sym_b[source] = edge_count


def new_node(own, ctx):
    global node_count
    if node_count == MAX_NODES:
        lk_err.fail(lk_err.E_COPIES)
    node_own[node_count] = own
    node_ctx[node_count] = ctx
    node_count += 1


def has_copy(f, ctx):
    """True if function f is linked for context ctx."""
    return (fn_ctx[f] & (1 << ctx)) != 0


def copy_node(f, ctx):
    """The node of function f's copy for context ctx, which it must have."""
    n = fn_node[f]
    for c in range(0, ctx):
        if (fn_ctx[f] & (1 << c)) != 0:
            n += 1
    return n


def member_class(f):
    """The live class function f is a member of, and whether it is in one."""
    if fn_class[f] == 0:
        return 0, False
    k = class_of(fn_class[f] - 1)
    return k, cls_reach[k] != 0


def in_block(f, ctx):
    """True if the copy of f for ctx has its parameters in a class block, not in its frame."""
    k, live = member_class(f)
    return live and cls_ctx[k] == ctx


def node_is_class(n):
    return node_own[n] >= CLASS_NODE


def node_class(n):
    return node_own[n] - CLASS_NODE


def node_sym(n):
    """The function or class symbol a node belongs to."""
    if node_is_class(n):
        return cls_sym[node_class(n)]
    return fn_sym[node_own[n]]


def slot_kind(s):
    return (slot_info[s] & S_KIND) >> S_KIND_SHIFT


def in_frame(f, i, blocked):
    """True if slot i of f is in the frame of a copy; `blocked` says the copy's parameters
    are in a class block."""
    return not (blocked and slot_kind(fn_slot[f] + i) == 0)


def is_extra_copy(n):
    """True if node n is a copy of a function that a lower context has too. Such a copy is
    named `function@context`; a function's first copy has the function's own name."""
    return not node_is_class(n) and n != fn_node[node_own[n]]


def error_node(n):
    """The name of a node, as the map shows it, as part of an error message."""
    lk_sym.error_name(node_sym(n))
    if is_extra_copy(n):
        lk_err.put(64)
        lk_err.put_number(node_ctx[n])
