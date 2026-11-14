"""Storage: an address for every variable, slot and class parameter (code-model.md, "Storage").

There are two pools, zero page and main memory (the environment's `zeropage` and `data`
ranges). In each, from the bottom:

    module-level variables, which are never shared
    the frames and class blocks of context 0
    those of context 1, and so on: a handler never touches what it interrupted

Within a context a node (a function copy's frame, or a class block) starts where the storage of
everything that can be active when it is called ends: the largest end among its callers. Nodes
that can reach each other by recursion form a set (lk_graph) that is laid out as one piece, its
members side by side, with every callee of any member above all of it.

Zero page. Class 0 slots are in zero page and class 2 never. The class 1 slots, variables and
class parameters of the whole program are then taken heaviest weight first, in the order slots,
class parameters, variables within a weight, and each is moved into zero page if the deepest
chain of calls still fits with it there; one that does not fit is left in main memory and the
next is tried. If every candidate fits, one layout shows it. Otherwise most items are judged
from bounds, without a new layout (judge).

A slot's choice holds for every copy of its function. A member's parameter slots are not in
the frame of the copy in its class's context: they are the class block.

Main memory on an NMOS 6502: no two-byte item is placed across a page boundary, because
`JMP (pointer)` reads the wrong high byte there and any pointer may be called through.
"""
import lk_envf
import lk_err
import lk_graph
import lk_name
import lk_op
import lk_sym
import lk_tab

POOL_ZP = 0
POOL_MAIN = 1

# The layout of one pool, a row per node, in lk_tab.work: where each column starts. Addresses
# here count from the start of the pool.
LAY_BASE = 0                        # where the node starts
LAY_END = lk_tab.MAX_NODES          # where its set ends
LAY_SIZE = 2 * lk_tab.MAX_NODES     # the size of its set
LAY_DOWN = 3 * lk_tab.MAX_NODES     # the most storage any chain of calls needs above its set
CHAIN = LAY_DOWN                    # the nodes of a call chain, for an error message, which needs
                                    # no depths
WEIGHTS = 256
WEIGHT_COUNT = lk_tab.W_MBASE       # while promote() works, before nodes have main memory: how many class
                                    # 1 candidates have each weight

ctx_bottom = [0] * lk_tab.MAX_CONTEXTS  # where a context's storage starts in the pool
ctx_depth = [0] * lk_tab.MAX_CONTEXTS   # how much its deepest chain needs

zp_cap = 0                          # bytes of zero page the linker may use
zp_vars = 0                         # of which module-level variables have this many
zp_used = 0                         # and variables and all contexts this many


def straddles(addr, size):
    """True if a two-byte item at addr would lie across a page boundary and must not."""
    return lk_envf.cpu == lk_op.CPU_6502 and size == 2 and (addr & 0xFF) == 0xFF


# ---- the size of a node

def zp_size(n):
    """Bytes of zero page node n needs, from the choices made so far."""
    total = 0
    if lk_tab.node_is_class(n):
        k = lk_tab.node_class(n)
        for p in range(lk_tab.cls_par[k], lk_tab.cls_par[k] + lk_tab.cls_np[k]):
            if (lk_tab.cp_info[p] & lk_tab.S_ZP) != 0:
                total += lk_tab.cp_size[p]
        return total
    f = lk_tab.own_of(n)
    blocked = lk_tab.in_block(f, lk_tab.ctx_of(n))
    for i in range(0, lk_tab.fn_nslots(f)):
        s = lk_tab.fn_slot[f] + i
        if lk_tab.slot_in_zp(s) and lk_tab.in_frame(f, i, blocked):
            total += lk_tab.slot_bytes(s)
    return total


def main_item(pos, size):
    """Where the next main memory item of this size starts if the last one ended at `pos`."""
    if straddles((lk_envf.data_lo + pos) & 0xFFFF, size):
        return lk_tab.add16(pos, 1)
    return pos


