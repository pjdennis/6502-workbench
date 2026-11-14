"""Fix-ups: what address a fix-up stands for, and which instructions of a function shrink.

An instruction shrinks if its fix-up is of kind 5 and the address with the addend is below $100
(object-format.md, "The size of an instruction"), so a function's fix-ups alone say how much it
shrinks. Pass 1 counts, for each context, the fix-ups of a function that shrink (count_shrinks).
Pass 2 holds the fix-ups of one function or one piece of constant data (hold), which come
before its code or data in the file, and applies them as the bytes go by (lk_emit). A copy of a
function for another context has other slot addresses, so each held fix-up carries one bit per
context in which its instruction shrinks.

The fix-ups of one function are the only thing about its code the linker ever holds.
"""
import lk_alloc
import lk_err
import lk_rec
import lk_scan
import lk_sym
import lk_tab

MAX_FIXES = lk_tab.MAX_FIXES
NO_CONTEXT = 0xFF                   # the context of a fix-up in constant data

# Fix-up kinds.
K_WORD = 1
K_LOW = 2
K_HIGH = 3
K_ZP = 4
K_SHRINK = 5

# The entry read last.
e_at = 0
e_kind = 0
e_sym = 0
e_slot = 0
e_add = 0

# The fix-ups held, in the order of the file, which is the order of offset: columns of
# lk_tab.work, which nothing else uses while code is written.
fix_count = 0
FX_AT = 0                           # offset in the code as written, or in the data
FX_KIND = MAX_FIXES
FX_SYM = 2 * MAX_FIXES
FX_SLOT = 3 * MAX_FIXES
FX_ADD = 4 * MAX_FIXES
FX_ZP = 5 * MAX_FIXES               # a bit per context in which the instruction shrinks
cursor = 0                          # the next fix-up to apply

shrink_count = [0] * lk_tab.MAX_CONTEXTS    # pass 1: bytes each copy of cur_fn loses

cur_fn = 0                          # the function whose records are being read
cur_sym = 0                         # its symbol, or that of the constant data being written


def bad():
    """A fix-up of the current function or constant makes no sense."""
    lk_sym.fail(lk_err.E_FIXUP, cur_sym)


def begin(f):
    """Start on function f."""
    global cur_fn, cur_sym
    cur_fn = f
    cur_sym = lk_tab.fn_sym[f]


def begin_data(sym):
    """Start on the constant data that is symbol sym."""
    global cur_sym
    cur_sym = sym


def is_word(kind):
    """True for the kinds that fill two bytes."""
    return kind == K_WORD or kind == K_SHRINK


def read_entry(obj):
    """Read the next fix-up entry of the record MAIN is in, of object file obj."""
    global e_at, e_kind, e_sym, e_slot, e_add
    e_at = lk_rec.get_word()
    e_kind = lk_rec.get_byte()
    e_sym = lk_scan.global_sym(obj, lk_rec.get_word())
    e_slot = lk_rec.get_byte()
    e_add = lk_rec.get_word()


def count_shrinks(obj):
    """Pass 1. MAIN is at cur_fn's FIX record: count, for each context, its fix-ups that
    shrink."""
    for ctx in range(0, lk_tab.ctx_count):
        shrink_count[ctx] = 0
    while lk_rec.left() > 0:
        read_entry(obj)
        if e_kind == K_SHRINK:
            bits = zp_contexts(e_sym, e_slot, e_add)
            for ctx in range(0, lk_tab.ctx_count):
                if (bits & (1 << ctx)) != 0:
                    shrink_count[ctx] += 1


def hold(obj, in_code):
    """Pass 2. MAIN is at a FIX record of cur_fn, or at a DFIX record: hold its entries.

    Whether they make sense is checked as they are applied."""
    global fix_count, cursor
    fix_count = 0
    cursor = 0
    while lk_rec.left() > 0:
        if fix_count == MAX_FIXES:
            if in_code:
                lk_sym.fail(lk_err.E_FIXES, cur_sym)
            lk_err.fail(lk_err.E_FIXES)
        read_entry(obj)
        lk_tab.work[FX_AT + fix_count] = e_at
        lk_tab.work[FX_KIND + fix_count] = e_kind
        lk_tab.work[FX_SYM + fix_count] = e_sym
        lk_tab.work[FX_SLOT + fix_count] = e_slot
        lk_tab.work[FX_ADD + fix_count] = e_add
        lk_tab.work[FX_ZP + fix_count] = 0
        if in_code and e_kind == K_SHRINK:
            lk_tab.work[FX_ZP + fix_count] = zp_contexts(e_sym, e_slot, e_add)
        fix_count += 1


def drop():
    """No fix-ups are held."""
    global fix_count, cursor
    fix_count = 0
    cursor = 0


def more():
    """True while some held fix-up is still to be applied."""
    return cursor < fix_count


def next_fix():
    """The fix-up at the cursor is applied: go on to the next."""
    global cursor
    if lk_tab.work[FX_KIND + cursor] < K_WORD or lk_tab.work[FX_KIND + cursor] > K_SHRINK:
        bad()
    cursor += 1
    if cursor < fix_count:
        # Fix-ups are sorted by offset, and do not overlap.
        after = lk_tab.work[FX_AT + cursor - 1] + 1
        if is_word(lk_tab.work[FX_KIND + cursor - 1]):
            after += 1
        if lk_tab.work[FX_AT + cursor] < after:
            bad()


def rewind():
    """Apply the held fix-ups again, to the next copy of the function."""
    global cursor
    cursor = 0


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
    if not lk_sym.is_defined(sym):
        lk_sym.fail(lk_err.E_UNDEFINED, sym)
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
            return lk_tab.work[lk_tab.W_ADDR + lk_tab.copy_node(f, ctx)]
        n, kept = address_copy(f)
        if not kept:
            return 0
        return lk_tab.work[lk_tab.W_ADDR + n]
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
    if kind == K_HIGH:
        return value >> 8
    if kind == K_ZP and value > 0xFF:
        # Only a class 0 slot is always in zero page; the compiler must not ask this of others.
        lk_sym.fail_in(lk_err.E_NOT_ZP, lk_tab.work[FX_SYM + cursor], cur_sym)
    return value & 0xFF


# ---- what shrinks

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


def shrinks(i, ctx):
    """True if the instruction of held fix-up i shrinks in the copy for context ctx."""
    return (lk_tab.work[FX_ZP + i] & (1 << ctx)) != 0


def removed_before(pos, ctx):
    """How many bytes are removed before written offset `pos` in the copy for context ctx.

    A fix-up is at the offset of an operand's low byte; the byte removed is the one after it."""
    count = 0
    for i in range(0, fix_count):
        if lk_tab.work[FX_AT + i] >= pos:
            return count
        if shrinks(i, ctx):
            count += 1
    return count
