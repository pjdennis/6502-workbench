"""Regions placed by the program as it starts: `region NAME WIN N dynamic` (configurations.md,
"Regions placed at run time"; lathe/docs/bbc.md, "One image for every machine with sideways
RAM").

A dynamic region is linked as any region in a bank is, its variables at their full sizes in the
window, so that every check of the link holds. Every place that names one of its variables, and
every `with` block's call of map and unmap, is in fixed code (the linker keeps a function with a
block, and all that runs inside one, in fixed memory), which on the BBC is copied into main RAM
at every command: so the program can move the region by changing those places, as it starts,
before anything else runs. The linker lists them, after everything else in the code range, and
`$start` gives the list to the placer module's `place` (the environment's `placer` entry) after
FARCALL.start and before `$init`:

    word    the code range's first address (the RAM from PAGE up to it is free)
    word    the end of the highest of `code`, `data` and `more`, + 1 (the RAM from it to HIMEM is
            free)
    byte    A, then A times: word first, word last
            what the link left free of main memory: the code range from this list on (the list
            is not needed once it has been read), `data` and `more` after their variables
    byte    R, then R times: byte the bank's value the region is linked with
            the dynamic regions, in the order of their entries
    byte    V, then V times: word address, word size, byte region
            the variables of the dynamic regions not in zero page, in the order they are defined
    the places of addresses, each:
            byte    type << 6 | variable: type 1 the word there is an address, 2 its low byte,
                    3 its high byte
            place   (below)
            byte    for type 3, the low byte of the address the linker put there, for the carry
            ended by a byte 0
    the places of banks, each the `LDA #` of a block, whose byte is the bank's value:
            byte    region + 1
            place
            ended by a byte 0
    the calls of map and unmap, by function copy:
            byte    N, the calls (0 ends the list)
            word    the regions the copy's blocks map, a bit each, and $8000 if one maps a bank
                    of no dynamic region
            N times a place: the address of a JSR's or JMP's operand

A place is a byte d, 1 to 255, for the place d bytes after the one before it in its list (the
first after address 0), or a byte 0 and the address.

Where the program puts a variable is its own choice; the linker gives only where it is now. A
two-byte variable, which on an NMOS 6502 must not lie across a page, is refused in a dynamic
region (link error 64), so that any address will do.
With a region in main RAM, the blocks of a function copy whose every block maps a region there
can be turned into nothing (a JSR of map or unmap into three NOPs, a JMP of unmap into an RTS).

The places are held while the image is written, in the order they are written, which is the
order of their addresses, two words each in the work area from W_SITES: an address, and its
type, variable or region, and low byte; a group (T_GROUP) holds the regions its copy maps.
"""
import lk_alloc
import lk_boot
import lk_envf
import lk_err
import lk_fix
import lk_name
import lk_op
import lk_out
import lk_scan
import lk_sym
import lk_tab

W_SITES = lk_tab.W_SNAME + 128      # after the slot names (lk_emit, lk_map): free while the
MAX_SITES = (lk_tab.W_OWN - W_SITES) // 2   # image is written, before the map is
MAX_VARS = 32

T_WORD = 1                          # the types of a place held, in the top three bits
T_LOW = 2
T_HIGH = 3
T_BANK = 4
T_GROUP = 5
T_CALL = 6
KEEP = 0x8000                       # a group's copy maps a bank of no dynamic region
NO_GROUP = 0xFFFF

site_count = 0
group = NO_GROUP                    # the group of the copy being written, if it has one


def active():
    return lk_envf.region_dynamic != 0


def is_dynamic(r):
    """True if region r (its entry in lk_envf) is dynamic."""
    return (lk_envf.region_dynamic & (1 << r)) != 0


def region_index(r):
    """Region r's number among the dynamic regions."""
    n = 0
    for i in range(0, r):
        if is_dynamic(i):
            n += 1
    return n


def rdef_of(d):
    """The entry of variable or constant d among lk_scan's region definitions, or MAX_REGION_DEFS."""
    for i in range(0, lk_scan.rdef_count):
        if lk_scan.rdef_def[i] == d:
            return i
    return lk_scan.MAX_REGION_DEFS


def movable(i):
    """True if region definition i is a kept variable of a dynamic region, not in zero page."""
    d = lk_scan.rdef_def[i]
    return is_dynamic(lk_scan.rdef_region[i]) and lk_tab.is_kept_var(d) and lk_tab.def_a[d] >= 0x100