def main_end(n, pos):
    """Where node n's main memory ends if it starts at `pos`."""
    if lk_tab.node_is_class(n):
        k = lk_tab.node_class(n)
        for p in range(lk_tab.cls_par[k], lk_tab.cls_par[k] + lk_tab.cls_np[k]):
            if (lk_tab.cp_info[p] & lk_tab.S_ZP) == 0:
                pos = lk_tab.add16(main_item(pos, lk_tab.cp_size[p]), lk_tab.cp_size[p])
        return pos
    f = lk_tab.own_of(n)
    blocked = lk_tab.in_block(f, lk_tab.ctx_of(n))
    for i in range(0, lk_tab.fn_nslots(f)):
        s = lk_tab.fn_slot[f] + i
        if not lk_tab.slot_in_zp(s) and lk_tab.in_frame(f, i, blocked):
            pos = lk_tab.add16(main_item(pos, lk_tab.slot_bytes(s)), lk_tab.slot_bytes(s))
    return pos


def node_end(pool, n, pos):
    if pool == POOL_ZP:
        return lk_tab.add16(pos, lk_tab.work[lk_tab.W_ZSIZE + n])
    return main_end(n, pos)


# ---- laying out one pool

def raise_callees(n, top):
    """Nothing node n calls outside its set may start below `top`."""
    e = lk_graph.first_edge(n)
    while e != 0:
        target, applies = lk_graph.edge_node(n, e)
        if applies and lk_tab.work[lk_tab.W_SCC + target] != lk_tab.work[lk_tab.W_SCC + n] and lk_tab.work[LAY_BASE + target] < top:
            lk_tab.work[LAY_BASE + target] = top
        e = lk_graph.next_edge(n, e)


def layout_set(pool, first, limit):
    """Lay out the set that is lk_tab.work[lk_tab.W_ORDER + first..limit-1]. Returns where it ends."""
    start = 0
    for i in range(first, limit):
        if lk_tab.work[LAY_BASE + lk_tab.work[lk_tab.W_ORDER + i]] > start:
            start = lk_tab.work[LAY_BASE + lk_tab.work[lk_tab.W_ORDER + i]]
    pos = start
    for i in range(first, limit):
        lk_tab.work[LAY_BASE + lk_tab.work[lk_tab.W_ORDER + i]] = pos
        pos = node_end(pool, lk_tab.work[lk_tab.W_ORDER + i], pos)
    for i in range(first, limit):
        lk_tab.work[LAY_END + lk_tab.work[lk_tab.W_ORDER + i]] = pos
        lk_tab.work[LAY_SIZE + lk_tab.work[lk_tab.W_ORDER + i]] = pos - start
        raise_callees(lk_tab.work[lk_tab.W_ORDER + i], pos)
    return pos


def layout(pool, ctx):
    """Lay out the nodes of one context from ctx_bottom up. Returns where the context ends.

    lk_graph.order has callees first, so going through it backwards meets every caller of a
    set before the set itself."""
    top = ctx_bottom[ctx]
    for n in range(0, lk_tab.node_count):
        if lk_tab.is_node(n) and lk_tab.ctx_of(n) == ctx:
            lk_tab.work[LAY_BASE + n] = ctx_bottom[ctx]
    limit = lk_graph.order_count
    while limit > 0:
        first = limit - 1
        scc = lk_tab.work[lk_tab.W_SCC + lk_tab.work[lk_tab.W_ORDER + first]]
        while first > 0 and lk_tab.work[lk_tab.W_SCC + lk_tab.work[lk_tab.W_ORDER + first - 1]] == scc:
            first -= 1
        if lk_tab.ctx_of(lk_tab.work[lk_tab.W_ORDER + first]) == ctx:
            set_end = layout_set(pool, first, limit)
            if set_end > top:
                top = set_end
        limit = first
    return top


def deepen():
    """Work out lay_down, callees first: the deepest chain of storage above each set."""
    first = 0
    while first < lk_graph.order_count:
        scc = lk_tab.work[lk_tab.W_SCC + lk_tab.work[lk_tab.W_ORDER + first]]
        limit = first + 1
        while limit < lk_graph.order_count and lk_tab.work[lk_tab.W_SCC + lk_tab.work[lk_tab.W_ORDER + limit]] == scc:
            limit += 1
        down = 0
        for i in range(first, limit):
            n = lk_tab.work[lk_tab.W_ORDER + i]
            e = lk_graph.first_edge(n)
            while e != 0:
                target, applies = lk_graph.edge_node(n, e)
                if applies and lk_tab.work[lk_tab.W_SCC + target] != scc:
                    below = lk_tab.add16(lk_tab.work[LAY_SIZE + target], lk_tab.work[LAY_DOWN + target])
                    if below > down:
                        down = below
                e = lk_graph.next_edge(n, e)
        for i in range(first, limit):
            lk_tab.work[LAY_DOWN + lk_tab.work[lk_tab.W_ORDER + i]] = down
        first = limit


