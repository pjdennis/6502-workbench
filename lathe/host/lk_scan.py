"""The first reading of the object files: symbols, variables, functions with their slots and
calls, and pointer classes go into the tables. Code is skipped; of the fix-ups only the variables,
constant data and function addresses they name are noted, once for each function or table that
names them, because naming them from what is kept keeps them (lk_graph).

An object file numbers its symbols from 0; lk_name.local says what each number stands for.

A WGT record adds weight to a variable or a slot defined elsewhere (object-format.md). A weight
for a slot of a function not read yet waits in the pend_ table until every file is read; if more
wait than the table holds, none is taken from it: the WGT records of the files that gave one are
read again then, and every weight that waited is added from them (reread_weights). A weight is a
saturating sum, the same in any order, so the order the files are named in decides nothing.

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
obj_bank = bytearray(lk_name.MAX_OBJECTS)       # the bank its code is placed in + 1, or 0
OBJ_CLASSES = 0x80                  # the file names a pointer class (lk_map.cparams)
OBJ_WEIGHTS = 0x40                  # a weight it gives waited for a function not read yet

cur_obj = 0                         # the object file being read
cur_fn = lk_tab.NONE                # the function whose records are being read
cur_sym = 0                         # its symbol
dfix_read = False                   # a DFIX record was just read: a DATA record must follow
rgn_read = False                    # a RGN record was read: a VAR, or a DFIX and DATA, must follow
rgn_bank = 0                        # the bank + 1 of its region, or 0 if the region is fixed
rgn_region = 0                      # the region itself, its entry in lk_envf
rgn_at = False                      # and it is `fixed ADDR` (lk_envf.region_at)

# The variables and constants in a region that is in a bank (lk_envf.region_bank), or that is
# `fixed ADDR`, in the order they are defined. Those of any other region in fixed memory are
# ordinary ones and are not here.
MAX_REGION_DEFS = 64
rdef_count = 0
rdef_def = [0] * MAX_REGION_DEFS
rdef_region = bytearray(MAX_REGION_DEFS)    # the region, its entry in lk_envf, whose bank it is in

# The weights waiting, in lk_tab.work, which nothing else uses while the files are read: where
# each column starts.
pend_count = 0
weights_lost = False                # more waited than the table holds: they are read again
late_before = lk_tab.NONE           # while they are (reread_weights): the record's next function
PEND_SYM = 0                        # a function
PEND_SLOT = MAX_PENDING
PEND_WEIGHT = 2 * MAX_PENDING
PEND_OBJ = 3 * MAX_PENDING          # the object file whose WGT record gave it


def cpu_of(obj):
    return obj_cpu[obj] & (0xFF ^ OBJ_CLASSES ^ OBJ_WEIGHTS)


def damaged():
    lk_rec.damaged()


def read_sym(kind):
    """Read a symbol number from the record; the symbol must be of this kind."""
    s = lk_name.global_sym(cur_obj, lk_rec.get_word())
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


def rec_rgn():
    """A RGN record: the region of the VAR or DATA record that follows. A name the environment
    file has no `region` entry for is a region in fixed memory, as is one given as `fixed`."""
    global rgn_read, rgn_bank, rgn_region, rgn_at
    size = lk_rec.get_byte()
    for i in range(0, size):
        c = lk_rec.get_byte()
        if i < lk_envf.TOKEN_SIZE:
            lk_envf.token[i] = c
    if size == 0 or lk_rec.left() != 0:
        damaged()
    rgn_read = True
    rgn_bank = 0
    rgn_at = False
    if size > lk_envf.TOKEN_SIZE:
        return
    lk_envf.token_len = size
    r = lk_envf.find_region()
    if r != lk_envf.MAX_REGIONS:
        rgn_bank = lk_envf.region_bank[r]
        rgn_region = r
        rgn_at = lk_envf.region_at[r] != 0


def in_region(d):
    """Variable or constant d is defined: if a RGN record came before it, it is in that region."""
    global rgn_read, rdef_count
    if not rgn_read:
        return
    rgn_read = False
    if rgn_bank == 0 and not rgn_at:
        return
    if rdef_count == MAX_REGION_DEFS:
        lk_err.fail(lk_err.E_DEFS)
    rdef_def[rdef_count] = d
    rdef_region[rdef_count] = rgn_region
    rdef_count += 1
    if rgn_bank != 0:
        lk_envf.region_used = rgn_bank


def region_of(d):
    """The bank + 1 of the region variable or constant d is in, or 0 for fixed memory."""
    for i in range(0, rdef_count):
        if rdef_def[i] == d:
            return lk_envf.region_bank[rdef_region[i]]
    return 0


def is_at(d):
    """True if variable or constant d is in a region that is `fixed ADDR`: a variable then has its
    address from lk_alloc.place_at, and constant data is fixed, as any region's in fixed memory."""
    if not lk_envf.has_at:
        return False
    for i in range(0, rdef_count):
        if rdef_def[i] == d:
            return lk_envf.region_at[rdef_region[i]] != 0
    return False


