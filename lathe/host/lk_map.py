"""The map file: one line for everything the linker gave an address (README.md).

    F 0200 0012 hello.main            function, in placement order
    F 0212 0012 hello.main@1          a further copy of it, for context 1
    F 0224 0008 hello.tick 1          a first copy for a context other than 0: its number follows
    D 022C 0006 hello.$1              constant data
    V C000 0001 demo.count            module-level variable
    S 0010 0002 demo.spaces 0 s       slot 0 of demo.spaces, named s
    C 0012 0001 demo.handler 0 code   parameter 0 of a pointer class

A class parameter is named by its CLAS records (object-format.md); one they leave unnamed takes
the name of the parameter of the first function recorded as the class's member, or p0, p1...
for a class without members.
"""
import env
import lk_alloc
import lk_boot
import lk_err
import lk_file
import lk_fix
import lk_name
import lk_rec
import lk_scan
import lk_sym
import lk_tab

START_NAME = b"$start"
INIT_NAME = b"$init"
HEX = b"0123456789ABCDEF"

handle = 0


def open_map():
    global handle
    handle = lk_file.open_out(lk_file.ARG_MAP)


def close_map():
    env.close(handle)


def put(ch):
    env.write(handle, ch)


def hex4(value):
    put(HEX[value >> 12])
    put(HEX[(value >> 8) & 15])
    put(HEX[(value >> 4) & 15])
    put(HEX[value & 15])


