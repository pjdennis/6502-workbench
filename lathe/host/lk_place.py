"""Sizes and placement: where every function copy and constant goes in the `code` range.

The object files are read once more, in order. A function's final size is its written size less
one byte for each instruction that shrinks (lk_fix), which is known now that every slot and
variable has its address. Code and constant data are placed in object order, then record order,
after the linker's own start-up code; the copies of a function follow one another.
"""
import lk_boot
import lk_envf
import lk_err
import lk_fix
import lk_rec
import lk_scan
import lk_sym
import lk_tab

code_used = 0                       # bytes of the code range given out so far


def take(size):
    """Give out the next `size` bytes of the code range. Returns their address."""
    global code_used
    if size > lk_envf.code_hi - lk_envf.code_lo + 1 - code_used:
        lk_err.fail(lk_err.E_CODE_FULL)
    addr = lk_envf.code_lo + code_used
    code_used += size
    return addr


def place_copies(f):
    """Size and place every copy of function f, whose sites lk_fix has just found."""
    for ctx in range(0, lk_tab.ctx_count):
        if lk_tab.has_copy(f, ctx):
            n = lk_tab.copy_node(f, ctx)
            lk_tab.node_len[n] = lk_fix.written - lk_fix.shrunk(ctx)
            lk_tab.node_addr[n] = take(lk_tab.node_len[n])


def place_object(obj):
    lk_rec.open_object(lk_rec.MAIN, obj)
    f = 0
    kept = False
    kind = lk_rec.advance(lk_rec.MAIN)
    while kind != lk_rec.R_END:
        if kind == lk_rec.R_FUNC:
            f = lk_sym.sym_a[lk_scan.global_sym(obj, lk_rec.get_word(lk_rec.MAIN))]
            kept = lk_tab.fn_ctx[f] != 0
            if kept:
                lk_fix.begin(f)
        elif kind == lk_rec.R_FIX and kept:
            lk_fix.collect(obj)
        elif kind == lk_rec.R_CODE and kept:
            lk_fix.confirm(lk_scan.obj_cpu[obj])
        elif kind == lk_rec.R_ENDF and kept:
            place_copies(f)
            kept = False
        elif kind == lk_rec.R_DATA:
            s = lk_scan.global_sym(obj, lk_rec.get_word(lk_rec.MAIN))
            lk_sym.sym_a[s] = take(lk_sym.sym_b[s])
        kind = lk_rec.advance(lk_rec.MAIN)
    lk_rec.close(lk_rec.MAIN)


def place():
    """Place the start-up code, then everything in the object files."""
    global code_used
    code_used = 0
    take(lk_boot.plan())
    for obj in range(0, lk_scan.object_count):
        place_object(obj)