def define(s):
    """Symbol s is defined by the record being read: it must not have been before."""
    if lk_sym.is_defined(lk_name.now(s)):
        lk_name.fail(lk_err.E_DUPLICATE, s)


def rec_sym():
    kind = lk_rec.get_byte()
    if kind < lk_sym.FUNCTION or kind > lk_sym.CLASS:
        damaged()
    if kind == lk_sym.CLASS:
        obj_cpu[cur_obj] |= OBJ_CLASSES
    read_name()
    if lk_name.local_count == lk_name.MAX_LOCALS:
        lk_err.fail(lk_err.E_LOCALS)
    lk_name.set_local(lk_name.local_count, lk_name.symbol(kind))
    lk_name.local_count += 1
    lk_name.obj_first[cur_obj + 1] = lk_name.local_count


def rec_var():
    s = read_sym(lk_sym.VARIABLE)
    define(s)
    size = lk_rec.get_word()
    zp_class = lk_rec.get_byte()
    weight = lk_rec.get_byte()
    flags = lk_rec.get_byte()
    if zp_class > 2:
        damaged()
    # Flag bit 0 once meant "an initial value follows". Initialisers are code now (lk_boot).
    if (flags & 1) != 0:
        lk_file.fail(lk_err.E_VERSION, lk_file.ARG_OBJECT + cur_obj)
    if rgn_read and zp_class != 2:
        damaged()                   # a variable in a region is never in zero page
    d = lk_tab.new_def(zp_class)
    in_region(d)
    lk_tab.def_b[d] = size
    # Other modules' WGT records may have come first.
    lk_tab.def_a[d] = heavier(lk_name.more(s), weight)       # the weight, for now (lk_tab.def_w)
    lk_name.bind(s, lk_tab.def_ref(d))


def rec_data():
    s = read_sym(lk_sym.CONSTANT)
    define(s)
    d = lk_tab.new_def(lk_tab.D_CONST)
    in_region(d)
    lk_tab.def_a[d] = cur_obj       # until it is placed (lk_graph.keep_referenced)
    lk_tab.def_b[d] = lk_rec.left()
    lk_name.bind(s, lk_tab.def_ref(d))


def rec_func():
    global cur_fn, cur_sym
    if cur_fn != lk_tab.NONE:
        damaged()
    s = read_sym(lk_sym.FUNCTION)
    define(s)
    flags = lk_rec.get_byte() & (lk_tab.F_RECURSIVE | lk_tab.F_INTERRUPT)
    if lk_name.is_init_sym(s):
        flags |= lk_tab.F_INIT
    if lk_name.is_block_sym(s):
        flags |= lk_tab.F_FIXED      # a call inside a `with` block read before it names it
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


def rec_call():
    if cur_fn == lk_tab.NONE:
        damaged()
    callee = lk_name.global_sym(cur_obj, lk_rec.get_word())
    flags = lk_rec.get_byte()
    outer = lk_rec.get_word()
    wanted = lk_sym.FUNCTION
    if (flags & 2) != 0:
        wanted = lk_sym.CLASS
    if lk_sym.kind_of(callee) != wanted:
        damaged()
    if (flags & 4) != 0:
        in_block(callee)
    edge = 0
    if (flags & 1) == 0:
        edge = lk_tab.E_NOSAVE
    lk_tab.add_own(cur_fn, lk_sym.edge_bits(callee), edge)
    if outer != 0xFFFF:
        outer = lk_name.global_sym(cur_obj, outer)
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