def var_of(sym):
    """The number of the dynamic variable symbol sym is, or NO_GROUP."""
    k = lk_sym.kind_of(sym)
    if (k != lk_sym.VARIABLE and k != lk_sym.CONSTANT) or not lk_sym.is_defined(sym):
        return NO_GROUP
    d = lk_sym.row_of(sym)
    i = rdef_of(d)
    if i == lk_scan.MAX_REGION_DEFS or not movable(i):
        return NO_GROUP
    n = 0
    for k in range(0, i):
        if movable(k):
            n += 1
    return n


def region_of_sym(sym):
    """The region (its entry in lk_envf) of the variable or constant sym, or MAX_REGIONS."""
    k = lk_sym.kind_of(sym)
    if (k != lk_sym.VARIABLE and k != lk_sym.CONSTANT) or not lk_sym.is_defined(sym):
        return lk_envf.MAX_REGIONS
    i = rdef_of(lk_sym.row_of(sym))
    if i == lk_scan.MAX_REGION_DEFS:
        return lk_envf.MAX_REGIONS
    return lk_scan.rdef_region[i]


def begin():
    """Before the image is written: no place held."""
    global site_count, group
    site_count = 0
    group = NO_GROUP


def begin_copy():
    """A function copy is about to be written: its blocks are a group of their own."""
    global group
    group = NO_GROUP


def add(info, addr):
    global site_count
    if site_count == MAX_SITES:
        lk_err.fail(lk_err.E_SITES)
    lk_tab.set_wk(W_SITES + 2 * site_count, addr)
    lk_tab.set_wk(W_SITES + 2 * site_count + 1, info)
    site_count += 1


def add_to_group(mask):
    """The copy being written has a block: its group, made if new, maps `mask` too."""
    global group
    if group == NO_GROUP:
        group = site_count
        add(T_GROUP << 13, 0)
    lk_tab.set_wk(W_SITES + 2 * group, lk_tab.wk(W_SITES + 2 * group) | mask)


def note(kind, sym, addr, address, op):
    """The image's byte at `addr` (a word's first byte) is a fix-up of this kind naming sym, which
    stands for `address`, in an instruction `op` (0 in constant data): hold it if it names a
    dynamic region's variable, maps a region's bank, or calls map or unmap."""
    if kind == lk_fix.K_BANK:
        r = region_of_sym(sym)
        if r != lk_envf.MAX_REGIONS and is_dynamic(r):
            add_to_group(1 << region_index(r))
            add((T_BANK << 13) | (region_index(r) << 8), addr)
        else:
            add_to_group(KEEP)
        return
    if kind == lk_fix.K_WORD and (sym == lk_name.fc_map or sym == lk_name.fc_unmap) \
            and (op == lk_op.OP_JSR or op == lk_op.OP_JMP):
        add_to_group(0)
        add(T_CALL << 13, addr)
        return
    v = var_of(sym)
    if v == NO_GROUP:
        return
    if v >= MAX_VARS:
        lk_err.fail(lk_err.E_SITES)
    if lk_fix.is_word(kind):
        add((T_WORD << 13) | (v << 8), addr)
    elif kind == lk_fix.K_HIGH or kind == lk_fix.K_REACH_HIGH:
        add((T_HIGH << 13) | (v << 8) | (address & 0xFF), addr)
    else:
        add((T_LOW << 13) | (v << 8), addr)


def refuse(kind, sym, user):
    """A fix-up naming sym of this kind is written outside the image (in a bank's file): it may
    not name a dynamic region's variable or map its bank. user is the function or constant it
    is in."""
    r = region_of_sym(sym)
    if r != lk_envf.MAX_REGIONS and is_dynamic(r) and (kind == lk_fix.K_BANK or var_of(sym) != NO_GROUP):
        lk_name.fail_in(lk_err.E_DYNAMIC, sym, user)


def check_constants():
    """A dynamic region holds no constant data, which would have to be copied where it goes, and
    no two-byte variable, which on an NMOS 6502 must not lie across a page: the placer puts a
    variable at any address."""
    for i in range(0, lk_scan.rdef_count):
        d = lk_scan.rdef_def[i]
        if is_dynamic(lk_scan.rdef_region[i]) and lk_tab.is_kept_def(d) \
                and (lk_tab.def_f[d] & lk_tab.D_CONST) != 0:
            lk_name.fail(lk_err.E_DYNAMIC, lk_tab.def_ref(d))
        if movable(i) and lk_alloc.straddles(0xFF, lk_tab.def_b[d]):
            lk_name.fail(lk_err.E_DYNAMIC, lk_tab.def_ref(d))


def top():
    """The end of the highest of the ranges of main memory, + 1."""
    t = lk_envf.code_hi
    if lk_envf.data_hi > t:
        t = lk_envf.data_hi
    if lk_envf.has_more and lk_envf.more_hi > t:
        t = lk_envf.more_hi
    return (t + 1) & 0xFFFF


