"""Regions placed by the program as it starts: `region NAME WIN N dynamic` (configurations.md,
"Regions placed at run time"; lathe/docs/bbc.md, "One image for every machine with sideways
RAM").

A dynamic region is linked as any region in a bank is, its variables at their full sizes in the
window, so that every check of the link holds. Every place that names one of its variables, and
every `with` block's `LDA #bank` of it, is in fixed code (the linker keeps a function with a
block, and all that runs inside one, in fixed memory), which on the BBC is copied into main RAM
at every command: so the program can move the region, and change its bank, by changing those
places as it starts, before anything else runs.

A region moves as one block, the bytes its variables take from the first of the lowest to the
last of the highest, and by a whole number of pages: then the low byte of every address in it
stays what it is, and a place is changed by adding one number, the pages moved, to one byte
(the high byte of an address, or of the word that is one). The low bytes are not listed at all,
and no two-byte variable comes to lie across a page. The placer gives up at most 255 bytes a
region for it.

The linker lists the places after everything else in the code range, and `$start` gives the list
to the placer module's `place` (the environment's `placer` entry) after FARCALL.start and before
`$init`:

    word    the code range's first address (the RAM from PAGE up to it is free)
    word    the end of the highest of `code`, `data` and `more`, + 1 (the RAM from it to HIMEM is
            free)
    byte    A, then A times: word first, word last
            what the link left free of main memory: the code range from this list on (the list
            is not needed once it has been read), `data` and `more` after their variables
    byte    R, then for each dynamic region, in the order of the entries:
            byte    the bank's value it is linked with
            word    its block's first byte, as linked, and word its size (0: nothing to move)
            word    N, then N places: a high byte, to which the pages moved are added
            word    M, then M places: a block's `LDA #bank` byte, which is the bank's value

A place is a byte d, 1 to 255, for the place d bytes after the one before it in its list (the
first after address 0), or a byte 0 and the address.

With a region in main RAM its blocks still map a bank: the module's own slot, which leaves the
window as it was; nothing that runs inside a block reads the window. They cost what they cost
(67 cycles a block, spikes.md), which was weighed against the bytes of listing every call of map
and unmap ("One image for every machine with sideways RAM", "The account").

The places are held while the image is written, in the order they are written, which is the
order of their addresses, two words each in the work area from W_SITES: an address, and its type
and region.
"""
import lk_alloc
import lk_boot
import lk_envf
import lk_err
import lk_fix
import lk_name
import lk_out
import lk_scan
import lk_sym
import lk_tab

W_SITES = lk_tab.W_SNAME + 128      # after the slot names (lk_emit, lk_map): free while the
MAX_SITES = (lk_tab.W_OWN - W_SITES) // 2   # image is written, before the map is

T_ADD = 1                           # a high byte: the pages moved are added to it
T_BANK = 2                          # a block's bank
NO_REGION = 0xFF

site_count = 0


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


def dynamic_of(sym, bank):
    """The number among the dynamic regions of the region of the variable or constant sym, if that
    region is dynamic and, unless `bank` (a kind 6 fix-up, which names the region's bank), sym is
    one of its variables not in zero page; else NO_REGION."""
    k = lk_sym.kind_of(sym)
    if (k != lk_sym.VARIABLE and k != lk_sym.CONSTANT) or not lk_sym.is_defined(sym):
        return NO_REGION
    i = rdef_of(lk_sym.row_of(sym))
    if i == lk_scan.MAX_REGION_DEFS or not is_dynamic(lk_scan.rdef_region[i]):
        return NO_REGION
    if not bank and not movable(i):
        return NO_REGION
    return region_index(lk_scan.rdef_region[i])


def begin():
    """Before the image is written: no place held."""
    global site_count
    site_count = 0


def add(t, r, addr):
    global site_count
    if site_count == MAX_SITES:
        lk_err.fail(lk_err.E_SITES)
    lk_tab.set_wk(W_SITES + 2 * site_count, addr)
    lk_tab.set_wk(W_SITES + 2 * site_count + 1, (t << 8) | r)
    site_count += 1


