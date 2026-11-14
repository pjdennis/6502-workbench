"""Pass 2: write the image and the map.

The object files are read in order once more, each by one stream. A kept function's fix-ups,
which come before its code, are held (lk_fix); then its code is written an instruction at a
time as it is read: fix-ups applied, instructions shrunk, and branches and labels corrected for
the bytes removed between them and their targets. A function with copies for several contexts
is written once for each, its code read again for each copy after the first. Constant data is
written with the fix-ups held from the DFIX record before it.

The map's slot lines are written on the way, because slot names are only in the files.
"""
import lk_boot
import lk_err
import lk_fix
import lk_map
import lk_name
import lk_op
import lk_out
import lk_rec
import lk_scan
import lk_sym
import lk_tab


def value(n, op):
    """The address the fix-up at lk_fix's cursor stands for in the copy that is node n, addend
    included. op is the opcode of the instruction it is in."""
    i = lk_fix.cursor
    ctx = lk_tab.ctx_of(n)
    kind = lk_tab.work[lk_fix.FX_KIND + i]
    add = lk_tab.work[lk_fix.FX_ADD + i]
    own = lk_tab.work[lk_fix.FX_SLOT + i] == 0xFF and lk_tab.work[lk_fix.FX_SYM + i] == lk_fix.cur_sym
    # A fix-up to the function's own symbol is a label: an offset into the code as written.
    # The one exception is `@f` inside f, which like any `@f` may mean another context's copy.
    if own and (lk_fix.is_word(kind) or add != 0):
        moved = add - lk_fix.removed_before(add, ctx)
        return (lk_tab.work[lk_tab.W_ADDR + n] + moved) & 0xFFFF
    is_call = kind == lk_fix.K_WORD and (op == lk_op.OP_JSR or op == lk_op.OP_JMP)
    return (lk_fix.target(ctx, lk_tab.work[lk_fix.FX_SYM + i], lk_tab.work[lk_fix.FX_SLOT + i], is_call) + add) & 0xFFFF


def branch(next_at, displacement, ctx):
    """The displacement of a branch once the bytes between it and its target are removed.

    next_at is the written offset of the instruction after the branch."""
    dest = next_at + displacement
    if displacement >= 0x80:
        dest -= 0x100
    dest &= 0xFFFF
    moved = (dest - lk_fix.removed_before(dest, ctx)) - (next_at - lk_fix.removed_before(next_at, ctx))
    return moved & 0xFF


def instruction(obj, n, pos):
    """Write the instruction at written offset `pos` of node n. Returns the next offset."""
    ctx = lk_tab.ctx_of(n)
    op = lk_rec.get_byte()
    size = lk_op.length(op)
    if lk_rec.left() < size - 1:
        lk_rec.damaged()
    more = lk_fix.more()
    i = lk_fix.cursor
    if more and lk_tab.work[lk_fix.FX_AT + i] <= pos:
        lk_fix.bad()
    if more and lk_tab.work[lk_fix.FX_AT + i] == pos + 1 and lk_fix.is_word(lk_tab.work[lk_fix.FX_KIND + i]):
        # Kind 5 exactly where the instruction has a zero page form (object-format.md).
        if size != 3 or lk_op.can_shrink(op) != (lk_tab.work[lk_fix.FX_KIND + i] == lk_fix.K_SHRINK):
            lk_fix.bad()
        lk_rec.get_word()
        address = value(n, op)
        if lk_fix.shrinks(i, ctx):
            lk_out.put(lk_op.zp_opcode(op))
            lk_out.put(address & 0xFF)
        else:
            lk_out.put(op)
            lk_out.put_word(address)
        lk_fix.next_fix()
        return pos + size
    lk_out.put(op)
    for k in range(1, size):
        b = lk_rec.get_byte()
        if lk_fix.more() and lk_tab.work[lk_fix.FX_AT + lk_fix.cursor] == pos + k:
            if lk_fix.is_word(lk_tab.work[lk_fix.FX_KIND + lk_fix.cursor]):
                lk_fix.bad()
            b = lk_fix.part(value(n, op), lk_tab.work[lk_fix.FX_KIND + lk_fix.cursor])
            lk_fix.next_fix()
        elif k == size - 1 and lk_op.is_branch(op, lk_scan.cpu_of(obj)):
            b = branch(pos + size, b, ctx)
        lk_out.put(b)
    return pos + size


def emit_copy(obj, n):
    """MAIN is at the function's CODE record: write the copy that is node n."""
    lk_out.seek(lk_tab.work[lk_tab.W_ADDR + n])
    before = lk_out.written
    planned = lk_rec.left() - lk_fix.shrunk(lk_tab.ctx_of(n))
    lk_fix.rewind()
    pos = 0
    while lk_rec.left() > 0:
        pos = instruction(obj, n, pos)
    if lk_fix.more():
        lk_fix.bad()
    if ((lk_out.written - before) & 0xFFFF) != planned:
        lk_name.fail(lk_err.E_SIZE, lk_fix.cur_sym)