def layout_zp():
    """Lay out zero page with the choices made so far. True if it all fits."""
    global zp_used
    lk_tab.overflow = False
    zp_used = zp_vars
    for ctx in range(0, lk_tab.ctx_count):
        ctx_bottom[ctx] = 0
        ctx_depth[ctx] = layout(POOL_ZP, ctx)
        zp_used = lk_tab.add16(zp_used, ctx_depth[ctx])
    deepen()
    return not lk_tab.overflow and zp_used <= zp_cap


# ---- errors that name a call chain

def deepest_context():
    ctx = 0
    for c in range(1, lk_tab.ctx_count):
        if ctx_depth[c] > ctx_depth[ctx]:
            ctx = c
    return ctx


def deepest_node(ctx):
    """A node of the context whose set ends at the context's top, and whether there is one."""
    if ctx_depth[ctx] == 0:
        return 0, False
    n = lk_tab.first_in_order()
    while n != lk_tab.NONE:
        if lk_tab.ctx_of(n) == ctx and lk_tab.work[LAY_END + n] - ctx_bottom[ctx] == ctx_depth[ctx]:
            return n, True
        n = lk_tab.next_in_order(n)
    return 0, False


def caller_below(n):
    """A caller of node n's set whose own set ends where n's starts, and whether there is one."""
    start = lk_tab.work[LAY_END + n] - lk_tab.work[LAY_SIZE + n]
    caller = lk_tab.first_in_order()
    while caller != lk_tab.NONE:
        if lk_tab.ctx_of(caller) == lk_tab.ctx_of(n) and lk_tab.work[LAY_END + caller] == start \
                and lk_tab.work[lk_tab.W_SCC + caller] != lk_tab.work[lk_tab.W_SCC + n]:
            e = lk_graph.first_edge(caller)
            while e != 0:
                target, applies = lk_graph.edge_node(caller, e)
                if applies and lk_tab.work[lk_tab.W_SCC + target] == lk_tab.work[lk_tab.W_SCC + n]:
                    return caller, True
                e = lk_graph.next_edge(caller, e)
        caller = lk_tab.next_in_order(caller)
    return 0, False


def fail_full(error, amount, wrapped):
    """Report a pool that is too small, by how much, and the call chain that needs the most of
    it."""
    count = 0
    n, more = deepest_node(deepest_context())
    while more:
        member = lk_tab.first_in_order()
        while member != lk_tab.NONE:
            if lk_tab.work[lk_tab.W_SCC + member] == lk_tab.work[lk_tab.W_SCC + n]:
                lk_tab.work[CHAIN + count] = member
                count += 1
            member = lk_tab.next_in_order(member)
        n, more = caller_below(n)
    lk_err.begin(error)
    lk_err.over(amount, wrapped)
    for i in range(count - 1, -1, -1):
        if i == count - 1:
            lk_err.colon()
        else:
            lk_err.arrow()
        lk_name.error_node(lk_tab.work[CHAIN + i])
    lk_err.finish()


def fail_zp():
    fail_full(lk_err.E_ZP_FULL, zp_used - zp_cap, lk_tab.overflow)


# ---- choosing what goes in zero page

def is_candidate(zp_class, size):
    """True for a class 1 item small enough to be worth trying."""
    return zp_class == 1 and size <= zp_cap


def must_fit(size, sym):
    """A class 0 item larger than all of zero page can be reported at once."""
    if size > zp_cap:
        lk_err.begin(lk_err.E_ZP_FULL)
        lk_err.over(size - zp_cap, False)
        lk_err.colon()
        lk_name.error_name(sym)
        lk_err.finish()


