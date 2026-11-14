"""The call graph: what is reachable, in which contexts, and where recursion is.

build() does the linker's steps between reading and allocating:

1. Contexts. Context 0 is the main program, rooted at main and at every module's `$init`
   (lk_boot); every interrupt function is the root of a context of its own. A function gets one
   bit in fn_ctx per context that reaches it; a function with no bit is dropped. A function
   whose address is taken by constant data or by a kept function is kept too: if nothing else
   reaches it, it is a further root of context 0. So no address in the image is that of a
   function the linker dropped. In the same way a variable or constant data is kept only if
   kept code or kept constant data refers to it; the rest get no address.
2. Pointer classes. A class is live if some kept function calls through it, and all those
   calls must be in one context. Its block's parameters take the strictest zero page class and
   the summed weight of its members' parameters.
3. Nodes: a copy of each function per context that reaches it, and a node per live class.
4. Cycles. The nodes are grouped into sets that can reach each other (lk_tab.W_SCC), by Tarjan's
   algorithm with its own stack in place of recursion. A call inside such a set is recursion:
   it must save the caller's frame, and both ends must be `recursive`.

`order` lists the nodes callees first, with the nodes of a set next to each other: the order in
which lk_alloc lays out storage, read backwards.

Calls that only place storage (E_PENDING, E_VIA) do not make anything reachable.
"""
import lk_boot
import lk_err
import lk_rec
import lk_scan
import lk_sym
import lk_tab

# lk_tab.work[lk_tab.W_ORDER...]: the nodes, callees before their callers
order_count = 0
scc_count = 0

# Work columns for the searches, one row per node (or per symbol while there are no nodes), in
# lk_tab.work: where each starts.
STACK = 0                           # nodes or symbols still to finish
STACK_EDGE = lk_tab.MAX_NODES       # for each, the next edge to follow + 1
FOUND = 2 * lk_tab.MAX_NODES        # Tarjan: nodes found and not yet given a set
SEEN = 3 * lk_tab.MAX_NODES         # Tarjan: order of discovery + 1; path search: came from + 1
LOW = 4 * lk_tab.MAX_NODES          # Tarjan: earliest node reachable
NAMED = lk_tab.MAX_NODES          # keep_in_object: what a DFIX record names, until its DATA
ON_STACK = 0xFFFF                   # the set number of a node in `found`
IN_CLASS = b", both in the pointer class "
OWN_CLASS = b", its own pointer class"
stack_top = 0
e_kind = 0                          # the fix-up entry read last (read_entry)
e_sym = 0
e_slot = 0
found_top = 0
discovered = 0                      # Tarjan: nodes discovered so far


def edge_target(e):
    """The symbol edge e calls: a function, or the class standing for the class named."""
    target = lk_tab.edge_sym(e)
    if lk_sym.kind_of(target) == lk_sym.CLASS:
        return lk_tab.cls_sym[lk_tab.class_of(lk_sym.sym_a[target])]
    return target


# ---- contexts and reachability

def mark(target, ctx):
    """Note that context ctx reaches a symbol. True if that is news."""
    bit = 1 << ctx
    if lk_sym.kind_of(target) == lk_sym.CLASS:
        k = lk_sym.sym_a[target]
        if (lk_tab.cls_reach[k] & bit) != 0:
            return False
        lk_tab.cls_reach[k] |= bit
        return True
    f = lk_sym.sym_a[target]
    if (lk_tab.fn_ctx[f] & bit) != 0:
        return False
    lk_tab.fn_ctx[f] |= bit
    return True


def reach(root, ctx):
    """Mark everything function symbol `root` can call as reached by context ctx."""
    if not mark(root, ctx):
        return
    top = 1
    lk_tab.work[STACK + 0] = root
    while top > 0:
        top -= 1
        e = lk_sym.sym_b[lk_tab.work[STACK + top]]
        while e != 0:
            if (lk_tab.edge_flag(e - 1) & (lk_tab.E_PENDING | lk_tab.E_VIA)) == 0:
                # Kept code calls it, so it must be defined.
                if not lk_sym.is_defined(lk_tab.edge_sym(e - 1)):
                    lk_sym.fail(lk_err.E_UNDEFINED, lk_tab.edge_sym(e - 1))
                target = edge_target(e - 1)
                if mark(target, ctx):
                    if top == lk_tab.MAX_NODES:
                        lk_err.fail(lk_err.E_COPIES)
                    lk_tab.work[STACK + top] = target
                    top += 1
            e = lk_tab.edge_next[e - 1]


