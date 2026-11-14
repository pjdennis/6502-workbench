"""Fix-ups: what address a fix-up stands for, and which instructions of a function shrink.

An instruction shrinks if its operand is a two-byte fix-up, its opcode has a zero page form,
and the address with the addend is below $100 (object-format.md, "The size of an instruction").
A function's FIX record comes before its CODE record, so finding its sites takes two steps on
the stream that reads the file in order: collect() notes the two-byte fix-ups whose address is
in zero page, and confirm() keeps those whose opcode can shrink. A copy of a function for
another context has other slot addresses, so each site carries one bit per context.

The list of sites of one function is all that pass 2 needs to correct branches and labels, and
is the only thing about a function's code the linker ever holds.
"""
import lk_alloc
import lk_err
import lk_op
import lk_rec
import lk_scan
import lk_sym
import lk_tab

MAX_SITES = 1024
NO_CONTEXT = 0xFF                   # the context of a fix-up in constant data

site_count = 0
site_at = [0] * MAX_SITES           # written offset of the operand
site_ctx = bytearray(MAX_SITES)     # a bit per context in which the instruction shrinks

cur_fn = 0                          # the function whose records are being read
cur_sym = 0                         # its symbol, or that of the constant data being written
written = 0                         # the size of its code as written
fix_record = 0                      # number of its FIX record in the file, or 0
code_record = 0                     # number of its CODE record, or 0

# The fix-up entry read last.
fx_more = False                     # False once a record's entries are used up
fx_at = 0
fx_kind = 0
fx_sym = 0
fx_slot = 0
fx_add = 0
fx_after = 0                        # entries must be at or after this offset: they are sorted


def bad():
    """A fix-up of the current function or constant makes no sense."""
    lk_sym.fail(lk_err.E_FIXUP, cur_sym)


def begin(f):
    """Start on function f."""
    global cur_fn, cur_sym, site_count, written, fix_record, code_record
    cur_fn = f
    cur_sym = lk_tab.fn_sym[f]
    site_count = 0
    written = 0
    fix_record = 0
    code_record = 0


def begin_data(sym):
    """Start on the constant data that is symbol sym."""
    global cur_sym
    cur_sym = sym


def first_entry(s, obj):
    """Read the first fix-up entry of the record stream s is at."""
    global fx_after
    fx_after = 0
    next_entry(s, obj)


def no_entries():
    """There is no fix-up record to read."""
    global fx_more
    fx_more = False


def next_entry(s, obj):
    """Read the next fix-up entry from stream s, which reads object file obj."""
    global fx_more, fx_at, fx_kind, fx_sym, fx_slot, fx_add, fx_after
    if lk_rec.left(s) == 0:
        fx_more = False
        return
    fx_more = True
    fx_at = lk_rec.get_word(s)
    fx_kind = lk_rec.get_byte(s)
    fx_sym = lk_scan.global_sym(obj, lk_rec.get_word(s))
    fx_slot = lk_rec.get_byte(s)
    fx_add = lk_rec.get_word(s)
    if fx_kind < 1 or fx_kind > 4 or fx_at < fx_after:
        bad()
    fx_after = fx_at + 1
    if fx_kind == 1:
        fx_after = fx_at + 2


# ---- what a fix-up points at

def address_copy(f):
    """The copy of function f that its address means, and whether f was kept at all.

    `@f` is the copy in the context that calls through f's class (code-model.md,
    "Interrupts"); a function in no live class is taken from the lowest context that has it."""
    if lk_tab.fn_ctx[f] == 0:
        return 0, False
    k, live = lk_tab.member_class(f)
    if live and lk_tab.has_copy(f, lk_tab.cls_ctx[k]):
        return lk_tab.copy_node(f, lk_tab.cls_ctx[k]), True
    return lk_tab.fn_node[f], True


