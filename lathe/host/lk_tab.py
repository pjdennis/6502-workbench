"""The program being linked, as tables: functions, slots, pointer classes, calls, and the copies
of functions the linker places.

    fn_     one row per function an object file defines, in object order then record order,
            which is also the order functions are placed in.
    slot_   the slots of all functions; a function's slots are a run of rows.
    cls_    one row per pointer class symbol. Classes that share a member are merged: cls_rep
            leads to the class that stands for the set, and only that row is used afterwards.
    cp_     the parameters of the classes: the slots of a class's shared block.
    memb_   which functions have their address taken as which class.
    edge_   calls. The calls of a function or class are a run of rows, from its fn_edge or
            cls_edge to the next function's or class's: the functions' runs in order, then the
            classes'. A walk (first_call, next_call) meets them in the order they are stored,
            which is the newest first (build_chains). While the files are read a function's own
            calls are a run in the order they are read, and a call made while another's
            arguments wait takes two rows at the top until the files are read.
    node_   what gets storage: a copy of a kept function for each context that reaches it,
            and a block for each live class. Node f is the first copy of function f (a function
            that is not kept leaves a hole: is_node); the further copies follow the functions,
            in function then context order, and the blocks follow them. The order the copies
            are placed in, first copies and further copies of each function together, is that
            of first_in_order and next_in_order.
    ctx_    contexts: 0 is the main program, the others one interrupt function each.
    def_    variables and constant data in the order they are defined.

A symbol is a reference (lk_sym): the kind and the row of one of these tables.

A call is kept as an edge between symbols, not between copies: the copies an edge joins are
worked out when the edge is followed (lk_graph.edge_node), because every copy of a function
makes the same calls.
"""
import lk_err
import lk_sym

# Capacities: sized for linking the compiler itself (architecture.md, "Memory in the linker").
MAX_FUNCS = 800
MAX_SLOTS = 4000
MAX_BIG_SLOTS = 64                  # slots of 15 bytes or more
MAX_CLASSES = 32
MAX_CPARAMS = 128
MAX_MEMBERS = 128
MAX_EDGES = 3600
MAX_NODES = 900
MAX_CONTEXTS = 8                    # a context is a bit in a byte
MAX_DEFS = 800
NONE = 0xFFFF

# FUNC record flags, and the linker's own.
F_RECURSIVE = 1
F_INTERRUPT = 2
F_HELD = 0x40                       # lk_map: a line of the file being read needs its name
F_INIT = 0x80                       # the function is some module's `$init` (lk_boot)

# Edge flags: the top three bits of edge_word, above the function or class called
# (lk_sym.edge_bits) in the 13 below them.
SYM_BITS = 0x1FFF
FLAG_SHIFT = 13
E_NOSAVE = 1                        # some call on this edge does not save the caller's frame
E_PENDING = 2                       # not a call: the target ran while the source's arguments waited
E_VIA = 4                           # to a class block, for a direct call of one of its members

# cp_info.
S_CLASS = 0x03                      # zero page class: 0 must, 1 either, 2 never
S_ZP = 0x80                         # the linker put it in zero page

# slot_sz: a slot in a byte. The size of a slot of 15 bytes or more is in big_size.
SL_SIZE = 0x0F
SL_BIG = 15
SL_CLASS = 0x30                     # zero page class, as S_CLASS
SL_CLASS_SHIFT = 4
SL_PARAM = 0x40                     # a parameter, not a local or temporary
SL_ZP = 0x80                        # the linker put it in zero page

fn_count = 0
fn_flags = bytearray(MAX_FUNCS)
fn_ctx = bytearray(MAX_FUNCS)       # one bit per context that reaches the function; 0 = dropped
fn_slot = [0] * MAX_FUNCS           # first row in slot_
fn_class = bytearray(MAX_FUNCS)     # a class the function is a member of + 1, or 0
fn_edge = [0] * MAX_FUNCS           # where its calls start

slot_count = 0
slot_sz = bytearray(MAX_SLOTS)      # SL_ bits: size, class, parameter, in zero page
big_count = 0
big_slot = [0] * MAX_BIG_SLOTS      # slots of 15 bytes or more, in slot order
big_size = [0] * MAX_BIG_SLOTS
slot_weight = bytearray(MAX_SLOTS)

