"""Sizes and placement: where every function copy and constant goes in the `code` range.

The object files are read once more, in order. A function's final size is its written size, the
length of its CODE record, less one byte for each of its kind 5 fix-ups whose address is in zero
page (lk_fix.count_shrinks), which is known now that every slot and variable has its address.
The code itself is not read. Code and the constant data kept are placed in object order, then record
order, after the linker's own start-up code; the copies of a function follow one another.
"""
import lk_boot
import lk_envf
import lk_err
import lk_fix
import lk_name
import lk_rec
import lk_sym
import lk_tab

code_used = 0                       # bytes of the code range given out so far
code_wrapped = False                # more than 16 bits can count were asked for


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


def place_copies(f, written):
    """Size and place every copy of function f, whose code as written is `written` bytes and
    whose fix-ups lk_fix has just counted."""
    for ctx in range(0, lk_tab.ctx_count):
        if lk_tab.has_copy(f, ctx):
            n = lk_tab.copy_node(f, ctx)
            lk_tab.work[lk_tab.W_ADDR + n] = take(written - lk_fix.shrink_count[ctx])


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
            place_copies(f, written)
            kept = False
        elif kind == lk_rec.R_DATA:
            s = lk_name.global_sym(obj, lk_rec.get_word())
            d = lk_sym.row_of(s)
            if lk_tab.is_kept_def(d):
                lk_tab.def_a[d] = take(lk_tab.def_b[d])
        kind = lk_rec.advance()
    lk_rec.close()


def place():
    """Place the start-up code, then everything in the object files."""
    global code_used, code_wrapped
    code_used = 0
    code_wrapped = False
    take(lk_boot.plan())
    for obj in range(0, lk_name.object_count):
        place_object(obj)
    room = lk_envf.code_hi - lk_envf.code_lo + 1
    if code_wrapped or code_used > room:
        lk_err.begin(lk_err.E_CODE_FULL)
        lk_err.over(code_used - room, code_wrapped)
        lk_err.finish()