def is_kept(s):
    """True if the function, variable or constant data that is symbol s is kept so far."""
    if lk_sym.kind_of(s) == lk_sym.FUNCTION:
        return lk_tab.fn_ctx[lk_sym.sym_a[s]] != 0
    return (lk_sym.sym_f[s] & lk_sym.KEPT) != 0


def keep_target(source, target):
    """Kept `source` refers to `target`. True if that keeps something new."""
    if not lk_sym.is_defined(target):
        lk_sym.fail(lk_err.E_UNDEFINED, target)
    if is_kept(target):
        return False
    if lk_sym.kind_of(target) == lk_sym.FUNCTION:
        reach(target, 0)
    else:
        lk_sym.sym_f[target] |= lk_sym.KEPT
    return True


def keeps(obj, source, kind, s, slot):
    """True if a fix-up entry of `source` keeps what it names, symbol s, if `source` is kept.

    That is every variable and piece of constant data it names, and every function whose
    address it takes. In code an address is taken by its low or high byte, `#<f` and `#>f`, or
    by an instruction that reads it (kind 5, `LDA f,X`). A kind 1 fix-up naming a function
    there is the operand of a JSR or JMP, a call, which needs a CALL record of its own; without
    one the call is an error (lk_fix.target), and must not quietly keep the callee. A
    function's fix-ups naming itself are its labels or its own address and keep nothing. In
    constant data (source NONE) every fix-up naming a function takes its address. Slots and
    class parameters are kept with their function or class."""
    sk = lk_sym.kind_of(s)
    if sk == lk_sym.VARIABLE or sk == lk_sym.CONSTANT:
        return True
    if sk != lk_sym.FUNCTION or slot != 0xFF:
        return False
    return source == lk_tab.NONE or (s != source and kind != 1)


def read_entry(obj):
    """Read the next fix-up entry of the record being read: its kind, symbol and slot."""
    global e_kind, e_sym, e_slot
    lk_rec.get_word()
    e_kind = lk_rec.get_byte()
    e_sym = lk_scan.global_sym(obj, lk_rec.get_word())
    e_slot = lk_rec.get_byte()
    lk_rec.get_word()


def keep_in_object(obj):
    """One reading of object obj: what the fix-ups of what is kept so far name is kept. True
    if that kept something new.

    A DFIX record's entries belong to the DATA record after it, which says whose they are:
    they wait in the work area (above what reach() uses) until it comes."""
    changed = False
    source = lk_tab.NONE
    named_count = 0
    lk_rec.open_object(obj)
    kind = lk_rec.advance()
    while kind != lk_rec.R_END:
        if kind == lk_rec.R_FUNC:
            source = lk_scan.global_sym(obj, lk_rec.get_word())
        elif kind == lk_rec.R_ENDF:
            source = lk_tab.NONE
        elif kind == lk_rec.R_FIX and is_kept(source):
            while lk_rec.left() > 0:
                read_entry(obj)
                if keeps(obj, source, e_kind, e_sym, e_slot) and keep_target(source, e_sym):
                    changed = True
        elif kind == lk_rec.R_DFIX:
            named_count = 0
            while lk_rec.left() > 0:
                read_entry(obj)
                if keeps(obj, lk_tab.NONE, e_kind, e_sym, e_slot):
                    # More than a table may have: an error if the table is kept (lk_emit).
                    if named_count < lk_tab.MAX_FIXES:
                        lk_tab.work[NAMED + named_count] = e_sym
                    named_count += 1
        elif kind == lk_rec.R_DATA:
            data = lk_scan.global_sym(obj, lk_rec.get_word())
            if is_kept(data):
                if named_count > lk_tab.MAX_FIXES:
                    lk_err.fail(lk_err.E_FIXES)
                for i in range(0, named_count):
                    if keep_target(data, lk_tab.work[NAMED + i]):
                        changed = True
            named_count = 0
        kind = lk_rec.advance()
    lk_rec.close()
    return changed


