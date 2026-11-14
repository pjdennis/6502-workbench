"""Pass 2: write the image and the map.

The object files are read in order once more. For each kept function the stream that reads the
file finds its sites (lk_fix); then, for each copy, a second stream reads the fix-ups while a
third reads the code, and the copy is written an instruction at a time: fix-ups applied,
instructions shrunk, and branches and labels corrected for the bytes removed between them and
their targets. Constant data is copied with its fix-ups, which follow it in the file.

The map's slot lines are written on the way, because slot names are only in the files.
"""
import lk_boot
import lk_err
import lk_fix
import lk_map
import lk_op
import lk_out
import lk_rec
import lk_scan
import lk_sym
import lk_tab


def value(n, op):
    """The address the current fix-up of the copy that is node n stands for, addend included.

    op is the opcode of the instruction it is in."""
    ctx = lk_tab.node_ctx[n]
    own = lk_fix.fx_slot == 0xFF and lk_fix.fx_sym == lk_fix.cur_sym
    # A fix-up to the function's own symbol is a label: an offset into the code as written.
    # The one exception is `@f` inside f, which like any `@f` may mean another context's copy.
    if own and (lk_fix.fx_kind == 1 or lk_fix.fx_add != 0):
        moved = lk_fix.fx_add - lk_fix.removed_before(lk_fix.fx_add, ctx)
        return (lk_tab.node_addr[n] + moved) & 0xFFFF
    is_call = lk_fix.fx_kind == 1 and (op == lk_op.OP_JSR or op == lk_op.OP_JMP)
    return (lk_fix.target(ctx, lk_fix.fx_sym, lk_fix.fx_slot, is_call) + lk_fix.fx_add) & 0xFFFF


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
    ctx = lk_tab.node_ctx[n]
    cpu = lk_scan.obj_cpu[obj]
    op = lk_rec.get_byte(lk_rec.CODES)
    size = lk_op.length(op)
    if lk_rec.left(lk_rec.CODES) < size - 1:
        lk_rec.damaged(lk_rec.CODES)
    if lk_fix.fx_more and lk_fix.fx_at <= pos:
        lk_fix.bad()
    if lk_fix.fx_more and lk_fix.fx_at == pos + 1 and lk_fix.fx_kind == 1:
        if size != 3:
            lk_fix.bad()
        lk_rec.get_word(lk_rec.CODES)
        address = value(n, op)
        if lk_fix.is_site(pos + 1, ctx):
            form, shrinks = lk_op.zp_opcode(op, cpu)
            lk_out.put(form)
            lk_out.put(address & 0xFF)
        else:
            lk_out.put(op)
            lk_out.put_word(address)
        lk_fix.next_entry(lk_rec.FIXES, obj)
        return pos + size
    lk_out.put(op)
    for i in range(1, size):
        b = lk_rec.get_byte(lk_rec.CODES)
        if lk_fix.fx_more and lk_fix.fx_at == pos + i:
            if lk_fix.fx_kind == 1:
                lk_fix.bad()
            b = lk_fix.part(value(n, op), lk_fix.fx_kind)
            lk_fix.next_entry(lk_rec.FIXES, obj)
        elif i == size - 1 and lk_op.is_branch(op, cpu):
            b = branch(pos + size, b, ctx)
        lk_out.put(b)
    return pos + size


def emit_copy(obj, n):
    """Write the function copy that is node n; lk_fix holds its function's sites."""
    lk_out.seek(lk_tab.node_addr[n])
    before = lk_out.written
    lk_fix.no_entries()
    if lk_fix.fix_record != 0:
        lk_rec.goto(lk_rec.FIXES, obj, lk_fix.fix_record)
        lk_fix.first_entry(lk_rec.FIXES, obj)
    if lk_fix.code_record != 0:
        lk_rec.goto(lk_rec.CODES, obj, lk_fix.code_record)
        pos = 0
        while lk_rec.left(lk_rec.CODES) > 0:
            pos = instruction(obj, n, pos)
    if lk_fix.fx_more:
        lk_fix.bad()
    if ((lk_out.written - before) & 0xFFFF) != lk_tab.node_len[n]:
        lk_sym.fail(lk_err.E_SIZE, lk_fix.cur_sym)


