"""The first reading of the object files: symbols, variables, functions with their slots and
calls, and pointer classes go into the tables. Code is skipped; of the fix-ups only those that
take the address of a function are noted, because taking it keeps the function (lk_graph).

An object file numbers its symbols from 0. `local` keeps, for every object file, the global
symbol each of its numbers stands for, so later readings of a file need no name lookups.

Once every file is read, finish() checks that every symbol is defined, merges pointer classes
that share a member, and adds the calls that only exist because of classes.
"""
import lk_envf
import lk_err
import lk_file
import lk_rec
import lk_sym
import lk_tab

MAX_OBJECTS = 64
MAX_LOCALS = 4096                   # SYM records in all object files together

object_count = 0
obj_first = [0] * (MAX_OBJECTS + 1) # row in `local` of each object's symbol 0
obj_cpu = bytearray(MAX_OBJECTS)
local = [0] * MAX_LOCALS
local_count = 0

cur_fn = lk_tab.NONE                # the function whose records are being read


def damaged():
    lk_rec.damaged(lk_rec.MAIN)


def global_sym(obj, number):
    """The symbol that object file obj calls `number`."""
    if number >= obj_first[obj + 1] - obj_first[obj]:
        lk_file.fail(lk_err.E_DAMAGED, lk_file.ARG_OBJECT + obj)
    return local[obj_first[obj] + number]


def read_sym(obj, kind):
    """Read a symbol number from the record; the symbol must be of this kind."""
    s = global_sym(obj, lk_rec.get_word(lk_rec.MAIN))
    if lk_sym.kind_of(s) != kind:
        damaged()
    return s


def read_name():
    """Read a string from the record as the pending name."""
    size = lk_rec.get_byte(lk_rec.MAIN)
    lk_sym.name_begin()
    for i in range(0, size):
        lk_sym.name_add(lk_rec.get_byte(lk_rec.MAIN))


def define(s):
    if lk_sym.is_defined(s):
        lk_sym.fail(lk_err.E_DUPLICATE, s)
    lk_sym.sym_kind[s] |= lk_sym.DEFINED


def rec_sym(obj):
    global local_count
    kind = lk_rec.get_byte(lk_rec.MAIN)
    if kind < lk_sym.FUNCTION or kind > lk_sym.CLASS:
        damaged()
    read_name()
    if local_count == MAX_LOCALS:
        lk_err.fail(lk_err.E_LOCALS)
    local[local_count] = lk_sym.intern(kind)
    local_count += 1
    obj_first[obj + 1] = local_count


def rec_var(obj):
    s = read_sym(obj, lk_sym.VARIABLE)
    define(s)
    size = lk_rec.get_word(lk_rec.MAIN)
    zp_class = lk_rec.get_byte(lk_rec.MAIN)
    weight = lk_rec.get_byte(lk_rec.MAIN)
    flags = lk_rec.get_byte(lk_rec.MAIN)
    if zp_class > 2:
        damaged()
    # Flag bit 0 once meant "an initial value follows". Initialisers are code now (lk_boot).
    if (flags & 1) != 0:
        lk_file.fail(lk_err.E_VERSION, lk_file.ARG_OBJECT + obj)
    lk_sym.sym_b[s] = size
    lk_sym.sym_f[s] = zp_class
    lk_sym.sym_w[s] = weight
    lk_tab.new_def(s)


def rec_data(obj):
    s = read_sym(obj, lk_sym.CONSTANT)
    define(s)
    lk_sym.sym_b[s] = lk_rec.left(lk_rec.MAIN)
    lk_tab.new_def(s)


def rec_func(obj):
    global cur_fn
    if cur_fn != lk_tab.NONE:
        damaged()
    s = read_sym(obj, lk_sym.FUNCTION)
    define(s)
    cur_fn = lk_tab.new_func(s, lk_rec.get_byte(lk_rec.MAIN))
    lk_sym.sym_a[s] = cur_fn


def rec_slot():
    if cur_fn == lk_tab.NONE or lk_tab.fn_nslots[cur_fn] == 255:
        damaged()
    size = lk_rec.get_word(lk_rec.MAIN)
    zp_class = lk_rec.get_byte(lk_rec.MAIN)
    weight = lk_rec.get_byte(lk_rec.MAIN)
    kind = lk_rec.get_byte(lk_rec.MAIN)
    if zp_class > 2 or kind > 2:
        damaged()
    lk_tab.new_slot(cur_fn, size, zp_class | (kind << lk_tab.S_KIND_SHIFT), weight)