def keep_referenced():
    """Keep what the fix-ups of kept code and kept constant data name, reading every object file
    again until a reading keeps nothing new.

    A variable or constant is kept; a function whose address is taken and that nothing
    reached is reached from context 0. Only now must a symbol be defined: one that nothing
    kept refers to may be missing."""
    changed = True
    while changed:
        changed = False
        for obj in range(0, lk_scan.object_count):
            if keep_in_object(obj):
                changed = True


def find_contexts(main_sym):
    """Number the contexts and mark what each reaches."""
    reach(main_sym, 0)
    for f in range(0, lk_tab.fn_count):
        if lk_boot.is_init(f):
            reach(lk_tab.fn_sym[f], 0)
    lk_tab.ctx_count = 1
    for f in range(0, lk_tab.fn_count):
        if (lk_tab.fn_flags[f] & lk_tab.F_INTERRUPT) != 0:
            if lk_tab.ctx_count == lk_tab.MAX_CONTEXTS:
                lk_err.fail(lk_err.E_CONTEXTS)
            reach(lk_tab.fn_sym[f], lk_tab.ctx_count)
            lk_tab.ctx_count += 1
    keep_referenced()


# ---- pointer classes

def pointer_caller(k, ctx):
    """A function of context ctx that calls through class k."""
    block = lk_tab.cls_sym[k]
    for f in range(0, lk_tab.fn_count):
        if lk_tab.has_copy(f, ctx):
            e = lk_sym.sym_b[lk_tab.fn_sym[f]]
            while e != 0:
                if lk_tab.edge_flag(e - 1) <= lk_tab.E_NOSAVE and edge_target(e - 1) == block:
                    return lk_tab.fn_sym[f]
                e = lk_tab.edge_next[e - 1]
    return block


def fail_two_contexts(k, first, second):
    lk_err.begin(lk_err.E_CLASS_CONTEXTS)
    lk_err.colon()
    lk_sym.error_name(lk_tab.cls_sym[k])
    lk_err.comma()
    lk_sym.error_name(pointer_caller(k, first))
    lk_err.comma()
    lk_sym.error_name(pointer_caller(k, second))
    lk_err.finish()


def class_contexts():
    """Each live class is called through pointers from exactly one context."""
    for k in range(0, lk_tab.cls_count):
        first = lk_tab.NONE
        for ctx in range(0, lk_tab.ctx_count):
            if (lk_tab.cls_reach[k] & (1 << ctx)) != 0:
                if first != lk_tab.NONE:
                    fail_two_contexts(k, first, ctx)
                first = ctx
        if first != lk_tab.NONE:
            lk_tab.cls_ctx[k] = first


def stricter(a, b):
    """The zero page class that satisfies both: must (0) beats never (2) beats either (1)."""
    if a == 0 or b == 0:
        return 0
    if a == 2 or b == 2:
        return 2
    return 1


def fit_member(k, f):
    """Member f's parameters are the block's: check they match and add what they ask for."""
    np = lk_tab.cls_np[k]
    first = lk_tab.fn_slot[f]
    params = 0
    while params < lk_tab.fn_nslots[f] and lk_tab.slot_kind(first + params) == 0:
        params += 1
    if params != np:
        lk_sym.fail(lk_err.E_MEMBER, lk_tab.fn_sym[f])
    for i in range(0, np):
        p = lk_tab.cls_par[k] + i
        if lk_tab.slot_bytes(first + i) != lk_tab.cp_size[p]:
            lk_sym.fail(lk_err.E_MEMBER, lk_tab.fn_sym[f])
        lk_tab.cp_info[p] = stricter(lk_tab.cp_info[p], lk_tab.slot_info[first + i] & lk_tab.S_CLASS)
        weight = lk_tab.cp_weight[p] + lk_tab.slot_weight[first + i]
        if weight > 255:
            weight = 255
        lk_tab.cp_weight[p] = weight


def fit_members():
    for i in range(0, lk_tab.memb_count):
        k = lk_tab.class_of(lk_sym.sym_a[lk_tab.memb_class[i]])
        fit_member(k, lk_sym.sym_a[lk_tab.memb_func[i]])


# ---- nodes

def make_nodes():
    """One node per copy of a kept function, in placement order, then one per live class."""
    for f in range(0, lk_tab.fn_count):
        lk_tab.fn_node[f] = lk_tab.node_count
        for ctx in range(0, lk_tab.ctx_count):
            if lk_tab.has_copy(f, ctx):
                lk_tab.new_node(f, ctx)
    for k in range(0, lk_tab.cls_count):
        if lk_tab.cls_reach[k] != 0:
            lk_tab.cls_node[k] = lk_tab.node_count
            lk_tab.new_node(lk_tab.CLASS_NODE + k, lk_tab.cls_ctx[k])