def emit_copies(obj, f):
    for ctx in range(0, lk_tab.ctx_count):
        if lk_tab.has_copy(f, ctx):
            emit_copy(obj, lk_tab.copy_node(f, ctx))


def emit_data(obj):
    """MAIN is at a DATA record: write the constant with its fix-ups, if it is kept."""
    s = lk_scan.global_sym(obj, lk_rec.get_word(lk_rec.MAIN))
    if not lk_sym.is_kept(s):
        return
    lk_fix.begin_data(s)
    lk_out.seek(lk_sym.sym_a[s])
    lk_fix.no_entries()
    if lk_rec.goto(lk_rec.FIXES, obj, lk_rec.recno(lk_rec.MAIN) + 1) == lk_rec.R_DFIX:
        lk_fix.first_entry(lk_rec.FIXES, obj)
    pos = 0
    while lk_rec.left(lk_rec.MAIN) > 0:
        b = lk_rec.get_byte(lk_rec.MAIN)
        if lk_fix.fx_more and lk_fix.fx_at < pos:
            lk_fix.bad()
        if lk_fix.fx_more and lk_fix.fx_at == pos:
            address = lk_fix.target(lk_fix.NO_CONTEXT, lk_fix.fx_sym, lk_fix.fx_slot, False)
            address = (address + lk_fix.fx_add) & 0xFFFF
            if lk_fix.fx_kind == 1:
                if lk_rec.left(lk_rec.MAIN) == 0:
                    lk_fix.bad()
                lk_rec.get_byte(lk_rec.MAIN)
                lk_out.put_word(address)
                pos += 2
            else:
                lk_out.put(lk_fix.part(address, lk_fix.fx_kind))
                pos += 1
            lk_fix.next_entry(lk_rec.FIXES, obj)
        else:
            lk_out.put(b)
            pos += 1
    if lk_fix.fx_more:
        lk_fix.bad()


def slot_line(f, number):
    """MAIN is at a SLOT record of kept function f: write its map lines."""
    lk_rec.get_word(lk_rec.MAIN)
    lk_rec.get_word(lk_rec.MAIN)
    lk_rec.get_byte(lk_rec.MAIN)
    lk_scan.read_name()
    lk_map.slot(f, number)


def emit_object(obj):
    lk_rec.open_object(lk_rec.MAIN, obj)
    f = 0
    slots = 0
    kept = False
    kind = lk_rec.advance(lk_rec.MAIN)
    while kind != lk_rec.R_END:
        if kind == lk_rec.R_FUNC:
            f = lk_sym.sym_a[lk_scan.global_sym(obj, lk_rec.get_word(lk_rec.MAIN))]
            kept = lk_tab.fn_ctx[f] != 0
            slots = 0
            if kept:
                lk_fix.begin(f)
        elif kind == lk_rec.R_SLOT and kept:
            slot_line(f, slots)
            slots += 1
        elif kind == lk_rec.R_FIX and kept:
            lk_fix.collect(obj)
        elif kind == lk_rec.R_CODE and kept:
            lk_fix.confirm(lk_scan.obj_cpu[obj])
        elif kind == lk_rec.R_ENDF and kept:
            emit_copies(obj, f)
            kept = False
        elif kind == lk_rec.R_DATA:
            emit_data(obj)
        kind = lk_rec.advance(lk_rec.MAIN)


def write(main_fn):
    """Write the image and the map file. main_fn is the program's main function."""
    lk_map.open_map()
    lk_map.functions()
    lk_map.symbols(lk_sym.CONSTANT, 68)
    lk_map.symbols(lk_sym.VARIABLE, 86)
    lk_out.open_image()
    lk_boot.write(main_fn)
    for obj in range(0, lk_scan.object_count):
        emit_object(obj)
    for s in range(0, lk_rec.MAX_STREAMS):
        lk_rec.close(s)
    lk_out.close_image(lk_boot.start_addr)
    lk_map.cparams()
    lk_map.close_map()