def in_block(s):
    """A call inside a `with` block names function or class s. What it reaches runs inside the
    block, and must be in fixed memory, as the block's own function is, so that the region stays
    mapped while it runs (configurations.md, "Functions kept in fixed memory"): a function is
    marked lk_tab.F_FIXED, and keep_called() marks what they call. A function defined later sees
    the mark on its symbol (rec_func); the members of a class are marked from it once every file
    is read (keep_members)."""
    lk_name.set_block(s)
    r = lk_name.now(s)
    if lk_sym.is_defined(r) and lk_sym.kind_of(r) == lk_sym.FUNCTION:
        lk_tab.fn_flags[lk_sym.row_of(r)] |= lk_tab.F_FIXED


def rec_clas():
    s = read_sym(lk_sym.CLASS)
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


def rec_memb():
    k = read_sym(lk_sym.CLASS)
    lk_tab.new_member(k, read_sym(lk_sym.FUNCTION))


def heavier(weight, amount):
    if weight + amount > 255:
        return 255
    return weight + amount


def rec_wgt():
    """Weights this module adds to variables and slots: entries of symbol (2), slot, weight. Read
    again by reread_weights (late_before is then the first function read after the record), it
    adds only those that waited."""
    global pend_count, weights_lost
    if cur_fn != lk_tab.NONE or lk_rec.left() % 4 != 0:
        damaged()
    while lk_rec.left() > 0:
        s = lk_name.global_sym(cur_obj, lk_rec.get_word())
        slot = lk_rec.get_byte()
        weight = lk_rec.get_byte()
        kind = lk_sym.kind_of(s)
        r = lk_name.now(s)
        if late_before != lk_tab.NONE and (kind != lk_sym.FUNCTION or slot == 0xFF
                                           or not lk_sym.is_defined(r) or lk_sym.row_of(r) < late_before):
            pass                        # added the first time, or nothing defines it
        elif kind == lk_sym.VARIABLE and slot == 0xFF:
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
            add_weight(lk_sym.row_of(r), slot, weight)
        elif kind == lk_sym.FUNCTION and slot != 0xFF:
            obj_cpu[cur_obj] |= OBJ_WEIGHTS
            if pend_count == MAX_PENDING:
                weights_lost = True
            else:
                lk_tab.set_wk(PEND_SYM + pend_count, s)
                lk_tab.set_wk(PEND_SLOT + pend_count, slot)
                lk_tab.set_wk(PEND_WEIGHT + pend_count, weight)
                lk_tab.set_wk(PEND_OBJ + pend_count, cur_obj)
                pend_count += 1
        else:
            damaged()


def add_weight(f, slot, weight):
    """The object file cur_obj weights slot `slot` of function f."""
    if slot >= lk_tab.fn_nslots(f):
        lk_file.fail(lk_err.E_DAMAGED, lk_file.ARG_OBJECT + cur_obj)
    i = lk_tab.fn_slot[f] + slot
    lk_tab.set_slot_weight(i, heavier(lk_tab.slot_weight_of(i), weight))


def add_pending_weights():
    """The weights given for slots of functions before the functions were read, each from the
    object file that gave it (cur_obj, once every file is read)."""
    global cur_obj
    for i in range(0, pend_count):
        s = lk_tab.wk(PEND_SYM + i)
        # A function nothing defines is reported if something kept calls it (lk_graph).
        if lk_sym.is_defined(s):
            cur_obj = lk_tab.wk(PEND_OBJ + i)
            add_weight(lk_sym.row_of(s), lk_tab.wk(PEND_SLOT + i), lk_tab.wk(PEND_WEIGHT + i))


