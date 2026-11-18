"""Fix-ups: what address a fix-up stands for, and which instructions of a function shrink.

An instruction shrinks if its fix-up is of kind 5 and the address with the addend is below $100
(object-format.md, "The size of an instruction"), so a function's fix-ups alone say how much it
shrinks. Pass 1 counts, for each context, the fix-ups of a function that shrink (count_shrinks).
Pass 2 holds the fix-ups of one function or one piece of constant data (hold), which come
before its code or data in the file, and applies them as the bytes go by (lk_emit). A copy of a
function for another context has other slot addresses, so each held fix-up carries one bit per
context in which its instruction shrinks.

The fix-ups of one function are the only thing about its code the linker ever holds, and it
holds at most MAX_FIXES of them, a run: a function with more has its FIX record read again for
each run after the first, from the place the code has reached and back (next_fix), and what its
code loses before an offset that the run held does not cover is counted from the record itself
(removed). Constant data is held whole: the compiler writes at most 256 addresses in a table
(out.MAX_TABLE_FIXES), and every build holds more.
"""
import lk_alloc
import lk_envf
import lk_err
import lk_name
import lk_rec
import lk_scan
import lk_sym
import lk_tab
import lk_win

MAX_FIXES = lk_tab.MAX_FIXES
NO_CONTEXT = 0xFF                   # the context of a fix-up in constant data

# Fix-up kinds.
K_WORD = 1
K_LOW = 2
K_HIGH = 3
K_ZP = 4
K_SHRINK = 5
K_BANK = 6                          # one byte: the register value of a region's bank (lk_win)
K_REACH_LOW = 7                     # K_LOW and K_HIGH of an address formed only to reach a part of
K_REACH_HIGH = 8                    # what it names, in code (lk_graph.note_named)

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

# A function of more fix-ups than a run holds (long_fix): where its FIX record is, the record's
# entry that the run's first is, and what the entries before the run lose. Set by hold.
long_fix = False
fix_obj = 0                         # the object file being written
fix_recno = 0                       # the number of the FIX record in it
fix_total = 0                       # the entries of the record
run_base = 0                        # the entry of the record that held entry 0 is
run_lost = [0] * lk_tab.MAX_CONTEXTS    # bytes each copy loses before the run
here = 0                            # while the record is read again (away): the record the
rest = 0                            # code was read in, and the bytes of it left

shrink_count = [0] * lk_tab.MAX_CONTEXTS    # pass 1: bytes each copy of cur_fn loses

mapped = 0                          # pass 2: a bit for each bank a kind 6 fix-up of cur_fn has
                                    # mapped so far, in the order of its code (bank_value)
cur_fn = 0                          # the function whose records are being read
cur_sym = 0                         # its symbol, or that of the constant data being written


def bad():
    """A fix-up of the current function or constant makes no sense."""
    lk_name.fail(lk_err.E_FIXUP, cur_sym)


def begin(f):
    """Start on function f, which has no fix-up that shrinks until count_shrinks finds some, and
    has mapped no bank."""
    global cur_fn, cur_sym, mapped
    cur_fn = f
    mapped = 0
    cur_sym = lk_tab.fn_ref(f)
    for ctx in range(0, lk_tab.ctx_count):
        shrink_count[ctx] = 0


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
    e_sym = lk_name.global_sym(obj, lk_rec.get_word())
    e_slot = lk_rec.get_byte()
    e_add = lk_rec.get_word()


def count_before(obj, pos):
    """MAIN is at cur_fn's FIX record: count, for each context, its fix-ups before written
    offset `pos` that shrink (shrink_count)."""
    for ctx in range(0, lk_tab.ctx_count):
        shrink_count[ctx] = 0
    while lk_rec.left() > 0:
        read_entry(obj)
        if e_at >= pos:
            return
        if e_kind == K_SHRINK:
            bits = zp_contexts(e_sym, e_slot, e_add)
            for ctx in range(0, lk_tab.ctx_count):
                if (bits & (1 << ctx)) != 0:
                    shrink_count[ctx] += 1


def count_shrinks(obj):
    """Pass 1. MAIN is at cur_fn's FIX record: count, for each context, its fix-ups that
    shrink."""
    count_before(obj, 0xFFFF)


def hold(obj, in_code):
    """Pass 2. MAIN is at a FIX record of cur_fn, or at a DFIX record: hold its entries, or the
    first run of them.

    Whether they make sense is checked as they are applied."""
    global fix_count, cursor, long_fix, fix_obj, fix_recno, fix_total
    fix_count = 0
    cursor = 0
    fix_obj = obj
    fix_recno = lk_rec.recno()
    take_run(obj, in_code)
    fix_total = fix_count + (lk_rec.left() >> 3)
    long_fix = lk_rec.left() > 0
    if long_fix and not in_code:
        lk_err.fail(lk_err.E_FIXES)
    first_run()


