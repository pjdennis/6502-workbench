"""Sizes and placement: where every function copy and constant goes in the `code` range, or
in the bank or overlay its module is placed in.

The object files are read once more, in order. A function's final size is its written size, the
length of its CODE record, less one byte for each of its kind 5 fix-ups whose address is in zero
page (lk_fix.count_shrinks), which is known now that every slot and variable has its address.
The code itself is not read. Code and the constant data kept are placed in object order, then record
order, after the linker's own start-up code; the copies of a function follow one another.

A bank or overlay is filled the same way, from the window's first address. Whether its contents
fit is judged by their size as written, before any instruction shrinks: zero page only makes
code smaller, so the contents placed are never larger than that, and whether a program links
cannot depend on what zero page promotion chose (configurations.md, "Sizes").
"""
import lk_alloc
import lk_boot
import lk_envf
import lk_err
import lk_fix
import lk_name
import lk_rec
import lk_scan
import lk_sym
import lk_tab
import lk_win

code_used = 0                       # bytes of the code range given out so far
code_wrapped = False                # more than 16 bits can count were asked for
bank_used = [0] * lk_envf.MAX_BANKS     # bytes of each bank or overlay given out so far
bank_judged = [0] * lk_envf.MAX_BANKS   # the same as written, before shrinking: the fit check


def take(size):
    """Give out the next `size` bytes of the code range. Returns their address.

    Whether it all fits is checked once everything is placed (place), so that the error can
    say by how much it does not."""
    global code_used, code_wrapped
    addr = (lk_envf.code_lo + code_used) & 0xFFFF
    if size > 0xFFFF - code_used:
        code_wrapped = True
        code_used = 0xFFFF
    else:
        code_used += size
    return addr


def take_bank(b, size, written):
    """Give out the next `size` bytes of bank or overlay b, which are `written` bytes as
    written. Returns their address."""
    addr = (lk_envf.win_lo[lk_envf.bank_win[b]] + bank_used[b]) & 0xFFFF
    bank_used[b] = lk_tab.add16(bank_used[b], size)
    bank_judged[b] = lk_tab.add16(bank_judged[b], written)
    return addr


def place_copies(f, written, bank):
    """Size and place every copy of function f, whose code as written is `written` bytes and
    whose fix-ups lk_fix has just counted, in fixed memory or in bank + 1."""
    for ctx in range(0, lk_tab.ctx_count):
        if lk_tab.has_copy(f, ctx):
            n = lk_tab.copy_node(f, ctx)
            size = written - lk_fix.shrink_count[ctx]
            if bank != 0:
                lk_tab.work[lk_tab.W_ADDR + n] = take_bank(bank - 1, size, written)
            else:
                lk_tab.work[lk_tab.W_ADDR + n] = take(size)


def place_object(obj):
    lk_rec.open_object(obj)
    f = 0
    kept = False
    written = 0
    kind = lk_rec.advance()
    while kind != lk_rec.R_END:
        if kind == lk_rec.R_FUNC:
            f = lk_sym.row_of(lk_name.global_sym(obj, lk_rec.get_word()))
            kept = lk_tab.fn_ctx[f] != 0
            written = 0
            if kept:
                lk_fix.begin(f)
        elif kind == lk_rec.R_FIX and kept:
            lk_fix.count_shrinks(obj)
        elif kind == lk_rec.R_CODE:
            written = lk_rec.left()
        elif kind == lk_rec.R_ENDF and kept:
            place_copies(f, written, lk_scan.obj_bank[obj])
            kept = False
        elif kind == lk_rec.R_DATA:
            s = lk_name.global_sym(obj, lk_rec.get_word())
            d = lk_sym.row_of(s)
            bank = lk_win.bank_def(d)
            if lk_tab.is_kept_def(d) and bank != 0:
                lk_tab.def_a[d] = take_bank(bank - 1, lk_tab.def_b[d], lk_tab.def_b[d])
            elif lk_tab.is_kept_def(d):
                lk_tab.def_a[d] = take(lk_tab.def_b[d])
        kind = lk_rec.advance()
    lk_rec.close()


def place_bank_vars():
    """The variables that go in a bank (lk_win.bank_def), at its top, going down, in the order
    they are defined; a word is not put across a page on an NMOS 6502. For the fit check every
    such variable counts, in zero page or not, with a byte for the page: whether it fits cannot
    depend on what zero page took."""
    for b in range(0, lk_envf.bank_count):
        top = lk_envf.win_hi[lk_envf.bank_win[b]] + 1
        for d in range(0, lk_tab.def_count):
            if lk_tab.is_kept_var(d) and lk_win.bank_def(d) == b + 1:
                size = lk_tab.def_b[d]
                extra = 0
                if lk_alloc.straddles(0xFF, size):
                    extra = 1
                bank_judged[b] = lk_tab.add16(bank_judged[b], size + extra)
                if (lk_tab.def_f[d] & lk_tab.D_ZP) == 0:
                    top = (top - size) & 0xFFFF
                    if lk_alloc.straddles(top, size):
                        top -= 1
                    lk_tab.def_a[d] = top


def place():
    """Place the start-up code, then everything in the object files."""
    global code_used, code_wrapped
    code_used = 0
    code_wrapped = False
    for b in range(0, lk_envf.MAX_BANKS):
        bank_used[b] = 0
        bank_judged[b] = 0
    take(lk_boot.plan())
    lk_tab.overflow = False
    for obj in range(0, lk_name.object_count):
        place_object(obj)
    place_bank_vars()
    room = lk_envf.code_hi - lk_envf.code_lo + 1
    if code_wrapped or code_used > room:
        lk_err.begin(lk_err.E_CODE_FULL)
        lk_err.over(code_used - room, code_wrapped)
        lk_err.finish()
    for b in range(0, lk_envf.bank_count):
        w = lk_envf.bank_win[b]
        room = lk_envf.win_hi[w] - lk_envf.win_lo[w] + 1
        if bank_judged[b] > room:
            lk_err.begin(lk_err.E_BANK_FULL)
            lk_err.colon()
            lk_envf.put_bank(b)
            lk_err.over(bank_judged[b] - room, lk_tab.overflow and bank_judged[b] == 0xFFFF)
            lk_err.finish()