def reread_weights():
    """More weights waited than the table holds: read again the WGT records of the files that gave
    one, and add each weight for a slot of a function read after the record (one that waited),
    those the table holds among them, which it then forgets. Before lk_name.resolve: once `local`
    holds what the symbols stand for, lk_name.now no longer applies to them. No WGT record is read
    after it."""
    global late_before, cur_obj, pend_count
    pend_count = 0
    for obj in range(0, lk_name.object_count):
        if (obj_cpu[obj] & OBJ_WEIGHTS) != 0:
            cur_obj = obj
            lk_rec.open_object(obj)
            late_before = lk_name.obj_fn[obj]   # the functions read before the record
            kind = lk_rec.advance()
            while kind != lk_rec.R_END:
                if kind == lk_rec.R_FUNC:
                    late_before += 1
                elif kind == lk_rec.R_WGT:
                    rec_wgt()
                kind = lk_rec.advance()
            lk_rec.close()


def rec_fixes():
    """A FIX or DFIX record: check its entries. What they keep is worked out later, by reading
    them again (lk_graph.keep_referenced). A function with a kind 6 fix-up, the bank of a region
    for `with`, is marked (lk_tab.F_WITH); constant data has none."""
    if lk_rec.left() % 8 != 0:
        damaged()
    while lk_rec.left() > 0:
        lk_rec.get_word()
        if lk_rec.get_byte() == 6:
            if cur_fn == lk_tab.NONE:
                damaged()
            lk_tab.fn_flags[cur_fn] |= lk_tab.F_WITH
        lk_name.global_sym(cur_obj, lk_rec.get_word())
        lk_rec.get_byte()
        lk_rec.get_word()


def take_record(kind):
    """Take in one record of the object file being read (cur_obj)."""
    global cur_fn, dfix_read
    fixed = dfix_read
    dfix_read = False
    if fixed and kind != lk_rec.R_DATA:
        damaged()               # a DFIX belongs to the DATA record just after it
    if rgn_read and kind != lk_rec.R_VAR and kind != lk_rec.R_DFIX and kind != lk_rec.R_DATA:
        damaged()               # a RGN record belongs to the VAR or DATA record after it
    if kind == lk_rec.R_SYM:
        rec_sym()
    elif kind == lk_rec.R_VAR:
        rec_var()
    elif kind == lk_rec.R_DATA:
        rec_data()
    elif kind == lk_rec.R_FUNC:
        rec_func()
    elif kind == lk_rec.R_SLOT:
        rec_slot()
    elif kind == lk_rec.R_CALL:
        rec_call()
    elif kind == lk_rec.R_ENDF:
        cur_fn = lk_tab.NONE
    elif kind == lk_rec.R_CLAS:
        rec_clas()
    elif kind == lk_rec.R_MEMB:
        rec_memb()
    elif kind == lk_rec.R_WGT:
        rec_wgt()
    elif kind == lk_rec.R_FIX:
        if cur_fn == lk_tab.NONE:
            damaged()
        rec_fixes()
    elif kind == lk_rec.R_DFIX:
        if cur_fn != lk_tab.NONE:
            damaged()
        rec_fixes()
        dfix_read = True
    elif kind == lk_rec.R_RGN:
        if cur_fn != lk_tab.NONE or rgn_read:
            damaged()
        rec_rgn()
    elif kind != lk_rec.R_IMP and kind != lk_rec.R_CODE:
        damaged()


def module_place():
    """The MOD record's module name: if the environment file places the module, its code goes
    in that bank or overlay. The name is read into lk_envf's token, which a longer name than
    any entry can hold does not match."""
    size = lk_rec.get_byte()
    for i in range(0, size):
        c = lk_rec.get_byte()
        if i < lk_envf.TOKEN_SIZE:
            lk_envf.token[i] = c
    obj_bank[cur_obj] = 0
    if size > lk_envf.TOKEN_SIZE:
        return
    lk_envf.token_len = size
    for i in range(0, lk_envf.place_count):
        if lk_envf.is_token(lk_envf.place_name[i]):
            obj_bank[cur_obj] = (lk_envf.place_bank[i] & lk_envf.P_BANK) + 1
            lk_envf.place_bank[i] |= lk_envf.P_LINKED


def check_places():
    """Every module the environment file places must be linked."""
    for i in range(0, lk_envf.place_count):
        if (lk_envf.place_bank[i] & lk_envf.P_LINKED) == 0:
            lk_envf.fail_text(lk_err.E_PLACE_UNLINKED, lk_envf.place_name[i])