def put(column, v):
    """Column `column` of the fix-up held next is v."""
    lk_tab.set_wk(column + fix_count, v)


def take_run(obj, in_code):
    """Hold the entries of the record MAIN is in from where it is, as many as a run holds."""
    global fix_count
    while lk_rec.left() > 0 and fix_count < MAX_FIXES:
        read_entry(obj)
        put(FX_AT, e_at)
        put(FX_KIND, e_kind)
        put(FX_SYM, e_sym)
        put(FX_SLOT, e_slot)
        put(FX_ADD, e_add)
        put(FX_ZP, 0)
        if in_code and e_kind == K_SHRINK:
            put(FX_ZP, zp_contexts(e_sym, e_slot, e_add))
        fix_count += 1


def first_run():
    """Nothing is lost before the first run."""
    global run_base
    run_base = 0
    for ctx in range(0, lk_tab.ctx_count):
        run_lost[ctx] = 0


def away():
    """Read the FIX record again, from its start, leaving the code where it is (back)."""
    global here, rest
    here = lk_rec.recno()
    rest = lk_rec.left()
    lk_rec.goto(fix_obj, fix_recno)


def back():
    """Back to where the code was being read."""
    lk_rec.goto(fix_obj, here)
    while lk_rec.left() > rest:
        lk_rec.get_byte()


def from_record(pos, ctx):
    """The bytes the copy for context ctx loses before written offset `pos`, counted from the FIX
    record, read again."""
    away()
    count_before(fix_obj, pos)
    back()
    return shrink_count[ctx]


def load_run(base):
    """Hold the run that starts at entry `base` of the FIX record, read again."""
    global fix_count, cursor, run_base
    away()
    for i in range(0, 8 * base):
        lk_rec.get_byte()
    fix_count = 0
    cursor = 0
    take_run(fix_obj, True)
    run_base = base
    back()


def drop():
    """No fix-ups are held."""
    global fix_count, cursor
    fix_count = 0
    cursor = 0


def more():
    """True while some held fix-up is still to be applied."""
    return cursor < fix_count


def held(column):
    """Column `column` of the held fix-up at the cursor."""
    return lk_tab.wk(column + cursor)


def next_run():
    """The run held is applied: hold the next one, read again from the record."""
    for ctx in range(0, lk_tab.ctx_count):
        run_lost[ctx] += shrunk(ctx)
    load_run(run_base + fix_count)


def next_fix():
    """The fix-up at the cursor is applied: go on to the next, in the next run if it is not held.
    (The order of two fix-ups on either side of the end of a run is checked by the instructions,
    which find a fix-up behind them bad: lk_emit.)"""
    global cursor
    if held(FX_KIND) < K_WORD or held(FX_KIND) > K_REACH_HIGH:
        bad()
    cursor += 1
    if cursor == fix_count and run_base + fix_count < fix_total:
        next_run()
    elif cursor < fix_count:
        # Fix-ups are sorted by offset, and do not overlap.
        after = lk_tab.wk(FX_AT + cursor - 1) + 1
        if is_word(lk_tab.wk(FX_KIND + cursor - 1)):
            after += 1
        if held(FX_AT) < after:
            bad()


def rewind():
    """Apply the held fix-ups again, to the next copy of the function: from the first run."""
    global cursor
    cursor = 0
    if run_base != 0:
        load_run(0)
        first_run()


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
    return lk_tab.first_node(f), True