def note(kind, sym, addr):
    """The image's byte at `addr` (a word's first byte) is a fix-up of this kind naming sym: hold
    it if it is the high byte of a dynamic region's variable's address (or the word of one) or a
    block's bank of a dynamic region."""
    r = dynamic_of(sym, kind == lk_fix.K_BANK)
    if r == NO_REGION:
        return
    if kind == lk_fix.K_BANK:
        add(T_BANK, r, addr)
    elif lk_fix.is_word(kind):
        add(T_ADD, r, addr + 1)
    elif kind == lk_fix.K_HIGH or kind == lk_fix.K_REACH_HIGH:
        add(T_ADD, r, addr)


def refuse(kind, sym, user):
    """A fix-up naming sym of this kind is written outside the image (in a bank's file): it may not
    name a dynamic region's variable or map its bank. user is the function or constant it is in."""
    if dynamic_of(sym, kind == lk_fix.K_BANK) != NO_REGION:
        lk_name.fail_in(lk_err.E_DYNAMIC, sym, user)


def check_constants():
    """A dynamic region holds no constant data: it would have to be copied where it goes."""
    for i in range(0, lk_scan.rdef_count):
        d = lk_scan.rdef_def[i]
        if is_dynamic(lk_scan.rdef_region[i]) and lk_tab.is_kept_def(d) \
                and (lk_tab.def_f[d] & lk_tab.D_CONST) != 0:
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


def has_code_area():
    return lk_boot.places_addr <= lk_envf.code_hi


def has_data_area():
    return lk_alloc.data_end <= lk_envf.data_hi - lk_envf.data_lo


def has_more_area():
    return lk_envf.has_more and lk_alloc.more_end <= lk_envf.more_hi - lk_envf.more_lo


def put_areas():
    """The free parts of the code range (from the list on), of `data` and of `more`, each if it is
    not empty."""
    n = 0
    if has_code_area():
        n += 1
    if has_data_area():
        n += 1
    if has_more_area():
        n += 1
    lk_out.put(n)
    if has_code_area():
        lk_out.put_word(lk_boot.places_addr)
        lk_out.put_word(lk_envf.code_hi)
    if has_data_area():
        lk_out.put_word((lk_envf.data_lo + lk_alloc.data_end) & 0xFFFF)
        lk_out.put_word(lk_envf.data_hi)
    if has_more_area():
        lk_out.put_word((lk_envf.more_lo + lk_alloc.more_end) & 0xFFFF)
        lk_out.put_word(lk_envf.more_hi)


def put_sites(t, r):
    """The places of type t of region r, their count first."""
    n = 0
    for i in range(0, site_count):
        if lk_tab.wk(W_SITES + 2 * i + 1) == (t << 8) | r:
            n += 1
    lk_out.put_word(n)
    before = 0
    for i in range(0, site_count):
        if lk_tab.wk(W_SITES + 2 * i + 1) == (t << 8) | r:
            before = put_place(before, lk_tab.wk(W_SITES + 2 * i))


def put_region(r, n):
    """Dynamic region r (its entry in lk_envf), number n among them."""
    lk_out.put(lk_envf.bank_value[lk_envf.region_bank[r] - 1])
    first = 0xFFFF
    past = 0
    for i in range(0, lk_scan.rdef_count):
        if lk_scan.rdef_region[i] == r and movable(i):
            d = lk_scan.rdef_def[i]
            if lk_tab.def_a[d] < first:
                first = lk_tab.def_a[d]
            if lk_tab.def_a[d] + lk_tab.def_b[d] > past:
                past = lk_tab.def_a[d] + lk_tab.def_b[d]
    if past == 0:
        first = 0
    lk_out.put_word(first)
    lk_out.put_word(past - first)
    put_sites(T_ADD, n)
    put_sites(T_BANK, n)


def write_list():
    """After the code in the image: the list ($places)."""
    check_constants()
    lk_out.seek(lk_boot.places_addr)
    lk_out.put_word(lk_envf.code_lo)
    lk_out.put_word(top())
    put_areas()
    n = 0
    for r in range(0, lk_envf.region_count):
        if is_dynamic(r):
            n += 1
    lk_out.put(n)
    n = 0
    for r in range(0, lk_envf.region_count):
        if is_dynamic(r):
            put_region(r, n)
            n += 1
    after = (lk_out.base + lk_out.written) & 0xFFFF     # after the list
    if after - 1 > lk_envf.code_hi:
        lk_err.begin(lk_err.E_CODE_FULL)
        lk_err.over(after - 1 - lk_envf.code_hi, False)
        lk_err.finish()