def put_place(before, addr):
    """A place: addr, after `before`. Returns addr."""
    d = (addr - before) & 0xFFFF
    if d >= 1 and d <= 0xFF:
        lk_out.put(d)
    else:
        lk_out.put(0)
        lk_out.put_word(addr)
    return addr


def site_type(i):
    return lk_tab.wk(W_SITES + 2 * i + 1) >> 13


def site_addr(i):
    return lk_tab.wk(W_SITES + 2 * i)


def area_count():
    n = 0
    if lk_boot.places_addr <= lk_envf.code_hi:
        n += 1
    if lk_alloc.data_end <= lk_envf.data_hi - lk_envf.data_lo:
        n += 1
    if lk_envf.has_more and lk_alloc.more_end <= lk_envf.more_hi - lk_envf.more_lo:
        n += 1
    return n


def put_areas():
    lk_out.put(area_count())
    if lk_boot.places_addr <= lk_envf.code_hi:
        lk_out.put_word(lk_boot.places_addr)
        lk_out.put_word(lk_envf.code_hi)
    if lk_alloc.data_end <= lk_envf.data_hi - lk_envf.data_lo:
        lk_out.put_word((lk_envf.data_lo + lk_alloc.data_end) & 0xFFFF)
        lk_out.put_word(lk_envf.data_hi)
    if lk_envf.has_more and lk_alloc.more_end <= lk_envf.more_hi - lk_envf.more_lo:
        lk_out.put_word((lk_envf.more_lo + lk_alloc.more_end) & 0xFFFF)
        lk_out.put_word(lk_envf.more_hi)


def put_regions():
    n = 0
    for r in range(0, lk_envf.region_count):
        if is_dynamic(r):
            n += 1
    lk_out.put(n)
    for r in range(0, lk_envf.region_count):
        if is_dynamic(r):
            lk_out.put(lk_envf.bank_value[lk_envf.region_bank[r] - 1])


def put_vars():
    n = 0
    for i in range(0, lk_scan.rdef_count):
        if movable(i):
            n += 1
    if n > MAX_VARS:
        lk_err.fail(lk_err.E_SITES)
    lk_out.put(n)
    for i in range(0, lk_scan.rdef_count):
        if movable(i):
            d = lk_scan.rdef_def[i]
            lk_out.put_word(lk_tab.def_a[d])
            lk_out.put_word(lk_tab.def_b[d])
            lk_out.put(region_index(lk_scan.rdef_region[i]))


def put_addresses():
    before = 0
    for i in range(0, site_count):
        t = site_type(i)
        if t == T_WORD or t == T_LOW or t == T_HIGH:
            info = lk_tab.wk(W_SITES + 2 * i + 1)
            lk_out.put((t << 6) | ((info >> 8) & 0x1F))
            before = put_place(before, site_addr(i))
            if t == T_HIGH:
                lk_out.put(info & 0xFF)
    lk_out.put(0)


def put_banks():
    before = 0
    for i in range(0, site_count):
        if site_type(i) == T_BANK:
            lk_out.put(((lk_tab.wk(W_SITES + 2 * i + 1) >> 8) & 0x1F) + 1)
            before = put_place(before, site_addr(i))
    lk_out.put(0)


def calls_from(i):
    """How many calls are held from place i up to the next group: at most 255."""
    n = 0
    while i < site_count and site_type(i) != T_GROUP and n < 0xFF:
        if site_type(i) == T_CALL:
            n += 1
        i += 1
    return n


def put_calls():
    """Each group's calls, in parts of at most 255 calls, each part with the group's regions."""
    before = 0
    for g in range(0, site_count):
        if site_type(g) == T_GROUP:
            i = g + 1
            n = calls_from(i)
            while n != 0:
                lk_out.put(n)
                lk_out.put_word(site_addr(g))
                while n != 0:
                    if site_type(i) == T_CALL:
                        before = put_place(before, site_addr(i))
                        n -= 1
                    i += 1
                n = calls_from(i)
    lk_out.put(0)


def write_list():
    """After the code in the image: the list ($places)."""
    check_constants()
    lk_out.seek(lk_boot.places_addr)
    lk_out.put_word(lk_envf.code_lo)
    lk_out.put_word(top())
    put_areas()
    put_regions()
    put_vars()
    put_addresses()
    put_banks()
    put_calls()
    after = (lk_out.base + lk_out.written) & 0xFFFF     # after the list
    if after - 1 > lk_envf.code_hi:
        lk_err.begin(lk_err.E_CODE_FULL)
        lk_err.over(after - 1 - lk_envf.code_hi, False)
        lk_err.finish()
