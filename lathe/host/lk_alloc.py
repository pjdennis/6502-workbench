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
class parameters of the whole program are then taken heaviest weight first and each is moved
into zero page if the deepest chain of calls still fits with it there; one that does not fit is
left in main memory and the next is tried. All candidates of one weight are first tried
together, because one layout is then enough for the lot; only if they do not all fit are they
taken one by one, in the order slots, class parameters, variables.

A slot's choice holds for every copy of its function. A member's parameter slots are not in
the frame of the copy in its class's context: they are the class block.

Main memory on an NMOS 6502: no two-byte item is placed across a page boundary, because
`JMP (pointer)` reads the wrong high byte there and any pointer may be called through.
"""
import lk_envf
import lk_err
import lk_graph
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
CHAIN = 4 * lk_tab.MAX_NODES        # the nodes of a call chain, for an error message

ctx_bottom = [0] * lk_tab.MAX_CONTEXTS  # where a context's storage starts in the pool
ctx_depth = [0] * lk_tab.MAX_CONTEXTS   # how much its deepest chain needs

zp_cap = 0                          # bytes of zero page the linker may use
zp_vars = 0                         # of which module-level variables have this many
zp_used = 0                         # and variables and all contexts this many

WEIGHTS = 256
weight_count = [0] * WEIGHTS        # how many class 1 candidates have each weight



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
    f = lk_tab.node_own[n]
    blocked = lk_tab.in_block(f, lk_tab.node_ctx[n])
    for i in range(0, lk_tab.fn_nslots[f]):
        s = lk_tab.fn_slot[f] + i
        if (lk_tab.slot_info[s] & lk_tab.S_ZP) != 0 and lk_tab.in_frame(f, i, blocked):
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
    f = lk_tab.node_own[n]
    blocked = lk_tab.in_block(f, lk_tab.node_ctx[n])
    for i in range(0, lk_tab.fn_nslots[f]):
        s = lk_tab.fn_slot[f] + i
        if (lk_tab.slot_info[s] & lk_tab.S_ZP) == 0 and lk_tab.in_frame(f, i, blocked):
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
        e = lk_graph.next_edge(e)


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
        if lk_tab.node_ctx[n] == ctx:
            lk_tab.work[LAY_BASE + n] = ctx_bottom[ctx]
    limit = lk_graph.order_count
    while limit > 0:
        first = limit - 1
        scc = lk_tab.work[lk_tab.W_SCC + lk_tab.work[lk_tab.W_ORDER + first]]
        while first > 0 and lk_tab.work[lk_tab.W_SCC + lk_tab.work[lk_tab.W_ORDER + first - 1]] == scc:
            first -= 1
        if lk_tab.node_ctx[lk_tab.work[lk_tab.W_ORDER + first]] == ctx:
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
                e = lk_graph.next_edge(e)
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
    for n in range(0, lk_tab.node_count):
        if lk_tab.node_ctx[n] == ctx and lk_tab.work[LAY_END + n] - ctx_bottom[ctx] == ctx_depth[ctx]:
            return n, True
    return 0, False


def caller_below(n):
    """A caller of node n's set whose own set ends where n's starts, and whether there is one."""
    start = lk_tab.work[LAY_END + n] - lk_tab.work[LAY_SIZE + n]
    for caller in range(0, lk_tab.node_count):
        if lk_tab.node_ctx[caller] == lk_tab.node_ctx[n] and lk_tab.work[LAY_END + caller] == start \
                and lk_tab.work[lk_tab.W_SCC + caller] != lk_tab.work[lk_tab.W_SCC + n]:
            e = lk_graph.first_edge(caller)
            while e != 0:
                target, applies = lk_graph.edge_node(caller, e)
                if applies and lk_tab.work[lk_tab.W_SCC + target] == lk_tab.work[lk_tab.W_SCC + n]:
                    return caller, True
                e = lk_graph.next_edge(e)
    return 0, False


def fail_full(error, amount, wrapped):
    """Report a pool that is too small, by how much, and the call chain that needs the most of
    it."""
    count = 0
    n, more = deepest_node(deepest_context())
    while more:
        for member in range(0, lk_tab.node_count):
            if lk_tab.work[lk_tab.W_SCC + member] == lk_tab.work[lk_tab.W_SCC + n]:
                lk_tab.work[CHAIN + count] = member
                count += 1
        n, more = caller_below(n)
    lk_err.begin(error)
    lk_err.over(amount, wrapped)
    for i in range(count - 1, -1, -1):
        if i == count - 1:
            lk_err.colon()
        else:
            lk_err.arrow()
        lk_tab.error_node(lk_tab.work[CHAIN + i])
    lk_err.finish()


def fail_zp():
    fail_full(lk_err.E_ZP_FULL, zp_used - zp_cap, lk_tab.overflow)


# ---- choosing what goes in zero page

def is_candidate(info, size):
    """True for a class 1 item small enough to be worth trying."""
    return (info & lk_tab.S_CLASS) == 1 and size <= zp_cap


def must_fit(size, sym):
    """A class 0 item larger than all of zero page can be reported at once."""
    if size > zp_cap:
        lk_err.begin(lk_err.E_ZP_FULL)
        lk_err.over(size - zp_cap, False)
        lk_err.colon()
        lk_sym.error_name(sym)
        lk_err.finish()


def start_choices():
    """Class 0 goes in zero page. Count the class 1 candidates by weight."""
    global zp_vars
    for w in range(0, WEIGHTS):
        weight_count[w] = 0
    for f in range(0, lk_tab.fn_count):
        if lk_tab.fn_ctx[f] != 0:
            for s in range(lk_tab.fn_slot[f], lk_tab.fn_slot[f] + lk_tab.fn_nslots[f]):
                if (lk_tab.slot_info[s] & lk_tab.S_CLASS) == 0:
                    must_fit(lk_tab.slot_bytes(s), lk_tab.fn_sym[f])
                    lk_tab.slot_info[s] |= lk_tab.S_ZP
                elif is_candidate(lk_tab.slot_info[s], lk_tab.slot_bytes(s)):
                    weight_count[lk_tab.slot_weight[s]] += 1
    for k in range(0, lk_tab.cls_count):
        if lk_tab.cls_reach[k] != 0:
            for p in range(lk_tab.cls_par[k], lk_tab.cls_par[k] + lk_tab.cls_np[k]):
                if (lk_tab.cp_info[p] & lk_tab.S_CLASS) == 0:
                    must_fit(lk_tab.cp_size[p], lk_tab.cls_sym[k])
                    lk_tab.cp_info[p] |= lk_tab.S_ZP
                elif is_candidate(lk_tab.cp_info[p], lk_tab.cp_size[p]):
                    weight_count[lk_tab.cp_weight[p]] += 1
    zp_vars = 0
    for d in range(0, lk_tab.def_count):
        s = lk_tab.def_sym[d]
        if lk_sym.is_kept_var(s):
            if (lk_sym.sym_f[s] & lk_sym.V_CLASS) == 0:
                must_fit(lk_sym.sym_b[s], s)
                lk_sym.sym_f[s] |= lk_sym.V_ZP
                zp_vars += lk_sym.sym_b[s]
            elif (lk_sym.sym_f[s] & lk_sym.V_CLASS) == 1 and lk_sym.sym_b[s] <= zp_cap:
                weight_count[lk_sym.sym_w[s]] += 1


def growth(n, size):
    """How much deeper node n's context gets if its node needs `size` more bytes."""
    top = lk_tab.add16(lk_tab.add16(lk_tab.work[LAY_END + n], size), lk_tab.work[LAY_DOWN + n])
    if top > ctx_depth[lk_tab.node_ctx[n]]:
        return top - ctx_depth[lk_tab.node_ctx[n]]
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
    lk_tab.slot_info[s] ^= lk_tab.S_ZP
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