def target(ctx, sym, slot, is_call):
    """The address a fix-up stands for, before the addend, seen from context ctx.

    A function whose address something kept takes is kept itself (lk_graph), so what is left
    with address 0 is storage nothing kept can use: a slot of a dropped function, or a
    parameter of a class that no kept function calls through."""
    kind = lk_sym.kind_of(sym)
    if kind == lk_sym.VARIABLE or kind == lk_sym.CONSTANT:
        if slot != 0xFF:
            bad()
        return lk_sym.sym_a[sym]
    if kind == lk_sym.CLASS:
        k = lk_tab.class_of(lk_sym.sym_a[sym])
        if slot >= lk_tab.cls_np[k]:
            bad()
        if lk_tab.cls_reach[k] == 0:
            return 0
        return lk_tab.cp_addr[lk_tab.cls_par[k] + slot]
    f = lk_sym.sym_a[sym]
    if slot == 0xFF:
        if is_call:
            # A call goes to the callee's copy in the caller's own context.
            if ctx == NO_CONTEXT or not lk_tab.has_copy(f, ctx):
                lk_sym.fail_in(lk_err.E_NOT_LINKED, sym, cur_sym)
            return lk_tab.node_addr[lk_tab.copy_node(f, ctx)]
        n, kept = address_copy(f)
        if not kept:
            return 0
        return lk_tab.node_addr[n]
    if slot >= lk_tab.fn_nslots[f]:
        bad()
    if ctx != NO_CONTEXT and lk_tab.has_copy(f, ctx):
        return lk_alloc.slot_addr(lk_tab.copy_node(f, ctx), slot)
    n, kept = address_copy(f)
    if not kept:
        return 0
    return lk_alloc.slot_addr(n, slot)


def part(value, kind):
    """The byte a one-byte fix-up of this kind puts in the code."""
    if kind == 3:
        return value >> 8
    if kind == 4 and value > 0xFF:
        # Only a class 0 slot is always in zero page; the compiler must not ask this of others.
        lk_sym.fail_in(lk_err.E_NOT_ZP, fx_sym, cur_sym)
    return value & 0xFF


# ---- sites

def zp_contexts(sym, slot, addend):
    """The contexts, as bits, in which the address of a fix-up of cur_fn is below $100.

    Code and constant data are never below $100 (lk_envf.check), which is what lets sizes be
    worked out before anything is placed."""
    kind = lk_sym.kind_of(sym)
    if kind == lk_sym.CONSTANT or (kind == lk_sym.FUNCTION and slot == 0xFF):
        return 0
    if kind == lk_sym.VARIABLE:
        if ((lk_sym.sym_a[sym] + addend) & 0xFFFF) < 0x100:
            return lk_tab.fn_ctx[cur_fn]
        return 0
    bits = 0
    for ctx in range(0, lk_tab.ctx_count):
        if lk_tab.has_copy(cur_fn, ctx):
            if ((target(ctx, sym, slot, False) + addend) & 0xFFFF) < 0x100:
                bits |= 1 << ctx
    return bits


def collect(obj):
    """MAIN is at cur_fn's FIX record: note the two-byte fix-ups that land in zero page."""
    global site_count, fix_record
    fix_record = lk_rec.recno(lk_rec.MAIN)
    first_entry(lk_rec.MAIN, obj)
    while fx_more:
        if fx_kind == 1:
            if fx_at == 0:
                bad()               # an operand cannot be the first byte of the code
            bits = zp_contexts(fx_sym, fx_slot, fx_add)
            if bits != 0:
                if site_count == MAX_SITES:
                    lk_sym.fail(lk_err.E_SITES, cur_sym)
                site_at[site_count] = fx_at
                site_ctx[site_count] = bits
                site_count += 1
        next_entry(lk_rec.MAIN, obj)


def confirm(cpu):
    """MAIN is at cur_fn's CODE record: keep the sites whose opcode has a zero page form."""
    global site_count, written, code_record
    code_record = lk_rec.recno(lk_rec.MAIN)
    written = lk_rec.left(lk_rec.MAIN)
    kept = 0
    candidate = 0
    for pos in range(0, written):
        op = lk_rec.get_byte(lk_rec.MAIN)
        if candidate < site_count and site_at[candidate] == pos + 1:
            form, shrinks = lk_op.zp_opcode(op, cpu)
            if shrinks:
                site_at[kept] = site_at[candidate]
                site_ctx[kept] = site_ctx[candidate]
                kept += 1
            candidate += 1
    site_count = kept


def shrunk(ctx):
    """How many bytes cur_fn's copy for context ctx loses."""
    count = 0
    for i in range(0, site_count):
        if (site_ctx[i] & (1 << ctx)) != 0:
            count += 1
    return count


def removed_before(pos, ctx):
    """How many bytes are removed before written offset `pos` in the copy for context ctx.

    A site is the offset of an operand's low byte; the byte removed is the one after it."""
    count = 0
    for i in range(0, site_count):
        if site_at[i] < pos and (site_ctx[i] & (1 << ctx)) != 0:
            count += 1
    return count


def is_site(pos, ctx):
    """True if the operand at written offset `pos` shrinks in the copy for context ctx."""
    for i in range(0, site_count):
        if site_at[i] == pos:
            return (site_ctx[i] & (1 << ctx)) != 0
    return False
