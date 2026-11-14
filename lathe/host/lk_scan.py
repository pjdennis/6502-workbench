"""The first reading of the object files: symbols, variables, functions with their slots and
calls, and pointer classes go into the tables. Code is skipped; of the fix-ups only the variables,
constant data and function addresses they name are noted, once for each function or table that
names them, because naming them from what is kept keeps them (lk_graph).

An object file numbers its symbols from 0; lk_name.local says what each number stands for.

A WGT record adds weight to a variable or a slot defined elsewhere (object-format.md). A weight
for a slot of a function not read yet waits in the pend_ table until every file is read.

Once every file is read, finish() merges pointer classes that share a member, adds the calls
that only exist because of classes and adds the weights that waited. A symbol need not be defined unless something kept uses
it, which lk_graph checks as it finds what is kept.
"""
import lk_envf
import lk_err
import lk_file
import lk_name
import lk_rec
import lk_sym
import lk_tab

MAX_PENDING = 64                    # weights for slots of functions not read yet

obj_cpu = bytearray(lk_name.MAX_OBJECTS)        # its CPU, and OBJ_CLASSES
OBJ_CLASSES = 0x80                  # the file names a pointer class (lk_map.cparams)

cur_fn = lk_tab.NONE                # the function whose records are being read
cur_sym = 0                         # its symbol
dfix_read = False                   # a DFIX record was just read: a DATA record must follow

# The weights waiting, in lk_tab.work, which nothing else uses while the files are read: where
# each column starts.
pend_count = 0
PEND_SYM = 0                        # a function
PEND_SLOT = MAX_PENDING
PEND_WEIGHT = 2 * MAX_PENDING
PEND_OBJ = 3 * MAX_PENDING          # the object file whose WGT record gave it


def cpu_of(obj):
    return obj_cpu[obj] & (0xFF ^ OBJ_CLASSES)


def damaged():
    lk_rec.damaged()


def read_sym(obj, kind):
    """Read a symbol number from the record; the symbol must be of this kind."""
    s = lk_name.global_sym(obj, lk_rec.get_word())
    if lk_sym.kind_of(s) != kind:
        damaged()
    return s


def read_name():
    """Read a string from the record as the pending name."""
    size = lk_rec.get_byte()
    lk_name.name_begin()
    for i in range(0, size):
        lk_name.name_add(lk_rec.get_byte())


def skip_string():
    size = lk_rec.get_byte()
    for i in range(0, size):
        lk_rec.get_byte()


def define(s):
    """Symbol s is defined by the record being read: it must not have been before."""
    if lk_sym.is_defined(lk_name.now(s)):
        lk_name.fail(lk_err.E_DUPLICATE, s)


def rec_sym(obj):
    kind = lk_rec.get_byte()
    if kind < lk_sym.FUNCTION or kind > lk_sym.CLASS:
        damaged()
    if kind == lk_sym.CLASS:
        obj_cpu[obj] |= OBJ_CLASSES
    read_name()
    if lk_name.local_count == lk_name.MAX_LOCALS:
        lk_err.fail(lk_err.E_LOCALS)
    lk_name.local[lk_name.local_count] = lk_name.symbol(kind)
    lk_name.local_count += 1
    lk_name.obj_first[obj + 1] = lk_name.local_count


def rec_var(obj):
    s = read_sym(obj, lk_sym.VARIABLE)
    define(s)
    size = lk_rec.get_word()
    zp_class = lk_rec.get_byte()
    weight = lk_rec.get_byte()
    flags = lk_rec.get_byte()
    if zp_class > 2:
        damaged()
    # Flag bit 0 once meant "an initial value follows". Initialisers are code now (lk_boot).
    if (flags & 1) != 0:
        lk_file.fail(lk_err.E_VERSION, lk_file.ARG_OBJECT + obj)
    d = lk_tab.new_def(zp_class)
    lk_tab.def_b[d] = size
    # Other modules' WGT records may have come first.
    lk_tab.def_a[d] = heavier(lk_name.more(s), weight)       # the weight, for now (lk_tab.def_w)
    lk_name.bind(s, lk_tab.def_ref(d))