def target(ctx, sym, slot, is_call):
    """The address a fix-up stands for, before the addend, seen from context ctx.

    A function whose address something kept takes is kept itself (lk_graph), so what is left
    with address 0 is storage nothing kept can use: a slot of a dropped function, or a
    parameter of a class that no kept function calls through."""
    kind = lk_sym.kind_of(sym)
    if not lk_sym.is_defined(sym):
        lk_name.fail(lk_err.E_UNDEFINED, sym)
    if kind == lk_sym.VARIABLE or kind == lk_sym.CONSTANT:
        if slot != 0xFF:
            bad()
        return lk_tab.def_a[lk_sym.row_of(sym)]
    if kind == lk_sym.CLASS:
        k = lk_tab.class_of(lk_sym.row_of(sym))
        if slot >= lk_tab.cls_np[k]:
            bad()
        if lk_tab.cls_reach[k] == 0:
            return 0
        return lk_tab.cp_addr[lk_tab.cls_par[k] + slot]
    f = lk_sym.row_of(sym)
    if slot == 0xFF:
        if is_call:
            # A call goes to the callee's copy in the caller's own context: through its stub
            # if the callee is in a window and the caller is not in the same bank or overlay.
            if ctx == NO_CONTEXT or not lk_tab.has_copy(f, ctx):
                lk_name.fail_in(lk_err.E_NOT_LINKED, sym, cur_sym)
            n = lk_tab.copy_node(f, ctx)
            if lk_win.has_stub(f) and lk_scan.fn_bank(f) != lk_scan.fn_bank(cur_fn):
                return lk_win.stub_addr(n)
            return lk_tab.wk(lk_tab.W_ADDR + n)
        n, kept = address_copy(f)
        if not kept:
            return 0
        # `@f` of a function in a window is its stub, wherever it is taken.
        if lk_win.has_stub(f):
            return lk_win.stub_addr(n)
        return lk_tab.wk(lk_tab.W_ADDR + n)
    if slot >= lk_tab.fn_nslots(f):
        bad()
    if ctx != NO_CONTEXT and lk_tab.has_copy(f, ctx):
        return lk_alloc.slot_addr(lk_tab.copy_node(f, ctx), slot)
    n, kept = address_copy(f)
    if not kept:
        return 0
    return lk_alloc.slot_addr(n, slot)


def bank_of(s):
    """The bank + 1 of the region variable or constant data s is in, 0 for fixed memory, or 0xFF
    if s is not a variable or constant data that is defined."""
    k = lk_sym.kind_of(s)
    if (k != lk_sym.VARIABLE and k != lk_sym.CONSTANT) or not lk_sym.is_defined(s):
        return 0xFF
    return lk_scan.region_of(lk_sym.row_of(s))


def bank_value(s):
    """What a kind 6 fix-up naming symbol s stands for: the register value of the bank of the
    region s is in, or 0 if the region is in fixed memory. The bank is mapped from here on."""
    global mapped
    r = bank_of(s)
    if r == 0xFF:
        return 0x100                    # not a variable or constant data: a bad fix-up
    if r == 0:
        return 0
    mapped |= 1 << (r - 1)
    return lk_envf.bank_value[r - 1]


def check_mapped(s):
    """Code of cur_fn names symbol s: if s is a variable or constant data of a region in a bank,
    a kind 6 fix-up of cur_fn must have mapped that bank before (a `with` block's `LDA #bank`).
    Code compiled with the region in fixed memory (-fREGION) has no block, and would read the
    window as whatever is there."""
    r = bank_of(s)
    if r != 0 and r != 0xFF and (mapped & (1 << (r - 1))) == 0:
        lk_name.fail_in(lk_err.E_UNMAPPED, s, cur_sym)


def part(value, kind):
    """The byte a one-byte fix-up of this kind puts in the code."""
    if kind == K_HIGH or kind == K_REACH_HIGH:
        return value >> 8
    if kind == K_ZP and value > 0xFF:
        # Only a class 0 slot is always in zero page; the compiler must not ask this of others.
        lk_name.fail_in(lk_err.E_NOT_ZP, held(FX_SYM), cur_sym)
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
        if ((lk_tab.def_a[lk_sym.row_of(sym)] + addend) & 0xFFFF) < 0x100:
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
    return (lk_tab.wk(FX_ZP + i) & (1 << ctx)) != 0


def shrunk(ctx):
    """Bytes the copy for context ctx loses, from the fix-ups held."""
    count = 0
    for i in range(0, fix_count):
        if shrinks(i, ctx):
            count += 1
    return count


def lost(ctx):
    """Bytes the copy for context ctx loses, from all of the function's fix-ups."""
    if long_fix:
        return from_record(0xFFFF, ctx)
    return shrunk(ctx)


def removed(pos, ctx):
    """How many bytes are removed before written offset `pos` in the copy for context ctx: from
    the run held if it covers `pos` (every entry before the run is before it, every one after the
    run after it), else from the FIX record."""
    if long_fix and (run_base != 0 and pos < lk_tab.wk(FX_AT)
                     or pos > lk_tab.wk(FX_AT + fix_count - 1)):
        return from_record(pos, ctx)
    return run_lost[ctx] + removed_before(pos, ctx)


def removed_before(pos, ctx):
    """How many bytes are removed before written offset `pos` in the copy for context ctx.

    A fix-up is at the offset of an operand's low byte; the byte removed is the one after it."""
    count = 0
    for i in range(0, fix_count):
        if lk_tab.wk(FX_AT + i) >= pos:
            return count
        if shrinks(i, ctx):
            count += 1
    return count