def move_var(s, into):
    global zp_vars
    lk_sym.sym_f[s] ^= lk_sym.V_ZP
    if into:
        zp_vars += lk_sym.sym_b[s]
    else:
        zp_vars -= lk_sym.sym_b[s]


def var_is_candidate(s, weight):
    return lk_sym.is_kept_var(s) and (lk_sym.sym_f[s] & lk_sym.V_CLASS) == 1 \
        and lk_sym.sym_w[s] == weight and lk_sym.sym_b[s] <= zp_cap


def move_weight(weight, into):
    """Move every candidate of this weight into zero page, or all of them out again."""
    for f in range(0, lk_tab.fn_count):
        if lk_tab.fn_ctx[f] != 0:
            for i in range(0, lk_tab.fn_nslots[f]):
                s = lk_tab.fn_slot[f] + i
                if lk_tab.slot_weight[s] == weight and is_candidate(lk_tab.slot_info[s], lk_tab.slot_bytes(s)):
                    move_slot(f, i, into)
    for k in range(0, lk_tab.cls_count):
        if lk_tab.cls_reach[k] != 0:
            for p in range(lk_tab.cls_par[k], lk_tab.cls_par[k] + lk_tab.cls_np[k]):
                if lk_tab.cp_weight[p] == weight and is_candidate(lk_tab.cp_info[p], lk_tab.cp_size[p]):
                    move_cparam(k, p, into)
    for d in range(0, lk_tab.def_count):
        if var_is_candidate(lk_tab.def_sym[d], weight):
            move_var(lk_tab.def_sym[d], into)