def rec_data(obj):
    s = read_sym(obj, lk_sym.CONSTANT)
    define(s)
    d = lk_tab.new_def(lk_tab.D_CONST)
    lk_tab.def_a[d] = obj           # until it is placed (lk_graph.keep_referenced)
    lk_tab.def_b[d] = lk_rec.left()
    lk_name.bind(s, lk_tab.def_ref(d))


def rec_func(obj):
    global cur_fn, cur_sym
    if cur_fn != lk_tab.NONE:
        damaged()
    s = read_sym(obj, lk_sym.FUNCTION)
    define(s)
    flags = lk_rec.get_byte() & (0xFF ^ (lk_tab.F_INIT | lk_tab.F_HELD))
    if lk_name.is_init_sym(s):
        flags |= lk_tab.F_INIT
    cur_fn = lk_tab.new_func(flags)
    cur_sym = s
    lk_name.bind(s, lk_tab.fn_ref(cur_fn))


def rec_slot():
    if cur_fn == lk_tab.NONE or lk_tab.fn_nslots(cur_fn) == 255:
        damaged()
    size = lk_rec.get_word()
    zp_class = lk_rec.get_byte()
    weight = lk_rec.get_byte()
    kind = lk_rec.get_byte()
    if zp_class > 2 or kind > 2:
        damaged()
    lk_tab.new_slot(cur_fn, size, zp_class, kind == 0, weight)


def rec_call(obj):
    if cur_fn == lk_tab.NONE:
        damaged()
    callee = lk_name.global_sym(obj, lk_rec.get_word())
    flags = lk_rec.get_byte()
    outer = lk_rec.get_word()
    wanted = lk_sym.FUNCTION
    if (flags & 2) != 0:
        wanted = lk_sym.CLASS
    if lk_sym.kind_of(callee) != wanted:
        damaged()
    edge = 0
    if (flags & 1) == 0:
        edge = lk_tab.E_NOSAVE
    lk_tab.add_own(cur_fn, lk_sym.edge_bits(callee), edge)
    if outer != 0xFFFF:
        outer = lk_name.global_sym(obj, outer)
        kind = lk_sym.kind_of(outer)
        if kind != lk_sym.FUNCTION and kind != lk_sym.CLASS:
            damaged()
        # A call made while the caller's own arguments wait adds nothing to the call itself.
        if outer != cur_sym:
            edge = lk_tab.E_NOSAVE | lk_tab.E_PENDING
            r = lk_name.now(outer)
            if kind == lk_sym.FUNCTION and lk_sym.is_defined(r):
                edge |= lk_tab.E_VIA            # read after outer's own calls (build_chains)
            lk_tab.add_waiting(outer, lk_sym.edge_bits(callee), edge)


def rec_clas(obj):
    s = read_sym(obj, lk_sym.CLASS)
    lk_rec.get_byte()        # flags: see lk_graph.check_cycles for why they are not needed
    np = lk_rec.get_byte()
    fresh = not lk_sym.is_defined(lk_name.now(s))
    if fresh:
        lk_name.bind(s, lk_tab.cls_ref(lk_tab.new_class(np)))
    k = lk_sym.row_of(lk_name.now(s))
    # Every module that uses the class describes it; the sizes must agree. The names of the
    # parameters are read again for the map (lk_map.cparams).
    if lk_tab.cls_np[k] != np:
        lk_name.fail(lk_err.E_CLASS_DIFFERS, s)
    for i in range(0, np):
        size = lk_rec.get_word()
        p = lk_tab.cls_par[k] + i
        if fresh:
            lk_tab.new_cparam(size)
        elif lk_tab.cp_size[p] != size:
            lk_name.fail(lk_err.E_CLASS_DIFFERS, s)
        skip_string()