def decimal(n):
    """n in decimal; n is below 1000."""
    if n >= 100:
        put(48 + n // 100)
    if n >= 10:
        put(48 + (n // 10) % 10)
    put(48 + n % 10)


def begin(letter, addr, size):
    """Start a line: its kind, address and size."""
    put(letter)
    put(32)
    hex4(addr)
    put(32)
    hex4(size)
    put(32)


# The names of one object file are held in the work area (lk_name's buffer) while it is read:
# from index_at, where the name of each of its symbol numbers is held + 1, or 0; then the names.
# Only the names of symbols marked HELD are held. Before the image is written they take the
# first W_ADDR words; while it is written the words from W_HELD, above the slot name (W_SNAME).
W_HELD = lk_tab.W_SNAME + 128
index_at = 0


def is_held(s):
    """True if the function, variable or constant data s is marked (lk_tab.F_HELD, D_HELD)."""
    kind = lk_sym.kind_of(s)
    if not lk_sym.is_defined(s) or kind == lk_sym.CLASS:
        return False
    if kind == lk_sym.FUNCTION:
        return (lk_tab.fn_flags[lk_sym.row_of(s)] & lk_tab.F_HELD) != 0
    return (lk_tab.def_f[lk_sym.row_of(s)] & lk_tab.D_HELD) != 0


def hold_begin(obj, start, limit):
    """Hold names of object file obj in words start to limit of the work area."""
    global index_at
    index_at = start
    count = lk_name.obj_first[obj + 1] - lk_name.obj_first[obj]
    if start + count > limit:
        lk_err.fail(lk_err.E_NAMES)
    for i in range(0, count):
        lk_tab.work[start + i] = 0
    lk_name.buf_begin(2 * (start + count), 2 * limit)


def hold(obj, number):
    """MAIN is at SYM record `number` of object file obj, after its kind: hold its name if the
    symbol is marked."""
    if is_held(lk_name.global_sym(obj, number)):
        lk_tab.work[index_at + number] = lk_name.buf_keep() + 1


def write_name(number):
    """The name of the symbol the object being read numbers `number`, held earlier."""
    lk_name.write_held(handle, lk_tab.work[index_at + number] - 1)


def mark_functions(obj, on, slotted):
    """Mark the kept functions of object file obj, or only those with slots, or unmark them.
    True if there are some."""
    some = False
    for f in range(lk_name.obj_fn[obj], lk_name.obj_fn[obj + 1]):
        if lk_tab.fn_ctx[f] != 0 and (not slotted or lk_tab.fn_nslots(f) != 0):
            if on:
                lk_tab.fn_flags[f] |= lk_tab.F_HELD
            else:
                lk_tab.fn_flags[f] &= 0xFF ^ lk_tab.F_HELD
            some = True
    return some


def lines(obj, wanted):
    """Read object file obj, holding the names of the symbols marked HELD, and at each FUNC,
    DATA or VAR record (`wanted`) whose symbol is marked write its lines. A function's lines
    are written at its ENDF, when its size is known: the length of its code less what its
    fix-ups shrink (lk_fix.count_shrinks), as lk_place found it."""
    hold_begin(obj, 0, lk_tab.W_ADDR)
    lk_rec.open_object(obj)
    number = 0
    held = False                        # the function being read has lines
    f = 0
    fn_number = 0
    written = 0
    kind = lk_rec.advance()
    while kind != lk_rec.R_END:
        if kind == lk_rec.R_SYM:
            lk_rec.get_byte()
            hold(obj, number)
            number += 1
        elif kind == wanted:
            n = lk_rec.get_word()
            s = lk_name.global_sym(obj, n)
            if is_held(s):
                if kind == lk_rec.R_FUNC:
                    held = True
                    f = lk_sym.row_of(s)
                    fn_number = n
                    written = 0
                    lk_fix.begin(f)
                elif kind == lk_rec.R_DATA:
                    symbol_line(68, s, n)
                else:
                    symbol_line(86, s, n)
        elif kind == lk_rec.R_FIX and held:
            lk_fix.count_shrinks(obj)
        elif kind == lk_rec.R_CODE and held:
            written = lk_rec.left()
        elif kind == lk_rec.R_ENDF and held:
            copy_lines(f, fn_number, written)
            held = False
        kind = lk_rec.advance()
    lk_rec.close()


def copy_name(n, number):
    """The name of the function copy that is node n, whose symbol has this number."""
    write_name(number)
    if lk_tab.is_extra_copy(n):
        put(64)
        decimal(lk_tab.ctx_of(n))


def copy_lines(f, number, written):
    """The F lines of the copies of kept function f, whose symbol has this number and whose
    code as written is `written` bytes."""
    for ctx in range(0, lk_tab.ctx_count):
        if lk_tab.has_copy(f, ctx):
            n = lk_tab.copy_node(f, ctx)
            begin(70, lk_tab.work[lk_tab.W_ADDR + n], written - lk_fix.shrink_count[ctx])
            copy_name(n, number)
            if not lk_tab.is_extra_copy(n) and ctx != 0:
                put(32)
                decimal(ctx)
            put(10)


def symbol_line(letter, s, number):
    begin(letter, lk_tab.def_a[lk_sym.row_of(s)], lk_tab.def_b[lk_sym.row_of(s)])
    write_name(number)
    put(10)


def functions():
    """The F lines, in placement order: the linker's own code, then the copies kept, read from
    each object file that has some."""
    begin(70, lk_boot.start_addr, lk_boot.start_len)
    for i in range(0, len(START_NAME)):
        put(START_NAME[i])
    put(10)
    if lk_boot.init_len != 0:
        begin(70, lk_boot.init_addr, lk_boot.init_len)
        for i in range(0, len(INIT_NAME)):
            put(INIT_NAME[i])
        put(10)
    for obj in range(0, lk_name.object_count):
        if mark_functions(obj, True, False):
            lines(obj, lk_rec.R_FUNC)
            mark_functions(obj, False, False)


def symbols(kind, letter):
    """The D or V lines of what is kept, in the order the symbols are defined, read from each
    object file that has some."""
    wanted = lk_rec.R_VAR
    if kind == lk_sym.CONSTANT:
        wanted = lk_rec.R_DATA
    for obj in range(0, lk_name.object_count):
        some = False
        for d in range(lk_name.obj_def[obj], lk_name.obj_def[obj + 1]):
            if lk_sym.kind_of(lk_tab.def_ref(d)) == kind and lk_tab.is_kept_def(d):
                lk_tab.def_f[d] |= lk_tab.D_HELD
                some = True
        if some:
            lines(obj, wanted)
            for d in range(lk_name.obj_def[obj], lk_name.obj_def[obj + 1]):
                lk_tab.def_f[d] &= 0xFF ^ lk_tab.D_HELD


def slot(f, number, i, name):
    """The S lines of slot i of kept function f, one per copy: f's symbol has this number in
    the object being read, and the slot's name is held at `name`."""
    s = lk_tab.fn_slot[f] + i
    for ctx in range(0, lk_tab.ctx_count):
        if lk_tab.has_copy(f, ctx):
            n = lk_tab.copy_node(f, ctx)
            begin(83, lk_alloc.slot_addr(n, i), lk_tab.slot_bytes(s))
            copy_name(n, number)
            put(32)
            decimal(i)
            put(32)
            lk_name.write_held(handle, name)
            put(10)


# ---- the C lines, after the image: the names of classes and their parameters are read from
# the files again. In lk_tab.work: from CN, where the name of each class is held + 1, or 0; from
# CPN, that of each class parameter, the first a CLAS record gives; from NM, that of each
# parameter of a class standing for others, from its namer's slot; then the names.
CN = 0
CPN = CN + lk_tab.MAX_CLASSES
NM = CPN + lk_tab.MAX_CPARAMS
C_HELD = NM + lk_tab.MAX_CPARAMS


def class_names_object(obj):
    """Hold the class names, parameter names and namers' slot names object file obj gives."""
    lk_rec.open_object(obj)
    number = 0
    namer = lk_tab.NONE                 # the live class whose namer is being read
    slots = 0
    kind = lk_rec.advance()
    while kind != lk_rec.R_END:
        if kind == lk_rec.R_SYM:
            lk_rec.get_byte()
            s = lk_name.global_sym(obj, number)
            if lk_sym.kind_of(s) == lk_sym.CLASS and lk_sym.is_defined(s) \
                    and lk_tab.work[CN + lk_sym.row_of(s)] == 0:
                lk_tab.work[CN + lk_sym.row_of(s)] = lk_name.buf_keep() + 1
            number += 1
        elif kind == lk_rec.R_CLAS:
            k = lk_sym.row_of(lk_name.global_sym(obj, lk_rec.get_word()))
            lk_rec.get_byte()
            np = lk_rec.get_byte()
            for i in range(0, np):
                lk_rec.get_word()
                p = lk_tab.cls_par[k] + i
                pos = lk_name.buf_keep()
                if lk_tab.work[CPN + p] == 0 and lk_name.get_b(pos) != 0:
                    lk_tab.work[CPN + p] = pos + 1
                else:
                    lk_name.buf_top = pos       # not needed: no longer held
        elif kind == lk_rec.R_FUNC:
            f = lk_sym.row_of(lk_name.global_sym(obj, lk_rec.get_word()))
            namer = lk_tab.NONE
            slots = 0
            k, live = lk_tab.member_class(f)
            if live and lk_tab.cls_namer[k] == f + 1 and lk_tab.fn_ctx[f] != 0:
                namer = k
        elif kind == lk_rec.R_SLOT and namer != lk_tab.NONE:
            if slots < lk_tab.cls_np[namer]:
                lk_rec.get_word()
                lk_rec.get_word()
                lk_rec.get_byte()
                lk_tab.work[NM + lk_tab.cls_par[namer] + slots] = lk_name.buf_keep() + 1
            slots += 1
        kind = lk_rec.advance()
    lk_rec.close()


def param_name(rep, i):
    """Where the name of parameter i of live class rep is held + 1, or 0: the first a CLAS
    record of the class gives, else the first of a class merged into it (lk_scan.merge), else
    that of the namer's slot."""
    p = lk_tab.cls_par[rep] + i
    if lk_tab.work[CPN + p] != 0:
        return lk_tab.work[CPN + p]
    for k in range(0, lk_tab.cls_count):
        if k != rep and lk_tab.class_of(k) == rep and lk_tab.work[CPN + lk_tab.cls_par[k] + i] != 0:
            return lk_tab.work[CPN + lk_tab.cls_par[k] + i]
    return lk_tab.work[NM + p]


def cparams():
    """The C lines: the parameters of every live class, under each name the class has. The
    names are read again, if there is a live class, from the files that have them."""
    live = False
    for k in range(0, lk_tab.cls_count):
        if lk_tab.cls_reach[lk_tab.class_of(k)] != 0:
            live = True
    if not live:
        return
    for i in range(0, C_HELD):
        lk_tab.work[i] = 0
    lk_name.buf_begin(2 * C_HELD, 2 * lk_tab.W_OWN)
    # The files that name a class, and those of the functions that name class parameters.
    for obj in range(0, lk_name.object_count):
        wanted = (lk_scan.obj_cpu[obj] & lk_scan.OBJ_CLASSES) != 0
        for f in range(lk_name.obj_fn[obj], lk_name.obj_fn[obj + 1]):
            k, live = lk_tab.member_class(f)
            if live and lk_tab.cls_namer[k] == f + 1:
                wanted = True
        if wanted:
            class_names_object(obj)
    for k in range(0, lk_tab.cls_count):
        rep = lk_tab.class_of(k)
        if lk_tab.cls_reach[rep] != 0:
            for i in range(0, lk_tab.cls_np[rep]):
                p = lk_tab.cls_par[rep] + i
                begin(67, lk_tab.cp_addr[p], lk_tab.cp_size[p])
                lk_name.write_held(handle, lk_tab.work[CN + k] - 1)
                put(32)
                decimal(i)
                put(32)
                name = param_name(rep, i)
                if name != 0:
                    lk_name.write_held(handle, name - 1)
                else:
                    put(112)
                    decimal(i)
                put(10)