def try_slots(weight):
    for f in range(0, lk_tab.fn_count):
        if lk_tab.fn_ctx[f] != 0:
            for i in range(0, lk_tab.fn_nslots[f]):
                s = lk_tab.fn_slot[f] + i
                if lk_tab.slot_weight[s] == weight and is_candidate(lk_tab.slot_info[s], lk_tab.slot_bytes(s)):
                    lk_tab.overflow = False
                    if fits(slot_growth(f, i)):
                        move_slot(f, i, True)
                        layout_zp()


def try_cparams(weight):
    for k in range(0, lk_tab.cls_count):
        if lk_tab.cls_reach[k] != 0:
            for p in range(lk_tab.cls_par[k], lk_tab.cls_par[k] + lk_tab.cls_np[k]):
                if lk_tab.cp_weight[p] == weight and is_candidate(lk_tab.cp_info[p], lk_tab.cp_size[p]):
                    lk_tab.overflow = False
                    if fits(growth(lk_tab.cls_node[k], lk_tab.cp_size[p])):
                        move_cparam(k, p, True)
                        layout_zp()


def try_vars(weight):
    for d in range(0, lk_tab.def_count):
        s = lk_tab.def_sym[d]
        if var_is_candidate(s, weight):
            lk_tab.overflow = False
            if fits(lk_sym.sym_b[s]):
                move_var(s, True)
                layout_zp()


def move_all(into):
    """Move every candidate of weight 1 or more into zero page, or out again."""
    for weight in range(1, WEIGHTS):
        if weight_count[weight] != 0:
            move_weight(weight, into)


def promote():
    """Move class 1 items into zero page, heaviest first, while the deepest chain still fits.

    An item of weight 0 gains nothing from zero page and is left where it is. Trying the
    candidates of a weight together saves layouts only when there are several: a lone one is
    tried by itself at once, which needs a layout only if it fits.

    First every candidate is tried at once. More in zero page never makes a chain need less, so
    if they all fit, each would have been taken one at a time too: one layout does the work."""
    move_all(True)
    if layout_zp():
        return
    move_all(False)
    layout_zp()
    for weight in range(WEIGHTS - 1, 0, -1):
        if weight_count[weight] > 1:
            move_weight(weight, True)
            if not layout_zp():
                move_weight(weight, False)
                layout_zp()
                try_slots(weight)
                try_cparams(weight)
                try_vars(weight)
        elif weight_count[weight] == 1:
            try_slots(weight)
            try_cparams(weight)
            try_vars(weight)


# ---- addresses

def assign_zp():
    """Turn the zero page layout into addresses: variables, then each context."""
    pos = lk_envf.zp_lo
    for d in range(0, lk_tab.def_count):
        s = lk_tab.def_sym[d]
        if lk_sym.is_kept_var(s) and (lk_sym.sym_f[s] & lk_sym.V_ZP) != 0:
            lk_sym.sym_a[s] = pos
            pos += lk_sym.sym_b[s]
    for ctx in range(0, lk_tab.ctx_count):
        ctx_bottom[ctx] = pos
        pos += ctx_depth[ctx]
    for n in range(0, lk_tab.node_count):
        lk_tab.node_zbase[n] = (ctx_bottom[lk_tab.node_ctx[n]] + lk_tab.work[LAY_BASE + n]) & 0xFF


def place_vars():
    """Give main memory to the variables that are not in zero page. Returns where they end."""
    pos = 0
    for d in range(0, lk_tab.def_count):
        s = lk_tab.def_sym[d]
        if lk_sym.is_kept_var(s) and (lk_sym.sym_f[s] & lk_sym.V_ZP) == 0:
            pos = main_item(pos, lk_sym.sym_b[s])
            lk_sym.sym_a[s] = (lk_envf.data_lo + pos) & 0xFFFF
            pos = lk_tab.add16(pos, lk_sym.sym_b[s])
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
        lk_tab.node_mbase[n] = (lk_envf.data_lo + lk_tab.work[LAY_BASE + n]) & 0xFFFF


def assign_cparams():
    """The address of every parameter of every live class block."""
    for k in range(0, lk_tab.cls_count):
        if lk_tab.cls_reach[k] != 0:
            zp_at = lk_tab.node_zbase[lk_tab.cls_node[k]]
            main_at = lk_tab.node_mbase[lk_tab.cls_node[k]]
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
    f = lk_tab.node_own[n]
    blocked = lk_tab.in_block(f, lk_tab.node_ctx[n])
    if not lk_tab.in_frame(f, i, blocked):
        k, live = lk_tab.member_class(f)
        return lk_tab.cp_addr[lk_tab.cls_par[k] + i]
    zp_at = lk_tab.node_zbase[n]
    main_at = lk_tab.node_mbase[n]
    addr = 0
    for j in range(0, i + 1):
        if lk_tab.in_frame(f, j, blocked):
            s = lk_tab.fn_slot[f] + j
            if (lk_tab.slot_info[s] & lk_tab.S_ZP) != 0:
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