cls_count = 0
cls_rep = bytearray(MAX_CLASSES)
cls_reach = bytearray(MAX_CLASSES)  # one bit per context that calls through the class
cls_ctx = bytearray(MAX_CLASSES)    # the one context that does, when cls_reach is not 0
cls_np = bytearray(MAX_CLASSES)     # number of parameters
cls_par = [0] * MAX_CLASSES         # first row in cp_
cls_node = [0] * MAX_CLASSES
cls_namer = [0] * MAX_CLASSES       # the member whose parameter names the map shows + 1, or 0
cls_edge = [0] * MAX_CLASSES        # where its calls start (the calls of its block)

cp_count = 0
cp_size = [0] * MAX_CPARAMS
cp_info = bytearray(MAX_CPARAMS)
cp_weight = bytearray(MAX_CPARAMS)
cp_addr = [0] * MAX_CPARAMS

memb_count = 0
memb_class = [0] * MAX_MEMBERS      # references (lk_sym)
memb_func = [0] * MAX_MEMBERS

edge_count = 0
edge_word = [0] * MAX_EDGES         # function or class called, and the flags above it
waiting = 0                         # while the files are read: calls at the top, two rows each
                                    # (the caller, then the call)

node_count = 0                      # the node columns are in the work area (W_OWN...)
extra_end = 0                       # the further copies are the nodes from fn_count to here
CLASS_NODE = 0x8000

ctx_count = 0

def_count = 0
def_a = [0] * MAX_DEFS              # its address; until a variable is given one, its weight
                                    # (def_w); until constant data is placed, its file
def_b = [0] * MAX_DEFS              # its size
def_f = bytearray(MAX_DEFS)         # D_ flags
D_CLASS = 0x03                      # a variable's zero page class
D_CONST = 0x04                      # constant data, not a variable
D_HELD = 0x10                       # lk_map: a line of the file being read needs its name
D_PASSED = 0x20                     # lk_graph: the reading passed its DATA record
D_KEPT = 0x40                       # something kept uses it (lk_graph)
D_ZP = 0x80                         # the linker put the variable in zero page

# The work area: storage that one phase uses and the next reuses. lk_name's names and lk_scan's
# waiting weights use all of it while the files are read, lk_graph's searches the first 8
# columns of MAX_NODES words while the graph is built, lk_alloc's layouts the same columns while
# storage is allocated, and lk_fix's held fix-ups and the map's names them while the image is
# written; each module names where its columns start. Node columns that only the graph and
# storage need live in those 8 columns too; the node columns of placement replace them, above the
# fix-ups held. The columns every phase from lk_graph.make_nodes on needs come last (W_OWN...).
MAX_FIXES = 512                     # fix-ups of one function or one piece of constant data
# The map, before the image is written: the names of one object file in the first W_ADDR words
# (lk_map). While the image is written: the name of a slot, in the words from W_SNAME.
W_SCC = 5 * MAX_NODES               # graph, storage: nodes on one cycle of calls have one number
W_ORDER = 6 * MAX_NODES             # graph, storage: lk_graph's order of the nodes
W_ZSIZE = 4 * MAX_NODES             # storage: bytes of zero page a node's frame or block needs
W_ADDR = 6 * MAX_FIXES              # placement, image: where a function copy's code is placed
W_SNAME = W_ADDR + MAX_NODES        # image: 128 words
W_OWN = 7 * MAX_NODES               # a node's function, or CLASS_NODE + its class
W_CTXZ = W_OWN + MAX_NODES          # its context in the high byte; in the low byte where its zero
                                    # page bytes start (one past $FF is only that of a node with none)
W_MBASE = W_CTXZ + MAX_NODES        # where its main memory bytes start
WORK_SIZE = W_MBASE + MAX_NODES
work = [0] * WORK_SIZE

overflow = False                    # set when add16 could not hold its result


def add16(a, b):
    """a + b, or $FFFF with `overflow` set if that does not fit in 16 bits."""
    global overflow
    if b > 0xFFFF - a:
        overflow = True
        return 0xFFFF
    return a + b


def new_func(flags):
    global fn_count
    if fn_count == MAX_FUNCS:
        lk_err.fail(lk_err.E_FUNCTIONS)
    f = fn_count
    fn_count += 1
    fn_flags[f] = flags
    fn_edge[f] = edge_count
    fn_slot[f] = slot_count
    return f


