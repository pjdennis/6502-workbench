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
import lk_file
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


def copy_name(n):
    """The name of the function copy that is node n."""
    lk_sym.write_name(handle, lk_tab.node_sym(n))
    if lk_tab.is_extra_copy(n):
        put(64)
        decimal(lk_tab.node_ctx[n])


def functions():
    """The F lines, in placement order: the linker's own code, then the copies kept."""
    begin(70, lk_boot.start_addr, lk_boot.start_len)
    for i in range(0, len(START_NAME)):
        put(START_NAME[i])
    put(10)
    if lk_boot.init_len != 0:
        begin(70, lk_boot.init_addr, lk_boot.init_len)
        for i in range(0, len(INIT_NAME)):
            put(INIT_NAME[i])
        put(10)
    for n in range(0, lk_tab.node_count):
        if not lk_tab.node_is_class(n):
            begin(70, lk_tab.node_addr[n], lk_tab.node_len[n])
            copy_name(n)
            if not lk_tab.is_extra_copy(n) and lk_tab.node_ctx[n] != 0:
                put(32)
                decimal(lk_tab.node_ctx[n])
            put(10)


def symbols(kind, letter):
    """The D or V lines of what is kept, in the order the symbols are defined."""
    for d in range(0, lk_tab.def_count):
        s = lk_tab.def_sym[d]
        if lk_sym.kind_of(s) == kind and lk_sym.is_kept(s):
            begin(letter, lk_sym.sym_a[s], lk_sym.sym_b[s])
            lk_sym.write_name(handle, s)
            put(10)


def slot(f, i):
    """The S lines of slot i of kept function f, one per copy. Its name is the pending name."""
    s = lk_tab.fn_slot[f] + i
    for ctx in range(0, lk_tab.ctx_count):
        if lk_tab.has_copy(f, ctx):
            n = lk_tab.copy_node(f, ctx)
            begin(83, lk_alloc.slot_addr(n, i), lk_tab.slot_size[s])
            copy_name(n)
            put(32)
            decimal(i)
            put(32)
            lk_sym.write_pending(handle)
            put(10)
    # Remember the name if this slot is what names a class parameter.
    k, live = lk_tab.member_class(f)
    if live and lk_tab.cls_namer[k] == f + 1 and i < lk_tab.cls_np[k] \
            and lk_tab.cp_name[lk_tab.cls_par[k] + i] == 0:
        lk_tab.cp_name[lk_tab.cls_par[k] + i] = lk_sym.name_keep() + 1


def cparams():
    """The C lines: the parameters of every live class, under each name the class has."""
    for k in range(0, lk_tab.cls_count):
        rep = lk_tab.class_of(k)
        if lk_tab.cls_reach[rep] != 0:
            for i in range(0, lk_tab.cls_np[rep]):
                p = lk_tab.cls_par[rep] + i
                begin(67, lk_tab.cp_addr[p], lk_tab.cp_size[p])
                lk_sym.write_name(handle, lk_tab.cls_sym[k])
                put(32)
                decimal(i)
                put(32)
                if lk_tab.cp_name[p] != 0:
                    lk_sym.write_text(handle, lk_tab.cp_name[p] - 1)
                else:
                    put(112)
                    decimal(i)
                put(10)