def object_of(f):
    """The object file that defines function f."""
    obj = 0
    while f >= lk_name.obj_fn[obj + 1]:
        obj += 1
    return obj


def bank_in(f, obj):
    """The bank or overlay function f of object file obj is placed in + 1, or 0 for fixed
    memory: its module's bank, unless f is kept in fixed memory because it has a `with` block
    (lk_tab.F_WITH) or runs inside one (F_FIXED)."""
    if (lk_tab.fn_flags[f] & (lk_tab.F_WITH | lk_tab.F_FIXED)) != 0:
        return 0
    return obj_bank[obj]


def fn_bank(f):
    """The bank or overlay function f's code is placed in + 1, or 0 for fixed memory."""
    return bank_in(f, object_of(f))


def module_bank(f):
    """The bank or overlay + 1 of the module of function f, kept in fixed memory or not."""
    return obj_bank[object_of(f)]


def def_bank(d):
    """The bank or overlay the code of the module that defines variable or constant d is
    placed in + 1, or 0."""
    obj = 0
    while d >= lk_name.obj_def[obj + 1]:
        obj += 1
    return obj_bank[obj]


def scan(obj):
    """Read object file obj."""
    global cur_obj, cur_fn, dfix_read, rgn_read
    lk_rec.open_object(obj)
    cur_obj = obj
    lk_name.obj_first[obj] = lk_name.local_count
    lk_name.obj_first[obj + 1] = lk_name.local_count
    lk_name.obj_fn[obj] = lk_tab.fn_count
    lk_name.obj_def[obj] = lk_tab.def_count
    if lk_rec.advance() != lk_rec.R_MOD or lk_rec.get_byte() != lk_rec.VERSION:
        lk_file.fail(lk_err.E_VERSION, lk_file.ARG_OBJECT + obj)
    obj_cpu[obj] = lk_rec.get_byte()
    if obj_cpu[obj] > lk_envf.cpu:
        lk_file.fail(lk_err.E_NEEDS_65C02, lk_file.ARG_OBJECT + obj)
    module_place()
    cur_fn = lk_tab.NONE
    dfix_read = False
    rgn_read = False
    kind = lk_rec.advance()
    while kind != lk_rec.R_END:
        take_record(kind)
        kind = lk_rec.advance()
    if cur_fn != lk_tab.NONE or dfix_read or rgn_read:
        damaged()
    lk_rec.close()
    lk_name.obj_fn[obj + 1] = lk_tab.fn_count
    lk_name.obj_def[obj + 1] = lk_tab.def_count


def scan_all():
    """Read every object file named on the command line: once quietly for the names to keep
    (lk_name.mark_all), once for the tables."""
    global rdef_count
    rdef_count = 0
    lk_envf.region_used = 0
    lk_name.object_count = lk_file.arg_count() - lk_file.ARG_OBJECT
    if lk_name.object_count > lk_name.MAX_OBJECTS:
        lk_err.fail(lk_err.E_OBJECTS)
    lk_name.mark_all()
    lk_name.begin()
    for obj in range(0, lk_name.object_count):
        scan(obj)
    check_places()
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


def keep_targets(source):
    """Function `source` runs inside a `with` block: so does whatever it calls, and through a
    pointer whatever is a member of the class it calls through. Mark each (in_block). Returns
    True if one was not marked before."""
    found = False
    e = lk_tab.head_of(source)
    while e != 0:
        target = lk_tab.edge_sym(e - 1)
        flags = lk_tab.edge_flag(e - 1)
        e = lk_tab.chain_next(e)
        if (flags & (lk_tab.E_PENDING | lk_tab.E_VIA)) == 0 and lk_sym.is_defined(target):
            if lk_sym.kind_of(target) == lk_sym.FUNCTION:
                f = lk_sym.row_of(target)
                if (lk_tab.fn_flags[f] & lk_tab.F_FIXED) == 0:
                    lk_tab.fn_flags[f] |= lk_tab.F_FIXED
                    found = True
            else:
                for i in range(0, lk_tab.memb_count):
                    f = lk_sym.row_of(lk_tab.memb_func[i])
                    if lk_tab.memb_class[i] == target and (lk_tab.fn_flags[f] & lk_tab.F_FIXED) == 0:
                        lk_tab.fn_flags[f] |= lk_tab.F_FIXED
                        found = True
    return found