def start_choices():
    """Class 0 goes in zero page. Count the class 1 candidates by weight."""
    global zp_vars
    for w in range(0, WEIGHTS):
        lk_tab.work[WEIGHT_COUNT + w] = 0
    for f in range(0, lk_tab.fn_count):
        if lk_tab.fn_ctx[f] != 0:
            for s in range(lk_tab.fn_slot[f], lk_tab.fn_slot[f] + lk_tab.fn_nslots(f)):
                if lk_tab.slot_class(s) == 0:
                    must_fit(lk_tab.slot_bytes(s), lk_tab.fn_ref(f))
                    lk_tab.slot_sz[s] |= lk_tab.SL_ZP
                elif is_candidate(lk_tab.slot_class(s), lk_tab.slot_bytes(s)):
                    lk_tab.work[WEIGHT_COUNT + lk_tab.slot_weight[s]] += 1
    for k in range(0, lk_tab.cls_count):
        if lk_tab.cls_reach[k] != 0:
            for p in range(lk_tab.cls_par[k], lk_tab.cls_par[k] + lk_tab.cls_np[k]):
                if (lk_tab.cp_info[p] & lk_tab.S_CLASS) == 0:
                    must_fit(lk_tab.cp_size[p], lk_tab.cls_ref(k))
                    lk_tab.cp_info[p] |= lk_tab.S_ZP
                elif is_candidate(lk_tab.cp_info[p] & lk_tab.S_CLASS, lk_tab.cp_size[p]):
                    lk_tab.work[WEIGHT_COUNT + lk_tab.cp_weight[p]] += 1
    zp_vars = 0
    for d in range(0, lk_tab.def_count):
        if lk_tab.is_kept_var(d):
            if (lk_tab.def_f[d] & lk_tab.D_CLASS) == 0:
                must_fit(lk_tab.def_b[d], lk_tab.def_ref(d))
                lk_tab.def_f[d] |= lk_tab.D_ZP
                zp_vars += lk_tab.def_b[d]
            elif (lk_tab.def_f[d] & lk_tab.D_CLASS) == 1 and lk_tab.def_b[d] <= zp_cap:
                lk_tab.work[WEIGHT_COUNT + lk_tab.def_w(d)] += 1


def growth(n, size):
    """How much deeper node n's context gets if its node needs `size` more bytes."""
    top = lk_tab.add16(lk_tab.add16(lk_tab.work[LAY_END + n], size), lk_tab.work[LAY_DOWN + n])
    if top > ctx_depth[lk_tab.ctx_of(n)]:
        return top - ctx_depth[lk_tab.ctx_of(n)]
    return 0


def fits(need):
    return not lk_tab.overflow and need <= zp_cap - zp_used


def slot_growth(f, i):
    """How much more zero page the program needs with slot i of f in it."""
    need = 0
    for ctx in range(0, lk_tab.ctx_count):
        if lk_tab.has_copy(f, ctx) and lk_tab.in_frame(f, i, lk_tab.in_block(f, ctx)):
            need = lk_tab.add16(need, growth(lk_tab.copy_node(f, ctx), lk_tab.slot_bytes(lk_tab.fn_slot[f] + i)))
    return need


def move_slot(f, i, into):
    """Put slot i of f in zero page, or take it out again."""
    s = lk_tab.fn_slot[f] + i
    lk_tab.slot_sz[s] ^= lk_tab.SL_ZP
    for ctx in range(0, lk_tab.ctx_count):
        if lk_tab.has_copy(f, ctx) and lk_tab.in_frame(f, i, lk_tab.in_block(f, ctx)):
            n = lk_tab.copy_node(f, ctx)
            if into:
                lk_tab.work[lk_tab.W_ZSIZE + n] += lk_tab.slot_bytes(s)
            else:
                lk_tab.work[lk_tab.W_ZSIZE + n] -= lk_tab.slot_bytes(s)


def move_cparam(k, p, into):
    lk_tab.cp_info[p] ^= lk_tab.S_ZP
    if into:
        lk_tab.work[lk_tab.W_ZSIZE + lk_tab.cls_node[k]] += lk_tab.cp_size[p]
    else:
        lk_tab.work[lk_tab.W_ZSIZE + lk_tab.cls_node[k]] -= lk_tab.cp_size[p]


def move_var(d, into):
    global zp_vars
    lk_tab.def_f[d] ^= lk_tab.D_ZP
    if into:
        zp_vars += lk_tab.def_b[d]
    else:
        zp_vars -= lk_tab.def_b[d]


def var_is_candidate(d, weight):
    return lk_tab.is_kept_var(d) and (lk_tab.def_f[d] & lk_tab.D_CLASS) == 1 \
        and lk_tab.def_w(d) == weight and lk_tab.def_b[d] <= zp_cap