def rec_memb(obj):
    k = read_sym(obj, lk_sym.CLASS)
    lk_tab.new_member(k, read_sym(obj, lk_sym.FUNCTION))


def heavier(weight, amount):
    if weight + amount > 255:
        return 255
    return weight + amount


def rec_wgt(obj):
    """Weights this module adds to variables and slots: entries of symbol (2), slot, weight."""
    global pend_count
    if cur_fn != lk_tab.NONE or lk_rec.left() % 4 != 0:
        damaged()
    while lk_rec.left() > 0:
        s = lk_name.global_sym(obj, lk_rec.get_word())
        slot = lk_rec.get_byte()
        weight = lk_rec.get_byte()
        kind = lk_sym.kind_of(s)
        r = lk_name.now(s)
        if kind == lk_sym.VARIABLE and slot == 0xFF:
            if lk_sym.is_defined(r):
                d = lk_sym.row_of(r)
                lk_tab.def_a[d] = heavier(lk_tab.def_w(d), weight)
            else:
                lk_name.set_more(s, heavier(lk_name.more(s), weight))
        elif kind == lk_sym.CLASS and slot != 0xFF and lk_sym.is_defined(r):
            # Its CLAS record comes before the module uses the class.
            k = lk_sym.row_of(r)
            if slot >= lk_tab.cls_np[k]:
                damaged()
            p = lk_tab.cls_par[k] + slot
            lk_tab.cp_weight[p] = heavier(lk_tab.cp_weight[p], weight)
        elif kind == lk_sym.FUNCTION and slot != 0xFF and lk_sym.is_defined(r):
            f = lk_sym.row_of(r)
            if slot >= lk_tab.fn_nslots(f):
                damaged()
            i = lk_tab.fn_slot[f] + slot
            lk_tab.slot_weight[i] = heavier(lk_tab.slot_weight[i], weight)
        elif kind == lk_sym.FUNCTION and slot != 0xFF:
            if pend_count == MAX_PENDING:
                lk_err.fail(lk_err.E_WEIGHTS)
            lk_tab.work[PEND_SYM + pend_count] = s
            lk_tab.work[PEND_SLOT + pend_count] = slot
            lk_tab.work[PEND_WEIGHT + pend_count] = weight
            lk_tab.work[PEND_OBJ + pend_count] = obj
            pend_count += 1
        else:
            damaged()


def add_pending_weights():
    """The weights given for slots of functions before the functions were read."""
    for i in range(0, pend_count):
        s = lk_tab.work[PEND_SYM + i]
        # A function nothing defines is reported if something kept calls it (lk_graph).
        if lk_sym.is_defined(s):
            f = lk_sym.row_of(s)
            if lk_tab.work[PEND_SLOT + i] >= lk_tab.fn_nslots(f):
                lk_file.fail(lk_err.E_DAMAGED, lk_file.ARG_OBJECT + lk_tab.work[PEND_OBJ + i])
            slot = lk_tab.fn_slot[f] + lk_tab.work[PEND_SLOT + i]
            lk_tab.slot_weight[slot] = heavier(lk_tab.slot_weight[slot], lk_tab.work[PEND_WEIGHT + i])


def rec_fixes(obj):
    """A FIX or DFIX record: check its entries. What they keep is worked out later, by reading
    them again (lk_graph.keep_referenced)."""
    if lk_rec.left() % 8 != 0:
        damaged()
    while lk_rec.left() > 0:
        lk_rec.get_word()
        lk_rec.get_byte()
        lk_name.global_sym(obj, lk_rec.get_word())
        lk_rec.get_byte()
        lk_rec.get_word()