def emit_copies(obj, f):
    """MAIN is at the CODE record of kept function f: write each of its copies."""
    code_record = lk_rec.recno()
    first = True
    for ctx in range(0, lk_tab.ctx_count):
        if lk_tab.has_copy(f, ctx):
            if not first:
                lk_rec.goto(obj, code_record)
            emit_copy(obj, lk_tab.copy_node(f, ctx))
            first = False


def emit_data(obj):
    """MAIN is at a DATA record: write the constant with the fix-ups held, if it is kept."""
    s = lk_name.global_sym(obj, lk_rec.get_word())
    if not lk_tab.is_kept_def(lk_sym.row_of(s)):
        lk_fix.drop()
        return
    lk_fix.begin_data(s)
    lk_out.seek(lk_tab.def_a[lk_sym.row_of(s)])
    pos = 0
    while lk_rec.left() > 0:
        b = lk_rec.get_byte()
        i = lk_fix.cursor
        if lk_fix.more() and lk_tab.work[lk_fix.FX_AT + i] < pos:
            lk_fix.bad()
        if lk_fix.more() and lk_tab.work[lk_fix.FX_AT + i] == pos:
            address = lk_fix.target(lk_fix.NO_CONTEXT, lk_tab.work[lk_fix.FX_SYM + i], lk_tab.work[lk_fix.FX_SLOT + i], False)
            address = (address + lk_tab.work[lk_fix.FX_ADD + i]) & 0xFFFF
            if lk_tab.work[lk_fix.FX_KIND + i] == lk_fix.K_WORD:
                if lk_rec.left() == 0:
                    lk_fix.bad()
                lk_rec.get_byte()
                lk_out.put_word(address)
                pos += 2
            elif lk_tab.work[lk_fix.FX_KIND + i] == lk_fix.K_SHRINK:
                lk_fix.bad()            # only an instruction can shrink
            else:
                lk_out.put(lk_fix.part(address, lk_tab.work[lk_fix.FX_KIND + i]))
                pos += 1
            lk_fix.next_fix()
        else:
            lk_out.put(b)
            pos += 1
    if lk_fix.more():
        lk_fix.bad()
    lk_fix.drop()


def slot_line(f, number, i):
    """MAIN is at SLOT record i of kept function f, whose symbol has this number: write its
    map lines."""
    lk_rec.get_word()
    lk_rec.get_word()
    lk_rec.get_byte()
    lk_name.keep_at(2 * lk_tab.W_SNAME)
    lk_map.slot(f, number, i, 2 * lk_tab.W_SNAME)


def emit_object(obj):
    """Write what object file obj has kept. The names of its kept functions that have slots are
    held as the file is read, for the S lines (lk_map)."""
    some = lk_map.mark_functions(obj, True, True)
    if some:
        lk_map.hold_begin(obj, lk_map.W_HELD, lk_tab.W_OWN)
    lk_rec.open_object(obj)
    f = 0
    number = 0
    symbols = 0
    slots = 0
    kept = False
    kind = lk_rec.advance()
    while kind != lk_rec.R_END:
        if kind == lk_rec.R_SYM and some:
            lk_rec.get_byte()
            lk_map.hold(obj, symbols)
            symbols += 1
        elif kind == lk_rec.R_FUNC:
            number = lk_rec.get_word()
            f = lk_sym.row_of(lk_name.global_sym(obj, number))
            kept = lk_tab.fn_ctx[f] != 0
            slots = 0
            lk_fix.drop()
            if kept:
                lk_fix.begin(f)
        elif kind == lk_rec.R_SLOT and kept:
            slot_line(f, number, slots)
            slots += 1
        elif kind == lk_rec.R_FIX and kept:
            lk_fix.hold(obj, True)
        elif kind == lk_rec.R_CODE and kept:
            emit_copies(obj, f)
        elif kind == lk_rec.R_ENDF:
            kept = False
        elif kind == lk_rec.R_DFIX:
            lk_fix.hold(obj, False)
        elif kind == lk_rec.R_DATA:
            emit_data(obj)
        kind = lk_rec.advance()
    lk_rec.close()
    if some:
        lk_map.mark_functions(obj, False, True)


def write(main_fn):
    """Write the image and the map file. main_fn is the program's main function."""
    lk_map.open_map()
    lk_map.functions()
    lk_map.symbols(lk_sym.CONSTANT, 68)
    lk_map.symbols(lk_sym.VARIABLE, 86)
    lk_out.open_image()
    lk_boot.write(main_fn)
    for obj in range(0, lk_name.object_count):
        emit_object(obj)
    lk_out.close_image(lk_boot.start_addr)
    lk_map.cparams()
    lk_map.close_map()