def first_edge(n):
    """The first edge of node n + 1, or 0: the start of a walk with edge_node and next_edge."""
    return lk_sym.sym_b[lk_tab.node_sym(n)]


def next_edge(e):
    return lk_tab.edge_next[e - 1]


def edge_node(n, e):
    """The node that node n calls by edge e + 1, and whether the edge applies to n at all.

    An edge joins symbols; here it becomes an edge between copies in n's context. It does not
    apply if the target has nothing in that context: a class block lives in one context only,
    and elsewhere a member is an ordinary function."""
    ctx = lk_tab.node_ctx[n]
    # Only a call that places storage can name a symbol nothing defines (lk_scan.rec_call):
    # what that call is in was dropped.
    if not lk_sym.is_defined(lk_tab.edge_sym(e - 1)):
        return 0, False
    target = edge_target(e - 1)
    if lk_sym.kind_of(target) == lk_sym.CLASS:
        k = lk_sym.sym_a[target]
        if lk_tab.cls_reach[k] != 0 and lk_tab.cls_ctx[k] == ctx:
            return lk_tab.cls_node[k], True
        return 0, False
    f = lk_sym.sym_a[target]
    if lk_tab.has_copy(f, ctx):
        return lk_tab.copy_node(f, ctx), True
    return 0, False


# ---- cycles

def push(n):
    """Tarjan: node n is discovered."""
    global stack_top, found_top, discovered
    discovered += 1
    lk_tab.work[lk_tab.W_SCC + n] = ON_STACK
    lk_tab.work[SEEN + n] = discovered
    lk_tab.work[LOW + n] = discovered
    lk_tab.work[FOUND + found_top] = n
    found_top += 1
    lk_tab.work[STACK + stack_top] = n
    lk_tab.work[STACK_EDGE + stack_top] = first_edge(n)
    stack_top += 1


def close_set(n):
    """Tarjan: n is the first-found node of a set; everything found since belongs to it."""
    global found_top, order_count, scc_count
    member = lk_tab.NONE
    while member != n:
        found_top -= 1
        member = lk_tab.work[FOUND + found_top]
        lk_tab.work[lk_tab.W_SCC + member] = scc_count
        lk_tab.work[lk_tab.W_ORDER + order_count] = member
        order_count += 1
    scc_count += 1


def search(root):
    """Tarjan's algorithm from an undiscovered node."""
    global stack_top
    push(root)
    while stack_top > 0:
        n = lk_tab.work[STACK + stack_top - 1]
        e = lk_tab.work[STACK_EDGE + stack_top - 1]
        if e != 0:
            lk_tab.work[STACK_EDGE + stack_top - 1] = next_edge(e)
            target, applies = edge_node(n, e)
            if applies:
                if lk_tab.work[SEEN + target] == 0:
                    push(target)
                elif lk_tab.work[lk_tab.W_SCC + target] == ON_STACK and lk_tab.work[SEEN + target] < lk_tab.work[LOW + n]:
                    lk_tab.work[LOW + n] = lk_tab.work[SEEN + target]
        else:
            stack_top -= 1
            if lk_tab.work[LOW + n] == lk_tab.work[SEEN + n]:
                close_set(n)
            if stack_top > 0:
                caller = lk_tab.work[STACK + stack_top - 1]
                if lk_tab.work[LOW + n] < lk_tab.work[LOW + caller]:
                    lk_tab.work[LOW + caller] = lk_tab.work[LOW + n]


def find_sets():
    for n in range(0, lk_tab.node_count):
        lk_tab.work[SEEN + n] = 0
    for n in range(0, lk_tab.node_count):
        if lk_tab.work[SEEN + n] == 0:
            search(n)


def is_recursive(n):
    """A class block is only storage: what must be `recursive` is the functions around it."""
    if lk_tab.node_is_class(n):
        return True
    return (lk_tab.fn_flags[lk_tab.node_own[n]] & lk_tab.F_RECURSIVE) != 0