def take_record(obj, kind):
    """Take in one record of object file obj."""
    global cur_fn, dfix_read
    fixed = dfix_read
    dfix_read = False
    if fixed and kind != lk_rec.R_DATA:
        damaged()               # a DFIX belongs to the DATA record just after it
    if kind == lk_rec.R_SYM:
        rec_sym(obj)
    elif kind == lk_rec.R_VAR:
        rec_var(obj)
    elif kind == lk_rec.R_DATA:
        rec_data(obj)
    elif kind == lk_rec.R_FUNC:
        rec_func(obj)
    elif kind == lk_rec.R_SLOT:
        rec_slot()
    elif kind == lk_rec.R_CALL:
        rec_call(obj)
    elif kind == lk_rec.R_ENDF:
        cur_fn = lk_tab.NONE
    elif kind == lk_rec.R_CLAS:
        rec_clas(obj)
    elif kind == lk_rec.R_MEMB:
        rec_memb(obj)
    elif kind == lk_rec.R_WGT:
        rec_wgt(obj)
    elif kind == lk_rec.R_FIX:
        if cur_fn == lk_tab.NONE:
            damaged()
        rec_fixes(obj)
    elif kind == lk_rec.R_DFIX:
        if cur_fn != lk_tab.NONE:
            damaged()
        rec_fixes(obj)
        dfix_read = True
    elif kind != lk_rec.R_IMP and kind != lk_rec.R_CODE:
        damaged()


def scan(obj):
    """Read object file obj."""
    global cur_fn, dfix_read
    lk_rec.open_object(obj)
    lk_name.obj_first[obj] = lk_name.local_count
    lk_name.obj_first[obj + 1] = lk_name.local_count
    lk_name.obj_fn[obj] = lk_tab.fn_count
    lk_name.obj_def[obj] = lk_tab.def_count
    if lk_rec.advance() != lk_rec.R_MOD or lk_rec.get_byte() != lk_rec.VERSION:
        lk_file.fail(lk_err.E_VERSION, lk_file.ARG_OBJECT + obj)
    obj_cpu[obj] = lk_rec.get_byte()
    if obj_cpu[obj] > lk_envf.cpu:
        lk_file.fail(lk_err.E_NEEDS_65C02, lk_file.ARG_OBJECT + obj)
    cur_fn = lk_tab.NONE
    dfix_read = False
    kind = lk_rec.advance()
    while kind != lk_rec.R_END:
        take_record(obj, kind)
        kind = lk_rec.advance()
    if cur_fn != lk_tab.NONE or dfix_read:
        damaged()
    lk_rec.close()
    lk_name.obj_fn[obj + 1] = lk_tab.fn_count
    lk_name.obj_def[obj + 1] = lk_tab.def_count


def scan_all():
    """Read every object file named on the command line: once quietly for the names to keep
    (lk_name.mark_all), once for the tables."""
    lk_name.object_count = lk_file.arg_count() - lk_file.ARG_OBJECT
    if lk_name.object_count > lk_name.MAX_OBJECTS:
        lk_err.fail(lk_err.E_OBJECTS)
    lk_name.mark_all()
    lk_name.begin()
    for obj in range(0, lk_name.object_count):
        scan(obj)
    finish()


def add_class_weights():
    """A merged class's parameters are those of the class that stands for it: so are the
    weights given to them."""
    for k in range(0, lk_tab.cls_count):
        rep = lk_tab.class_of(k)
        if rep != k:
            for i in range(0, lk_tab.cls_np[k]):
                p = lk_tab.cls_par[rep] + i
                lk_tab.cp_weight[p] = heavier(lk_tab.cp_weight[p], lk_tab.cp_weight[lk_tab.cls_par[k] + i])


def merge(a, b):
    """Classes a and b share a member, so they are one class from now on."""
    if a == b:
        return
    if lk_tab.cls_np[a] != lk_tab.cls_np[b]:
        lk_name.fail(lk_err.E_CLASS_DIFFERS, lk_tab.cls_ref(b))
    for i in range(0, lk_tab.cls_np[a]):
        if lk_tab.cp_size[lk_tab.cls_par[a] + i] != lk_tab.cp_size[lk_tab.cls_par[b] + i]:
            lk_name.fail(lk_err.E_CLASS_DIFFERS, lk_tab.cls_ref(b))
    if b < a:
        lk_tab.cls_rep[a] = b
    else:
        lk_tab.cls_rep[b] = a


