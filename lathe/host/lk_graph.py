"""The call graph: what is reachable, in which contexts, and where recursion is.

build() does the linker's steps between reading and allocating:

1. Contexts. Context 0 is the main program, rooted at main and at every module's `$init`
   (lk_boot); every interrupt function is the root of a context of its own. A function gets one
   bit in fn_ctx per context that reaches it; a function with no bit is dropped. A function
   whose address is taken by constant data or by a kept function is kept too: if nothing else
   reaches it, it is a further root of context 0. So no address in the image is that of a
   function the linker dropped.
2. Pointer classes. A class is live if some kept function calls through it, and all those
   calls must be in one context. Its block's parameters take the strictest zero page class and
   the summed weight of its members' parameters.
3. Nodes: a copy of each function per context that reaches it, and a node per live class.
4. Cycles. The nodes are grouped into sets that can reach each other (node_scc), by Tarjan's
   algorithm with its own stack in place of recursion. A call inside such a set is recursion:
   it must save the caller's frame, and both ends must be `recursive`.

`order` lists the nodes callees first, with the nodes of a set next to each other: the order in
which lk_alloc lays out storage, read backwards.

Calls that only place storage (E_PENDING, E_VIA) do not make anything reachable.
"""
import lk_boot
import lk_err
import lk_sym
import lk_tab

order = [0] * lk_tab.MAX_NODES      # nodes, callees before their callers
order_count = 0
scc_count = 0

# Work columns for the searches, one row per node (or per symbol while there are no nodes).
stack = [0] * lk_tab.MAX_NODES      # nodes or symbols still to finish
stack_edge = [0] * lk_tab.MAX_NODES # for each, the next edge to follow + 1
found = [0] * lk_tab.MAX_NODES      # Tarjan: nodes found and not yet given a set
seen = [0] * lk_tab.MAX_NODES       # Tarjan: order of discovery + 1; path search: came from + 1
low = [0] * lk_tab.MAX_NODES        # Tarjan: earliest node reachable
ON_STACK = 0xFFFF                   # node_scc of a node in `found`
IN_CLASS = b", both in the pointer class "
OWN_CLASS = b", its own pointer class"
stack_top = 0
found_top = 0
discovered = 0                      # Tarjan: nodes discovered so far


def edge_target(e):
    """The symbol edge e calls: a function, or the class standing for the class named."""
    target = lk_tab.edge_to[e]
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
    stack[0] = root
    while top > 0:
        top -= 1
        e = lk_sym.sym_b[stack[top]]
        while e != 0:
            if (lk_tab.edge_flags[e - 1] & (lk_tab.E_PENDING | lk_tab.E_VIA)) == 0:
                target = edge_target(e - 1)
                if mark(target, ctx):
                    if top == lk_tab.MAX_NODES:
                        lk_err.fail(lk_err.E_COPIES)
                    stack[top] = target
                    top += 1
            e = lk_tab.edge_next[e - 1]


def keep_addresses():
    """Reach, from context 0, every function whose address something kept takes and nothing
    reached. What such a function takes is then kept too, so go round until nothing changes."""
    changed = True
    while changed:
        changed = False
        for i in range(0, lk_tab.adr_count):
            source = lk_tab.adr_from[i]
            f = lk_sym.sym_a[lk_tab.adr_to[i]]
            if lk_tab.fn_ctx[f] == 0 and (source == lk_tab.NONE or lk_tab.fn_ctx[source] != 0):
                reach(lk_tab.adr_to[i], 0)
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
    keep_addresses()


# ---- pointer classes

def pointer_caller(k, ctx):
    """A function of context ctx that calls through class k."""
    block = lk_tab.cls_sym[k]
    for f in range(0, lk_tab.fn_count):
        if lk_tab.has_copy(f, ctx):
            e = lk_sym.sym_b[lk_tab.fn_sym[f]]
            while e != 0:
                if lk_tab.edge_flags[e - 1] <= lk_tab.E_NOSAVE and edge_target(e - 1) == block:
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
        if lk_tab.slot_size[first + i] != lk_tab.cp_size[p]:
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
    lk_tab.node_scc[n] = ON_STACK
    seen[n] = discovered
    low[n] = discovered
    found[found_top] = n
    found_top += 1
    stack[stack_top] = n
    stack_edge[stack_top] = first_edge(n)
    stack_top += 1


def close_set(n):
    """Tarjan: n is the first-found node of a set; everything found since belongs to it."""
    global found_top, order_count, scc_count
    member = lk_tab.NONE
    while member != n:
        found_top -= 1
        member = found[found_top]
        lk_tab.node_scc[member] = scc_count
        order[order_count] = member
        order_count += 1
    scc_count += 1


def search(root):
    """Tarjan's algorithm from an undiscovered node."""
    global stack_top
    push(root)
    while stack_top > 0:
        n = stack[stack_top - 1]
        e = stack_edge[stack_top - 1]
        if e != 0:
            stack_edge[stack_top - 1] = next_edge(e)
            target, applies = edge_node(n, e)
            if applies:
                if seen[target] == 0:
                    push(target)
                elif lk_tab.node_scc[target] == ON_STACK and seen[target] < low[n]:
                    low[n] = seen[target]
        else:
            stack_top -= 1
            if low[n] == seen[n]:
                close_set(n)
            if stack_top > 0:
                caller = stack[stack_top - 1]
                if low[n] < low[caller]:
                    low[caller] = low[n]


def find_sets():
    for n in range(0, lk_tab.node_count):
        seen[n] = 0
    for n in range(0, lk_tab.node_count):
        if seen[n] == 0:
            search(n)


def is_recursive(n):
    """A class block is only storage: what must be `recursive` is the functions around it."""
    if lk_tab.node_is_class(n):
        return True
    return (lk_tab.fn_flags[lk_tab.node_own[n]] & lk_tab.F_RECURSIVE) != 0


def fail_cycle(source, target):
    """Report the cycle that the call source -> target closes."""
    # Find a way back from target to source inside their set, breadth first; seen[] holds the
    # node each node was reached from, + 1.
    for n in range(0, lk_tab.node_count):
        seen[n] = 0
    head = 0
    tail = 1
    stack[0] = target
    seen[target] = target + 1
    while head < tail and seen[source] == 0:
        n = stack[head]
        head += 1
        e = first_edge(n)
        while e != 0:
            reached, applies = edge_node(n, e)
            if applies and seen[reached] == 0 and lk_tab.node_scc[reached] == lk_tab.node_scc[n]:
                seen[reached] = n + 1
                stack[tail] = reached
                tail += 1
            e = next_edge(e)
    # Walk back from source to target, then print it forwards.
    count = 0
    n = source
    while n != target:
        found[count] = n
        count += 1
        n = seen[n] - 1
    lk_err.begin(lk_err.E_CYCLE)
    lk_err.colon()
    lk_tab.error_node(source)
    lk_err.arrow()
    lk_tab.error_node(target)
    for i in range(count - 1, -1, -1):
        lk_err.arrow()
        lk_tab.error_node(found[i])
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
    if (lk_tab.edge_flags[e - 1] & lk_tab.E_VIA) != 0:
        other = first_edge(n)
        while other != 0:
            s = lk_tab.edge_to[other - 1]
            if (lk_tab.edge_flags[other - 1] & lk_tab.E_VIA) == 0 and lk_sym.kind_of(s) == lk_sym.FUNCTION \
                    and is_member(lk_sym.sym_a[s], k):
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
            if applies and lk_tab.node_scc[target] == lk_tab.node_scc[n]:
                saves = (lk_tab.edge_flags[e - 1] & lk_tab.E_NOSAVE) == 0
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