def keep_members():
    """Before the symbols are resolved: the functions taken as a class that a call inside a
    `with` block calls through (lk_name.X_BLOCK) can be reached there, so are marked (in_block).
    Only those: a pointer of a class holds only functions taken as that class; classes merged
    because they share a member share their parameters, not their pointers."""
    for i in range(0, lk_tab.memb_count):
        r = lk_name.now(lk_tab.memb_func[i])
        if lk_name.is_block_sym(lk_tab.memb_class[i]) and lk_sym.is_defined(r):
            lk_tab.fn_flags[lk_sym.row_of(r)] |= lk_tab.F_FIXED


def keep_called():
    """Everything a function marked by in_block calls, directly or not, through a pointer or
    not, runs inside the block too, so it is kept in fixed memory: a pointer into the region
    that the block passes on is good there. Marked until nothing new is found, a pass for each
    level of calls."""
    more = True
    while more:
        more = False
        for f in range(0, lk_tab.fn_count):
            if (lk_tab.fn_flags[f] & lk_tab.F_FIXED) != 0 and keep_targets(lk_tab.fn_ref(f)):
                more = True


def move_edges():
    """Hand the calls recorded against a merged class to the class that stands for it."""
    for k in range(0, lk_tab.cls_count):
        rep = lk_tab.class_of(k)
        e = lk_tab.cls_edge[k]
        if rep != k and e != 0:
            while lk_tab.chain_next(e) != 0:
                e = lk_tab.chain_next(e)
            lk_tab.set_wk(lk_tab.W_NEXT + e - 1, lk_tab.cls_edge[rep])
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
    keep_members()
    if weights_lost:
        reread_weights()            # while the records' symbols are still symbols
    lk_name.resolve()
    for i in range(0, pend_count):
        lk_tab.set_wk(PEND_SYM + i, lk_name.now(lk_tab.wk(PEND_SYM + i)))
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
    keep_called()
    add_far_edges()
    lk_tab.chains_to_runs()


def crosses(source, target, flags):
    """True if a call of function source, with these edge flags, of `target` is a far call:
    a call (not an edge that only places storage) of a function in a window from code that is
    not in the same bank or overlay."""
    if (flags & (lk_tab.E_PENDING | lk_tab.E_VIA)) != 0:
        return False
    if lk_sym.kind_of(target) != lk_sym.FUNCTION or not lk_sym.is_defined(target):
        return False
    b = fn_bank(lk_sym.row_of(target))
    return b != 0 and b != fn_bank(source)


def add_far_edges():
    """A far call is a call of the far-call module's `call` (configurations.md, "The stub"):
    a function that makes one calls it, and so does the block of a class with a member in a
    window, whose calls go through the member's stub. Its storage, and that of what it calls
    (rt_ovl.load), is then never shared with the caller's."""
    if not lk_envf.placed():
        return
    call = lk_name.fc_call
    if call == lk_tab.NONE or lk_name.fc_start == lk_tab.NONE:
        lk_envf.fail_text(lk_err.E_NO_FARCALL, lk_envf.farcall)
    for f in range(0, lk_tab.fn_count):
        e = lk_tab.head_of(lk_tab.fn_ref(f))
        while e != 0:
            if crosses(f, lk_tab.edge_sym(e - 1), lk_tab.edge_flag(e - 1)):
                lk_tab.add_edge(lk_tab.fn_ref(f), call, lk_tab.E_NOSAVE)
                e = 0
            else:
                e = lk_tab.chain_next(e)
    for i in range(0, lk_tab.memb_count):
        if fn_bank(lk_sym.row_of(lk_tab.memb_func[i])) != 0:
            k = lk_tab.class_of(lk_sym.row_of(lk_tab.memb_class[i]))
            lk_tab.add_edge(lk_tab.cls_ref(k), call, lk_tab.E_NOSAVE)