def fail_cycle(source, target):
    """Report the cycle that the call source -> target closes."""
    # Find a way back from target to source inside their set, breadth first; lk_tab.work[SEEN + ] holds the
    # node each node was reached from, + 1.
    for n in range(0, lk_tab.node_count):
        lk_tab.work[SEEN + n] = 0
    head = 0
    tail = 1
    lk_tab.work[STACK + 0] = target
    lk_tab.work[SEEN + target] = target + 1
    while head < tail and lk_tab.work[SEEN + source] == 0:
        n = lk_tab.work[STACK + head]
        head += 1
        e = first_edge(n)
        while e != 0:
            reached, applies = edge_node(n, e)
            if applies and lk_tab.work[SEEN + reached] == 0 and lk_tab.work[lk_tab.W_SCC + reached] == lk_tab.work[lk_tab.W_SCC + n]:
                lk_tab.work[SEEN + reached] = n + 1
                lk_tab.work[STACK + tail] = reached
                tail += 1
            e = next_edge(e)
    # Walk back from source to target, then print it forwards.
    count = 0
    n = source
    while n != target:
        lk_tab.work[FOUND + count] = n
        count += 1
        n = lk_tab.work[SEEN + n] - 1
    lk_err.begin(lk_err.E_CYCLE)
    lk_err.colon()
    lk_tab.error_node(source)
    lk_err.arrow()
    lk_tab.error_node(target)
    for i in range(count - 1, -1, -1):
        lk_err.arrow()
        lk_tab.error_node(lk_tab.work[FOUND + i])
    lk_err.finish()


def is_member(f, k):
    """True if function f is a member of class k."""
    return lk_tab.fn_class[f] != 0 and lk_tab.class_of(lk_tab.fn_class[f] - 1) == k


def fail_member_call(n, target, e):
    """Report the call by edge e + 1 of node n, a function, into the block of its own class,
    node target: as the call of the member it is (E_VIA), or as the call through the class."""
    k = lk_tab.node_class(target)
    lk_err.begin(lk_err.E_MEMBER_CYCLE)
    lk_err.colon()
    lk_tab.error_node(n)
    lk_err.arrow()
    callee = lk_tab.cls_sym[k]
    if (lk_tab.edge_flag(e - 1) & lk_tab.E_VIA) != 0:
        other = first_edge(n)
        while other != 0:
            s = lk_tab.edge_sym(other - 1)
            if (lk_tab.edge_flag(other - 1) & lk_tab.E_VIA) == 0 and lk_sym.kind_of(s) == lk_sym.FUNCTION \
                    and lk_sym.is_defined(s) and is_member(lk_sym.sym_a[s], k):
                callee = s
            other = next_edge(other)
    lk_sym.error_name(callee)
    if callee == lk_tab.cls_sym[k]:
        for i in range(0, len(OWN_CLASS)):
            lk_err.put(OWN_CLASS[i])
    else:
        for i in range(0, len(IN_CLASS)):
            lk_err.put(IN_CLASS[i])
        lk_sym.error_name(lk_tab.cls_sym[k])
    lk_err.finish()


def check_cycles():
    """Every call between two nodes of one set is recursion and must be marked as such.

    A class block counts as `recursive`, and its edge to a member as saving, because a member
    that saves its frame saves its parameters in the block with it (code-model.md,
    "Recursion"). The checks therefore fall on the real calls into and out of the block. A
    member's call into its own class's block, of another member or through the class, is
    reported as that: the two share their parameters (language.md, "Members calling members")."""
    for n in range(0, lk_tab.node_count):
        e = first_edge(n)
        while e != 0:
            target, applies = edge_node(n, e)
            if applies and lk_tab.work[lk_tab.W_SCC + target] == lk_tab.work[lk_tab.W_SCC + n]:
                saves = (lk_tab.edge_flag(e - 1) & lk_tab.E_NOSAVE) == 0
                if not (saves and is_recursive(n) and is_recursive(target)):
                    if not lk_tab.node_is_class(n) and lk_tab.node_is_class(target) \
                            and is_member(lk_tab.node_own[n], lk_tab.node_class(target)):
                        fail_member_call(n, target, e)
                    fail_cycle(n, target)
            e = next_edge(e)


def build(main_sym):
    """From the tables of lk_scan to nodes, sets and the order to allocate in."""
    find_contexts(main_sym)
    class_contexts()
    fit_members()
    make_nodes()
    find_sets()
    check_cycles()
