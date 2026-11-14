"""Code in a window: which bank or overlay each function and constant is in, the stubs, and the
table the far-call module's start() reads (configurations.md, section 5).

A module's code is placed by the environment file's `place` entry (lk_scan.obj_bank); every
function of the module, and every copy of it for a context, goes there. Everything else is fixed.

A stub is six bytes of fixed code, `JSR FARCALL.call` / `.byte VALUE` / `.word f-1`, through
which code outside f's bank or overlay calls f, and which `@f` means wherever it is taken. A
function in a window has stubs (lk_tab.F_STUB) if some kept code outside its bank calls it, if
kept code or constant data takes its address (F_ADDR), or if the start-up code calls it (main, a
module's `$init`); then each of its copies has one. The stubs follow `$start` and `$init`, in the
order the copies are placed in, so a stub's place is worked out from the function table, with a
count per object file (obj_stub), and no table of stubs is kept. The table for start() follows
them:

    $banks      .word WINDOW, .byte N, then N times .byte VALUE, .word NAME
    $overlays   .word WINDOW, .byte N, then N times, overlay 1 first, .word NAME

and after it each file's name, zero-terminated: the banks of the window that have a file, in the
order of their entries; or every overlay.
"""
import lk_envf
import lk_err
import lk_name
import lk_scan
import lk_sym
import lk_tab

STUB_SIZE = 6

obj_stub = [0] * (lk_name.MAX_OBJECTS + 1)  # the number of the first stub of each object's functions
stub_count = 0
stub_base = 0                       # where the stubs start: lk_boot places them
table_count = 0                     # banks or overlays in the table


def bank_def(d):
    """The bank + 1 that variable or constant d goes in, or 0 for fixed memory: that of its
    module's code, if no fix-up outside that bank names it and none takes its address
    (lk_graph.note_named). A variable goes in a bank, never an overlay, which is loaded again
    from its file."""
    if not lk_envf.placed() or (lk_tab.def_f[d] & lk_tab.D_FIXED) != 0:
        return 0
    if (lk_tab.def_f[d] & lk_tab.D_CONST) == 0 and lk_envf.is_overlay():
        return 0
    return lk_scan.def_bank(d)


def def_dest(d):
    """The file constant data d is written to, or where variable d is: 0 the image or fixed
    memory, or its bank + 1. Only once it is placed."""
    if lk_envf.placed() and lk_envf.in_window(lk_tab.def_a[d]):
        return lk_scan.def_bank(d)
    return 0


def copies(f):
    """The number of copies of function f: one per context that reaches it."""
    count = 0
    for ctx in range(0, lk_tab.ctx_count):
        if lk_tab.has_copy(f, ctx):
            count += 1
    return count


def has_stub(f):
    return (lk_tab.fn_flags[f] & lk_tab.F_STUB) != 0


def needs_stub(f):
    """Function f, if it is in a window, needs stubs."""
    if lk_tab.fn_ctx[f] != 0 and lk_scan.fn_bank(f) != 0:
        lk_tab.fn_flags[f] |= lk_tab.F_STUB


def check_interrupts():
    """An interrupt function is fixed: it is entered from a vector and ends in RTI, so it cannot
    be entered through a stub. What it calls may be in a bank, because rt_bank's routine is
    reentrant, but not in an overlay: the loader is not, and a file is not loaded in an
    interrupt (configurations.md, "Interrupts")."""
    if not lk_envf.placed():
        return
    ctx = 0
    for h in range(0, lk_tab.fn_count):
        if (lk_tab.fn_flags[h] & lk_tab.F_INTERRUPT) != 0:
            ctx += 1
            if lk_scan.fn_bank(h) != 0:
                lk_name.fail(lk_err.E_IRQ_PLACED, lk_tab.fn_ref(h))
            if lk_envf.is_overlay():
                for f in range(0, lk_tab.fn_count):
                    if lk_tab.has_copy(f, ctx) and lk_scan.fn_bank(f) != 0:
                        lk_name.fail_in(lk_err.E_IRQ_OVERLAY, lk_tab.fn_ref(h), lk_tab.fn_ref(f))


def mark_stubs(main_fn):
    """Mark the functions that have stubs, and count the stubs of each object file."""
    global stub_count
    stub_count = 0
    if not lk_envf.placed():
        return
    needs_stub(main_fn)
    for f in range(0, lk_tab.fn_count):
        if (lk_tab.fn_flags[f] & (lk_tab.F_ADDR | lk_tab.F_INIT)) != 0:
            needs_stub(f)
        if lk_tab.fn_ctx[f] != 0:
            r = lk_tab.fn_ref(f)
            e = lk_tab.first_call(r)
            while e != 0:
                target = lk_tab.edge_sym(e - 1)
                if lk_scan.crosses(f, target, lk_tab.edge_flag(e - 1)):
                    needs_stub(lk_sym.row_of(target))
                e = lk_tab.next_call(r, e)
    for obj in range(0, lk_name.object_count):
        obj_stub[obj] = stub_count
        for f in range(lk_name.obj_fn[obj], lk_name.obj_fn[obj + 1]):
            if has_stub(f):
                stub_count += copies(f)
    obj_stub[lk_name.object_count] = stub_count


def stub_addr(n):
    """The address of the stub of the function copy that is node n, which has one."""
    f = lk_tab.own_of(n)
    obj = lk_scan.object_of(f)
    i = obj_stub[obj]
    for g in range(lk_name.obj_fn[obj], f):
        if has_stub(g):
            i += copies(g)
    for ctx in range(0, lk_tab.ctx_of(n)):
        if lk_tab.has_copy(f, ctx):
            i += 1
    return (stub_base + STUB_SIZE * i) & 0xFFFF


def in_table(b):
    """True if bank or overlay b is in the table: one of the window code is placed in that has
    a file."""
    return lk_envf.bank_win[b] == lk_envf.window() and lk_envf.bank_file[b] != 0


def table_size():
    """The bytes of the table and its names. Only when lk_envf.placed()."""
    global table_count
    entry = 3
    if lk_envf.is_overlay():
        entry = 2
    size = 3
    table_count = 0
    for b in range(0, lk_envf.bank_count):
        if in_table(b):
            table_count += 1
            size += entry + lk_envf.text[lk_envf.bank_file[b] - 1] + 1
    return size


def table_bank(i):
    """The bank or overlay of entry i of the table, from 0: the banks with a file in the order
    of their entries; the overlays by their number."""
    if lk_envf.is_overlay():
        return lk_envf.find_bank(lk_envf.window(), i + 1)
    for b in range(0, lk_envf.bank_count):
        if in_table(b):
            if i == 0:
                return b
            i -= 1
    return 0