def rec_call(obj):
    if cur_fn == lk_tab.NONE:
        damaged()
    callee = global_sym(obj, lk_rec.get_word(lk_rec.MAIN))
    flags = lk_rec.get_byte(lk_rec.MAIN)
    outer = lk_rec.get_word(lk_rec.MAIN)
    wanted = lk_sym.FUNCTION
    if (flags & 2) != 0:
        wanted = lk_sym.CLASS
    if lk_sym.kind_of(callee) != wanted:
        damaged()
    caller = lk_tab.fn_sym[cur_fn]
    edge = 0
    if (flags & 1) == 0:
        edge = lk_tab.E_NOSAVE
    lk_tab.add_edge(caller, callee, edge)
    if outer != 0xFFFF:
        outer = global_sym(obj, outer)
        kind = lk_sym.kind_of(outer)
        if kind != lk_sym.FUNCTION and kind != lk_sym.CLASS:
            damaged()
        # A call made while the caller's own arguments wait adds nothing to the call itself.
        if outer != caller:
            lk_tab.add_edge(outer, callee, lk_tab.E_NOSAVE | lk_tab.E_PENDING)


def rec_clas(obj):
    s = read_sym(obj, lk_sym.CLASS)
    lk_rec.get_byte(lk_rec.MAIN)        # flags: see lk_graph.check_cycles for why they are not needed
    np = lk_rec.get_byte(lk_rec.MAIN)
    if not lk_sym.is_defined(s):
        lk_sym.sym_kind[s] |= lk_sym.DEFINED
        lk_sym.sym_a[s] = lk_tab.new_class(s, np)
        for i in range(0, np):
            lk_tab.new_cparam(lk_rec.get_word(lk_rec.MAIN))
        return
    # Every module that uses the class describes it; the descriptions must agree.
    k = lk_sym.sym_a[s]
    if lk_tab.cls_np[k] != np:
        lk_sym.fail(lk_err.E_CLASS_DIFFERS, s)
    for i in range(0, np):
        if lk_tab.cp_size[lk_tab.cls_par[k] + i] != lk_rec.get_word(lk_rec.MAIN):
            lk_sym.fail(lk_err.E_CLASS_DIFFERS, s)


def rec_memb(obj):
    k = read_sym(obj, lk_sym.CLASS)
    lk_tab.new_member(k, read_sym(obj, lk_sym.FUNCTION))


def rec_fixes(obj, source):
    """A FIX or DFIX record: note each function whose address it takes.

    In code (source is a function) an address is taken by its low or high byte, `#<f` and
    `#>f`. A two-byte fix-up naming a function there is the operand of a JSR or JMP, a call,
    which needs a CALL record of its own; without one the call is an error (lk_fix.target), and
    must not quietly keep the callee. A function's fix-ups naming itself are its labels or its
    own address and keep nothing. In constant data every fix-up naming a function takes its
    address."""
    if lk_rec.left(lk_rec.MAIN) % 8 != 0:
        damaged()
    lk_tab.begin_addrs()
    while lk_rec.left(lk_rec.MAIN) > 0:
        lk_rec.get_word(lk_rec.MAIN)
        kind = lk_rec.get_byte(lk_rec.MAIN)
        s = global_sym(obj, lk_rec.get_word(lk_rec.MAIN))
        slot = lk_rec.get_byte(lk_rec.MAIN)
        lk_rec.get_word(lk_rec.MAIN)
        if lk_sym.kind_of(s) == lk_sym.FUNCTION and slot == 0xFF:
            if source == lk_tab.NONE:
                lk_tab.new_addr(source, s)
            elif s != lk_tab.fn_sym[source] and (kind == 2 or kind == 3):
                lk_tab.new_addr(source, s)


def take_record(obj, kind):
    """Take in one record of object file obj."""
    global cur_fn
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
    elif kind == lk_rec.R_FIX:
        if cur_fn == lk_tab.NONE:
            damaged()
        rec_fixes(obj, cur_fn)
    elif kind == lk_rec.R_DFIX:
        rec_fixes(obj, lk_tab.NONE)
    elif kind != lk_rec.R_IMP and kind != lk_rec.R_CODE:
        damaged()


def scan(obj):
    """Read object file obj."""
    global cur_fn
    lk_rec.open_object(lk_rec.MAIN, obj)
    obj_first[obj] = local_count
    obj_first[obj + 1] = local_count
    if lk_rec.advance(lk_rec.MAIN) != lk_rec.R_MOD or lk_rec.get_byte(lk_rec.MAIN) != 1:
        lk_file.fail(lk_err.E_VERSION, lk_file.ARG_OBJECT + obj)
    obj_cpu[obj] = lk_rec.get_byte(lk_rec.MAIN)
    if obj_cpu[obj] > lk_envf.cpu:
        lk_file.fail(lk_err.E_NEEDS_65C02, lk_file.ARG_OBJECT + obj)
    cur_fn = lk_tab.NONE
    kind = lk_rec.advance(lk_rec.MAIN)
    while kind != lk_rec.R_END:
        take_record(obj, kind)
        kind = lk_rec.advance(lk_rec.MAIN)
    if cur_fn != lk_tab.NONE:
        damaged()
    lk_rec.close(lk_rec.MAIN)