def move_weight(weight, into):
    """Move every candidate of this weight into zero page, or all of them out again."""
    for f in range(0, lk_tab.fn_count):
        if lk_tab.fn_ctx[f] != 0:
            for i in range(0, lk_tab.fn_nslots(f)):
                s = lk_tab.fn_slot[f] + i
                if lk_tab.slot_weight[s] == weight and is_candidate(lk_tab.slot_class(s), lk_tab.slot_bytes(s)):
                    move_slot(f, i, into)
    for k in range(0, lk_tab.cls_count):
        if lk_tab.cls_reach[k] != 0:
            for p in range(lk_tab.cls_par[k], lk_tab.cls_par[k] + lk_tab.cls_np[k]):
                if lk_tab.cp_weight[p] == weight and is_candidate(lk_tab.cp_info[p] & lk_tab.S_CLASS, lk_tab.cp_size[p]):
                    move_cparam(k, p, into)
    for d in range(0, lk_tab.def_count):
        if var_is_candidate(d, weight):
            move_var(d, into)


# Promotion decides most items without laying the program out again. After a layout L, what
# was accepted since is a list of the copies it went into, each with its context, its size and
# the longest chain through its node in L (`through`). A chain of calls that passes through
# copies x1..xk is no longer than the shortest of their throughs plus the sum of their sizes,
# so the deepest chain of a context is now at most the largest, over the throughs t of the list
# in that context, of t plus the sizes of the copies whose through is t or more (bound). An item
# fits if zero page fits with it at that bound; it does not fit if it does not fit with L
# alone, since more in zero page never makes a chain need less. Only an item between the two
# needs a new layout, after which it is judged exactly. The choices are those of laying out
# after every item accepted.
CAND = WEIGHT_COUNT + WEIGHTS       # while promote() works: the copies of the item judged, then
LIST = CAND + lk_tab.MAX_CONTEXTS   # the list, two words a copy (through; size, and context << 12),
                                    # throughs largest first
MAX_TAKEN = 128                     # a list longer than this takes a layout instead: judging an item
                                    # reads it, and longer lists saved no layouts on the corpus
taken = 0
taken_vars = 0                      # bytes of variables accepted since L
cand_count = 0
cand_size = 0


def lay_out():
    """Lay zero page out again with the choices made so far."""
    global taken, taken_vars
    layout_zp()
    taken = 0
    taken_vars = 0


def through(n):
    """The longest chain through node n's set in the last layout."""
    return lk_tab.add16(lk_tab.work[LAY_END + n], lk_tab.work[LAY_DOWN + n])


def deepest(ctx, extra):
    """At most how deep context ctx is now, with the item judged if `extra` is a node of its."""
    deep = ctx_depth[ctx]
    total = 0
    used = extra == lk_tab.NONE
    for i in range(0, taken):
        t = lk_tab.work[LIST + 2 * i]
        if not used and through(extra) >= t:
            total = lk_tab.add16(total, cand_size)
            used = True
            if lk_tab.add16(through(extra), total) > deep:
                deep = lk_tab.add16(through(extra), total)
        if (lk_tab.work[LIST + 2 * i + 1] >> 12) == ctx:
            total = lk_tab.add16(total, lk_tab.work[LIST + 2 * i + 1] & 0xFFF)
            if lk_tab.add16(t, total) > deep:
                deep = lk_tab.add16(t, total)
    if not used:
        total = lk_tab.add16(total, cand_size)
        if lk_tab.add16(through(extra), total) > deep:
            deep = lk_tab.add16(through(extra), total)
    return deep


def bound(var_size):
    """At most how much zero page the program needs now with the item judged in it."""
    used = lk_tab.add16(lk_tab.add16(zp_used, taken_vars), var_size)
    for ctx in range(0, lk_tab.ctx_count):
        extra = lk_tab.NONE
        for c in range(0, cand_count):
            if lk_tab.ctx_of(lk_tab.work[CAND + c]) == ctx:
                extra = lk_tab.work[CAND + c]
        used = lk_tab.add16(used, deepest(ctx, extra) - ctx_depth[ctx])
    return used