def join_members():
    """Give every member its class, merging the classes of a function that is in two."""
    for i in range(0, lk_tab.memb_count):
        # A MEMB record is not inside a function: what it names must be there, kept or not.
        if not lk_sym.is_defined(lk_tab.memb_func[i]):
            lk_name.fail(lk_err.E_UNDEFINED, lk_tab.memb_func[i])
        if not lk_sym.is_defined(lk_tab.memb_class[i]):
            lk_name.fail(lk_err.E_UNDEFINED, lk_tab.memb_class[i])
        f = lk_sym.row_of(lk_tab.memb_func[i])
        k = lk_tab.class_of(lk_sym.row_of(lk_tab.memb_class[i]))
        if lk_tab.fn_class[f] == 0:
            lk_tab.fn_class[f] = k + 1
        else:
            merge(lk_tab.class_of(lk_tab.fn_class[f] - 1), k)


def move_edges():
    """Hand the calls recorded against a merged class to the class that stands for it."""
    for k in range(0, lk_tab.cls_count):
        rep = lk_tab.class_of(k)
        e = lk_tab.cls_edge[k]
        if rep != k and e != 0:
            while lk_tab.chain_next(e) != 0:
                e = lk_tab.chain_next(e)
            lk_tab.work[lk_tab.W_NEXT + e - 1] = lk_tab.cls_edge[rep]
            lk_tab.cls_edge[rep] = lk_tab.cls_edge[k]
            lk_tab.cls_edge[k] = 0


def add_block_edges():
    """A class block calls every member of the class."""
    for i in range(0, lk_tab.memb_count):
        k = lk_tab.class_of(lk_sym.row_of(lk_tab.memb_class[i]))
        lk_tab.add_edge(lk_tab.cls_ref(k), lk_tab.memb_func[i], 0)
        if lk_tab.cls_namer[k] == 0:
            lk_tab.cls_namer[k] = lk_sym.row_of(lk_tab.memb_func[i]) + 1


def add_via_edges(source):
    """Whoever calls a member of a class calls the class block too, because the member's
    parameters are there (code-model.md, "Functions called through a pointer")."""
    e = lk_tab.head_of(source)
    while e != 0:
        target = lk_tab.edge_sym(e - 1)
        flags = lk_tab.edge_flag(e - 1)
        e = lk_tab.chain_next(e)
        if (flags & lk_tab.E_VIA) == 0 and lk_sym.kind_of(target) == lk_sym.FUNCTION \
                and lk_sym.is_defined(target):
            f = lk_sym.row_of(target)
            if lk_tab.fn_class[f] != 0:
                block = lk_tab.cls_ref(lk_tab.class_of(lk_tab.fn_class[f] - 1))
                # The block's own edge to its member is not a call of the member.
                if block != source:
                    lk_tab.add_edge(source, block, flags | lk_tab.E_VIA)


def finish():
    """What can only be done once every object file has been read: from here on a symbol is
    what it stands for (lk_name.resolve)."""
    lk_name.resolve()
    for i in range(0, pend_count):
        lk_tab.work[PEND_SYM + i] = lk_name.now(lk_tab.work[PEND_SYM + i])
    lk_tab.build_chains()
    join_members()
    add_class_weights()
    add_pending_weights()
    move_edges()
    add_block_edges()
    for f in range(0, lk_tab.fn_count):
        add_via_edges(lk_tab.fn_ref(f))
    for k in range(0, lk_tab.cls_count):
        add_via_edges(lk_tab.cls_ref(k))
    lk_tab.chains_to_runs()