def scan_all():
    """Read every object file named on the command line."""
    global object_count
    object_count = lk_file.arg_count() - lk_file.ARG_OBJECT
    if object_count > MAX_OBJECTS:
        lk_err.fail(lk_err.E_OBJECTS)
    for obj in range(0, object_count):
        scan(obj)
    finish()


def check_defined():
    for s in range(0, lk_sym.count):
        if not lk_sym.is_defined(s):
            lk_sym.fail(lk_err.E_UNDEFINED, s)


def merge(a, b):
    """Classes a and b share a member, so they are one class from now on."""
    if a == b:
        return
    if lk_tab.cls_np[a] != lk_tab.cls_np[b]:
        lk_sym.fail(lk_err.E_CLASS_DIFFERS, lk_tab.cls_sym[b])
    for i in range(0, lk_tab.cls_np[a]):
        if lk_tab.cp_size[lk_tab.cls_par[a] + i] != lk_tab.cp_size[lk_tab.cls_par[b] + i]:
            lk_sym.fail(lk_err.E_CLASS_DIFFERS, lk_tab.cls_sym[b])
    if b < a:
        lk_tab.cls_rep[a] = b
    else:
        lk_tab.cls_rep[b] = a


def join_members():
    """Give every member its class, merging the classes of a function that is in two."""
    for i in range(0, lk_tab.memb_count):
        f = lk_sym.sym_a[lk_tab.memb_func[i]]
        k = lk_tab.class_of(lk_sym.sym_a[lk_tab.memb_class[i]])
        if lk_tab.fn_class[f] == 0:
            lk_tab.fn_class[f] = k + 1
        else:
            merge(lk_tab.class_of(lk_tab.fn_class[f] - 1), k)


def move_edges():
    """Hand the calls recorded against a merged class to the class that stands for it."""
    for k in range(0, lk_tab.cls_count):
        rep = lk_tab.class_of(k)
        e = lk_sym.sym_b[lk_tab.cls_sym[k]]
        if rep != k and e != 0:
            while lk_tab.edge_next[e - 1] != 0:
                e = lk_tab.edge_next[e - 1]
            lk_tab.edge_next[e - 1] = lk_sym.sym_b[lk_tab.cls_sym[rep]]
            lk_sym.sym_b[lk_tab.cls_sym[rep]] = lk_sym.sym_b[lk_tab.cls_sym[k]]
            lk_sym.sym_b[lk_tab.cls_sym[k]] = 0


def add_block_edges():
    """A class block calls every member of the class."""
    for i in range(0, lk_tab.memb_count):
        k = lk_tab.class_of(lk_sym.sym_a[lk_tab.memb_class[i]])
        lk_tab.add_edge(lk_tab.cls_sym[k], lk_tab.memb_func[i], 0)
        if lk_tab.cls_namer[k] == 0:
            lk_tab.cls_namer[k] = lk_sym.sym_a[lk_tab.memb_func[i]] + 1


def add_via_edges(source):
    """Whoever calls a member of a class calls the class block too, because the member's
    parameters are there (code-model.md, "Functions called through a pointer")."""
    e = lk_sym.sym_b[source]
    while e != 0:
        target = lk_tab.edge_to[e - 1]
        flags = lk_tab.edge_flags[e - 1]
        e = lk_tab.edge_next[e - 1]
        if (flags & lk_tab.E_VIA) == 0 and lk_sym.kind_of(target) == lk_sym.FUNCTION:
            f = lk_sym.sym_a[target]
            if lk_tab.fn_class[f] != 0:
                block = lk_tab.cls_sym[lk_tab.class_of(lk_tab.fn_class[f] - 1)]
                # The block's own edge to its member is not a call of the member.
                if block != source:
                    lk_tab.add_edge(source, block, flags | lk_tab.E_VIA)


def finish():
    """What can only be done once every object file has been read."""
    check_defined()
    join_members()
    move_edges()
    add_block_edges()
    for s in range(0, lk_sym.count):
        kind = lk_sym.kind_of(s)
        if kind == lk_sym.FUNCTION or kind == lk_sym.CLASS:
            add_via_edges(s)