def take():
    """Add the copies of the item judged to the list. False if there is no room."""
    global taken
    if taken + cand_count > MAX_TAKEN:
        return False
    for c in range(0, cand_count):
        n = lk_tab.work[CAND + c]
        t = through(n)
        i = taken
        while i > 0 and lk_tab.work[LIST + 2 * (i - 1)] < t:
            lk_tab.work[LIST + 2 * i] = lk_tab.work[LIST + 2 * (i - 1)]
            lk_tab.work[LIST + 2 * i + 1] = lk_tab.work[LIST + 2 * (i - 1) + 1]
            i -= 1
        lk_tab.work[LIST + 2 * i] = t
        lk_tab.work[LIST + 2 * i + 1] = cand_size | (lk_tab.ctx_of(n) << 12)
        taken += 1
    return True


def least():
    """At least how much more zero page the item judged needs: as much as with L alone."""
    need = 0
    for c in range(0, cand_count):
        need = lk_tab.add16(need, growth(lk_tab.work[CAND + c], cand_size))
    return need


def judge(var_size):
    """True if the item judged, its copies at CAND, or a variable of var_size bytes, is
    taken into zero page."""
    global taken_vars
    lk_tab.overflow = False
    if not fits(lk_tab.add16(least(), var_size)):
        return False
    lk_tab.overflow = False
    most = bound(var_size)
    if lk_tab.overflow or most > zp_cap or not take():
        lay_out()
        lk_tab.overflow = False
        if not fits(lk_tab.add16(least(), var_size)):
            return False
        take()
    taken_vars += var_size
    return True


def try_slot(f, i):
    global cand_count, cand_size
    cand_count = 0
    cand_size = lk_tab.slot_bytes(lk_tab.fn_slot[f] + i)
    for ctx in range(0, lk_tab.ctx_count):
        if lk_tab.has_copy(f, ctx) and lk_tab.in_frame(f, i, lk_tab.in_block(f, ctx)):
            lk_tab.work[CAND + cand_count] = lk_tab.copy_node(f, ctx)
            cand_count += 1
    if judge(0):
        move_slot(f, i, True)


def try_cparam(k, p):
    global cand_count, cand_size
    cand_count = 1
    lk_tab.work[CAND + 0] = lk_tab.cls_node[k]
    cand_size = lk_tab.cp_size[p]
    if judge(0):
        move_cparam(k, p, True)


def try_var(d):
    global cand_count
    cand_count = 0
    if judge(lk_tab.def_b[d]):
        move_var(d, True)


def try_slots(weight):
    for f in range(0, lk_tab.fn_count):
        if lk_tab.fn_ctx[f] != 0:
            for i in range(0, lk_tab.fn_nslots(f)):
                s = lk_tab.fn_slot[f] + i
                if lk_tab.slot_weight[s] == weight and is_candidate(lk_tab.slot_class(s), lk_tab.slot_bytes(s)):
                    try_slot(f, i)


def try_cparams(weight):
    for k in range(0, lk_tab.cls_count):
        if lk_tab.cls_reach[k] != 0:
            for p in range(lk_tab.cls_par[k], lk_tab.cls_par[k] + lk_tab.cls_np[k]):
                if lk_tab.cp_weight[p] == weight and is_candidate(lk_tab.cp_info[p] & lk_tab.S_CLASS, lk_tab.cp_size[p]):
                    try_cparam(k, p)


def try_vars(weight):
    for d in range(0, lk_tab.def_count):
        if var_is_candidate(d, weight):
            try_var(d)


def move_all(into):
    """Move every candidate of weight 1 or more into zero page, or out again."""
    for weight in range(1, WEIGHTS):
        if lk_tab.work[WEIGHT_COUNT + weight] != 0:
            move_weight(weight, into)


def promote():
    """Move class 1 items into zero page, heaviest first, while the deepest chain still fits.

    An item of weight 0 gains nothing from zero page and is left where it is.

    First every candidate is tried at once. More in zero page never makes a chain need less, so
    if they all fit, each would have been taken one at a time too: one layout does the work.
    Otherwise each is judged in turn (judge)."""
    move_all(True)
    if layout_zp():
        return
    move_all(False)
    lay_out()
    for weight in range(WEIGHTS - 1, 0, -1):
        if lk_tab.work[WEIGHT_COUNT + weight] != 0:
            try_slots(weight)
            try_cparams(weight)
            try_vars(weight)


# ---- addresses