def new_slot(f, size, zp_class, param, weight):
    """Add the next slot of function f, the function defined last."""
    global slot_count
    if slot_count == MAX_SLOTS:
        lk_err.fail(lk_err.E_SLOTS)
    global big_count
    if size >= SL_BIG:
        if big_count == MAX_BIG_SLOTS:
            lk_err.fail(lk_err.E_SLOTS)
        big_slot[big_count] = slot_count
        big_size[big_count] = size
        big_count += 1
        size = SL_BIG
    bits = size | (zp_class << SL_CLASS_SHIFT)
    if param:
        bits |= SL_PARAM
    slot_sz[slot_count] = bits
    slot_weight[slot_count] = weight
    slot_count += 1


def new_class(np):
    """Add a class with np parameters whose rows in cp_ follow."""
    global cls_count
    if cls_count == MAX_CLASSES or cp_count + np > MAX_CPARAMS:
        lk_err.fail(lk_err.E_CLASSES)
    k = cls_count
    cls_count += 1
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


def new_def(flags):
    """A new variable or piece of constant data. Returns its row."""
    global def_count
    if def_count == MAX_DEFS:
        lk_err.fail(lk_err.E_DEFS)
    def_f[def_count] = flags
    def_count += 1
    return def_count - 1


def def_ref(d):
    """The reference of definition d."""
    if (def_f[d] & D_CONST) != 0:
        return lk_sym.ref(lk_sym.CONSTANT, d)
    return lk_sym.ref(lk_sym.VARIABLE, d)


def fn_ref(f):
    return lk_sym.ref(lk_sym.FUNCTION, f)


def cls_ref(k):
    return lk_sym.ref(lk_sym.CLASS, k)


def is_kept_def(d):
    return (def_f[d] & D_KEPT) != 0


def is_kept_var(d):
    return (def_f[d] & (D_CONST | D_KEPT)) == D_KEPT


def fn_nslots(f):
    """The number of slots of function f: up to the next function's first."""
    if f + 1 < fn_count:
        return fn_slot[f + 1] - fn_slot[f]
    return slot_count - fn_slot[f]


def def_w(d):
    """The weight of variable d, until it is given an address."""
    return def_a[d]


def class_of(k):
    """The class that stands for class k after merging."""
    while cls_rep[k] != k:
        k = cls_rep[k]
    return k


def first_call(r):
    """The first call of function or class r + 1, or 0: the start of a walk with next_call."""
    if run_start(r) < run_end(r):
        return run_start(r) + 1
    return 0


def next_call(r, e):
    """The call after call e + 1 of function or class r + 1, or 0."""
    if e < run_end(r):
        return e + 1
    return 0


def run_start(r):
    if lk_sym.kind_of(r) == lk_sym.CLASS:
        return cls_edge[lk_sym.row_of(r)]
    return fn_edge[lk_sym.row_of(r)]


def run_end(r):
    """Where the calls of function or class r end: where the next one's start."""
    i = lk_sym.row_of(r) + 1
    if lk_sym.kind_of(r) == lk_sym.FUNCTION:
        if i < fn_count:
            return fn_edge[i]
        i = 0
    if i < cls_count:
        return cls_edge[i]
    return edge_count


def room_for(needed):
    if edge_count + 2 * waiting + needed > MAX_EDGES:
        lk_err.fail(lk_err.E_CALLS)


def same_call(call, target, flags):
    """True if the call `call` is of `target` and of the same kind as a call with these flags."""
    kind = flags & (E_PENDING | E_VIA)
    return (call & SYM_BITS) == target and ((call >> FLAG_SHIFT) & (E_PENDING | E_VIA)) == kind


def add_own(f, target, flags):
    """While the files are read: function f, the function defined last, calls `target`, a
    function or class as lk_sym.edge_bits gives it.

    Calls of the same kind between the same two symbols are one edge, which does not save the
    caller's frame if any of them does not."""
    global edge_count
    for e in range(fn_edge[f], edge_count):
        if same_call(edge_word[e], target, flags):
            edge_word[e] |= flags << FLAG_SHIFT
            return
    room_for(1)
    edge_word[edge_count] = target | (flags << FLAG_SHIFT)
    edge_count += 1


def add_waiting(caller, target, flags):
    """While the files are read: `caller`, a symbol (lk_name), calls `target` while another
    function's arguments wait. Flags E_VIA marks one whose caller's own calls were read before."""
    global waiting
    for i in range(0, waiting):
        if edge_word[MAX_EDGES - 1 - 2 * i] == caller and (edge_word[MAX_EDGES - 2 - 2 * i] & SYM_BITS) == target:
            return
    room_for(2)
    edge_word[MAX_EDGES - 1 - 2 * waiting] = caller
    edge_word[MAX_EDGES - 2 - 2 * waiting] = target | (flags << FLAG_SHIFT)
    waiting += 1


# ---- chains, while the calls of classes are added (lk_scan.finish): in the work area, above
# lk_scan's waiting weights. A function's or class's fn_edge or cls_edge is its newest call + 1.
W_WCALLER = 256                     # build_chains: the waiting calls, oldest first
W_WCALL = W_WCALLER + MAX_EDGES // 2
W_START = W_WCALL + MAX_EDGES // 2  # where each function's run started
W_NEXT = W_START + MAX_FUNCS        # the next call of the same caller + 1, or 0
W_RUNS = 256                        # chains_to_runs: the calls in their new places


def chain_next(e):
    return work[W_NEXT + e - 1]


def head_of(r):
    if lk_sym.kind_of(r) == lk_sym.CLASS:
        return cls_edge[lk_sym.row_of(r)]
    return fn_edge[lk_sym.row_of(r)]


def set_head(r, e):
    if lk_sym.kind_of(r) == lk_sym.CLASS:
        cls_edge[lk_sym.row_of(r)] = e
    else:
        fn_edge[lk_sym.row_of(r)] = e


def prepend(r, e):
    """Call e becomes the newest of r's chain."""
    work[W_NEXT + e] = head_of(r)
    set_head(r, e + 1)


def build_chains():
    """Once the files are read and the symbols resolved: every function's and class's calls as
    a chain, newest first, as if each had been added to the front of its caller's chain when
    it was read. A waiting call whose caller nothing defines goes in no chain."""
    global edge_count, waiting
    own_end = edge_count
    for i in range(0, waiting):
        work[W_WCALLER + i] = edge_word[MAX_EDGES - 1 - 2 * i]
        work[W_WCALL + i] = edge_word[MAX_EDGES - 2 - 2 * i]
    for f in range(0, fn_count):
        work[W_START + f] = fn_edge[f]
        fn_edge[f] = 0
    for k in range(0, cls_count):
        cls_edge[k] = 0
    for i in range(0, waiting):
        edge_word[own_end + i] = work[W_WCALL + i] & (0xFFFF ^ (E_VIA << FLAG_SHIFT))
    edge_count = own_end + waiting
    # Waiting calls read before their caller's own calls, then the own calls, then the rest.
    for i in range(0, waiting):
        if (work[W_WCALL + i] & (E_VIA << FLAG_SHIFT)) == 0 and lk_sym.is_defined(work[W_WCALLER + i]):
            prepend(work[W_WCALLER + i], own_end + i)
    for f in range(0, fn_count):
        limit = own_end
        if f + 1 < fn_count:
            limit = work[W_START + f + 1]
        for e in range(work[W_START + f], limit):
            prepend(fn_ref(f), e)
    for i in range(0, waiting):
        if (work[W_WCALL + i] & (E_VIA << FLAG_SHIFT)) != 0 and lk_sym.is_defined(work[W_WCALLER + i]):
            prepend(work[W_WCALLER + i], own_end + i)
    waiting = 0


def add_edge(r, target, flags):
    """Record that function or class r, which is defined, calls function or class `target`,
    while the calls are chains.

    Calls of the same kind between the same two symbols are one edge, which does not save the
    caller's frame if any of them does not."""
    global edge_count
    bits = lk_sym.edge_bits(target)
    e = head_of(r)
    while e != 0:
        if same_call(edge_word[e - 1], bits, flags):
            edge_word[e - 1] |= flags << FLAG_SHIFT
            return
        e = chain_next(e)
    room_for(1)
    edge_word[edge_count] = bits | (flags << FLAG_SHIFT)
    edge_count += 1
    prepend(r, edge_count - 1)


def chains_to_runs():
    """Each chain becomes a run, in the order of the chain: the functions' in order, then the
    classes'. A call in no chain is dropped."""
    global edge_count
    pos = 0
    for f in range(0, fn_count):
        e = fn_edge[f]
        fn_edge[f] = pos
        while e != 0:
            work[W_RUNS + pos] = edge_word[e - 1]
            pos += 1
            e = chain_next(e)
    for k in range(0, cls_count):
        e = cls_edge[k]
        cls_edge[k] = pos
        while e != 0:
            work[W_RUNS + pos] = edge_word[e - 1]
            pos += 1
            e = chain_next(e)
    for i in range(0, pos):
        edge_word[i] = work[W_RUNS + i]
    edge_count = pos