def assign_zp():
    """Turn the zero page layout into addresses: variables, then each context."""
    pos = lk_envf.zp_lo
    for d in range(0, lk_tab.def_count):
        if lk_tab.is_kept_var(d) and (lk_tab.def_f[d] & lk_tab.D_ZP) != 0:
            lk_tab.def_a[d] = pos
            pos += lk_tab.def_b[d]
    for ctx in range(0, lk_tab.ctx_count):
        ctx_bottom[ctx] = pos
        pos += ctx_depth[ctx]
    for n in range(0, lk_tab.node_count):
        if lk_tab.is_node(n):
            lk_tab.set_zbase(n, (ctx_bottom[lk_tab.ctx_of(n)] + lk_tab.work[LAY_BASE + n]) & 0xFF)


def place_vars():
    """Give main memory to the variables that are not in zero page. Returns where they end."""
    pos = 0
    for d in range(0, lk_tab.def_count):
        if lk_tab.is_kept_var(d) and (lk_tab.def_f[d] & lk_tab.D_ZP) == 0:
            pos = main_item(pos, lk_tab.def_b[d])
            lk_tab.def_a[d] = (lk_envf.data_lo + pos) & 0xFFFF
            pos = lk_tab.add16(pos, lk_tab.def_b[d])
    return pos


def assign_main():
    """Lay out main memory: the variables, then each context."""
    lk_tab.overflow = False
    pos = place_vars()
    for ctx in range(0, lk_tab.ctx_count):
        ctx_bottom[ctx] = pos
        pos = layout(POOL_MAIN, ctx)
        ctx_depth[ctx] = pos - ctx_bottom[ctx]
    room = lk_envf.data_hi - lk_envf.data_lo + 1
    if lk_tab.overflow or pos > room:
        fail_full(lk_err.E_DATA_FULL, pos - room, lk_tab.overflow)
    for n in range(0, lk_tab.node_count):
        if lk_tab.is_node(n):
            lk_tab.work[lk_tab.W_MBASE + n] = (lk_envf.data_lo + lk_tab.work[LAY_BASE + n]) & 0xFFFF


def assign_cparams():
    """The address of every parameter of every live class block."""
    for k in range(0, lk_tab.cls_count):
        if lk_tab.cls_reach[k] != 0:
            zp_at = lk_tab.zbase_of(lk_tab.cls_node[k])
            main_at = lk_tab.mbase_of(lk_tab.cls_node[k])
            for p in range(lk_tab.cls_par[k], lk_tab.cls_par[k] + lk_tab.cls_np[k]):
                if (lk_tab.cp_info[p] & lk_tab.S_ZP) != 0:
                    lk_tab.cp_addr[p] = zp_at
                    zp_at += lk_tab.cp_size[p]
                else:
                    if straddles(main_at, lk_tab.cp_size[p]):
                        main_at += 1
                    lk_tab.cp_addr[p] = main_at
                    main_at = (main_at + lk_tab.cp_size[p]) & 0xFFFF


def slot_addr(n, i):
    """The address of slot i of the function copy that is node n."""
    f = lk_tab.own_of(n)
    blocked = lk_tab.in_block(f, lk_tab.ctx_of(n))
    if not lk_tab.in_frame(f, i, blocked):
        k, live = lk_tab.member_class(f)
        return lk_tab.cp_addr[lk_tab.cls_par[k] + i]
    zp_at = lk_tab.zbase_of(n)
    main_at = lk_tab.mbase_of(n)
    addr = 0
    for j in range(0, i + 1):
        if lk_tab.in_frame(f, j, blocked):
            s = lk_tab.fn_slot[f] + j
            if lk_tab.slot_in_zp(s):
                addr = zp_at
                zp_at += lk_tab.slot_bytes(s)
            else:
                if straddles(main_at, lk_tab.slot_bytes(s)):
                    main_at += 1
                addr = main_at
                main_at = (main_at + lk_tab.slot_bytes(s)) & 0xFFFF
    return addr


def allocate():
    """Choose what goes in zero page and give everything its address."""
    global zp_cap
    zp_cap = lk_envf.zp_hi - lk_envf.zp_lo + 1
    start_choices()
    for n in range(0, lk_tab.node_count):
        if lk_tab.is_node(n):
            lk_tab.work[lk_tab.W_ZSIZE + n] = zp_size(n)
    if not layout_zp():
        fail_zp()
    promote()
    # promote() only moved in what it had worked out would fit. Make sure of it.
    if not layout_zp():
        fail_zp()
    assign_zp()
    assign_main()
    assign_cparams()