def edge_sym(e):
    """The function or class edge e calls."""
    return lk_sym.edge_ref(edge_word[e] & SYM_BITS)


def edge_flag(e):
    """The E_ flags of edge e."""
    return edge_word[e] >> FLAG_SHIFT


def slot_bytes(s):
    """The size of slot s."""
    if (slot_sz[s] & SL_SIZE) != SL_BIG:
        return slot_sz[s] & SL_SIZE
    # big_slot is in slot order.
    low = 0
    high = big_count - 1
    while big_slot[low] != s:
        mid = (low + high + 1) >> 1
        if big_slot[mid] > s:
            high = mid - 1
        else:
            low = mid
    return big_size[low]


def slot_class(s):
    """The zero page class of slot s: 0 must, 1 either, 2 never."""
    return (slot_sz[s] & SL_CLASS) >> SL_CLASS_SHIFT


def slot_in_zp(s):
    return (slot_sz[s] & SL_ZP) != 0


def new_node(own, ctx):
    global node_count
    if node_count == MAX_NODES:
        lk_err.fail(lk_err.E_COPIES)
    work[W_OWN + node_count] = own
    work[W_CTXZ + node_count] = ctx << 8
    node_count += 1


def own_of(n):
    """The function, or CLASS_NODE + the class, that node n is a copy or block of."""
    if n < fn_count:
        return n
    return work[W_OWN + n]


def is_node(n):
    """False for the node of a function that is not kept."""
    return n >= fn_count or fn_ctx[n] != 0


def ctx_of(n):
    return work[W_CTXZ + n] >> 8


def zbase_of(n):
    """Where node n's zero page bytes start: the low byte of the address."""
    return work[W_CTXZ + n] & 0xFF


def set_zbase(n, value8):
    work[W_CTXZ + n] = (work[W_CTXZ + n] & 0xFF00) | value8


def mbase_of(n):
    """Where node n's main memory bytes start."""
    return work[W_MBASE + n]


def first_node(f):
    """The node of function f's first copy."""
    return f


def first_extra(f):
    """The first further copy of function f, or NONE."""
    low = fn_count
    high = extra_end
    while low < high:
        mid = (low + high) >> 1
        if work[W_OWN + mid] < f:
            low = mid + 1
        else:
            high = mid
    if low < extra_end and work[W_OWN + low] == f:
        return low
    return NONE


def next_kept(f):
    """The first node in placement order from function f on, or NONE."""
    while f < fn_count and fn_ctx[f] == 0:
        f += 1
    if f < fn_count:
        return f
    if extra_end < node_count:
        return extra_end
    return NONE


def first_in_order():
    """The first node in placement order, or NONE: a walk with next_in_order."""
    return next_kept(0)


def next_in_order(n):
    """The node after node n in placement order, or NONE."""
    if n < fn_count:
        x = first_extra(n)
        if x != NONE:
            return x
        return next_kept(n + 1)
    if n < extra_end:
        if n + 1 < extra_end and work[W_OWN + n + 1] == work[W_OWN + n]:
            return n + 1
        return next_kept(work[W_OWN + n] + 1)
    if n + 1 < node_count:
        return n + 1
    return NONE


def has_copy(f, ctx):
    """True if function f is linked for context ctx."""
    return (fn_ctx[f] & (1 << ctx)) != 0


def copy_node(f, ctx):
    """The node of function f's copy for context ctx, which it must have."""
    if (fn_ctx[f] & ((1 << ctx) - 1)) == 0:
        return f
    n = first_extra(f) - 1
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
    return own_of(n) >= CLASS_NODE


def node_class(n):
    return own_of(n) - CLASS_NODE


def node_sym(n):
    """The function or class a node belongs to."""
    if node_is_class(n):
        return cls_ref(node_class(n))
    return fn_ref(own_of(n))


def slot_is_param(s):
    return (slot_sz[s] & SL_PARAM) != 0


def in_frame(f, i, blocked):
    """True if slot i of f is in the frame of a copy; `blocked` says the copy's parameters
    are in a class block."""
    return not (blocked and slot_is_param(fn_slot[f] + i))


def is_extra_copy(n):
    """True if node n is a copy of a function that a lower context has too. Such a copy is
    named `function@context`; a function's first copy has the function's own name."""
    return n >= fn_count and n < extra_end

