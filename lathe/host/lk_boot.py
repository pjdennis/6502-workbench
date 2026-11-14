"""The code the linker makes itself: `$start` and `$init`, and with code in a window the stubs
and the table of banks or overlays.

`$start` is the first thing in the code range and what the reset vector points at:

    LDX #stack / TXS            if the environment has a `stack` entry
    CLD
    LDA #<$banks / LDX #>$banks / JSR FARCALL.start
                                if code is placed in a window ($overlays for overlays)
    JSR $init                   if there is one
    JSR MAINMODULE.main
    LDA #$00 / JMP addr         for `exit call addr`; a JMP to itself for `exit loop`;
                                RTS for `exit return`; STP ($DB, 65C02) for `exit stop`

`$init` follows it if any module has a function `MODULE.$init`, which is where the compiler
puts a module's initialisers: one JSR for each, in the order of the object files, and an RTS.
A JSR of a function in a window, here or in `$start`, is a JSR of its stub. The stubs follow, and
then the table (lk_win).
"""
import lk_envf
import lk_name
import lk_out
import lk_scan
import lk_sym
import lk_tab
import lk_win

start_addr = 0
start_len = 0
init_addr = 0
init_len = 0                        # 0 if no module has initialisers
table_addr = 0                      # $banks or $overlays
table_len = 0                       # 0 if no code is placed in a window


def is_init(f):
    """True if function f is some module's `$init`: its name ends in `.$init` (lk_name)."""
    return (lk_tab.fn_flags[f] & lk_tab.F_INIT) != 0


def plan():
    """Work out the addresses and sizes of the two. Returns their size together."""
    global start_addr, start_len, init_addr, init_len, table_addr, table_len
    init_len = 0
    for f in range(0, lk_tab.fn_count):
        if is_init(f):
            init_len += 3
    if init_len != 0:
        init_len += 1
    start_len = 4                   # CLD and JSR main
    if lk_envf.has_stack:
        start_len += 3
    table_len = 0
    if lk_envf.placed():
        start_len += 7
        table_len = lk_win.table_size()
    if init_len != 0:
        start_len += 3
    if lk_envf.exit_kind == lk_envf.EXIT_CALL:
        start_len += 5
    elif lk_envf.exit_kind == lk_envf.EXIT_LOOP:
        start_len += 3
    else:
        start_len += 1              # RTS or STP
    start_addr = lk_envf.code_lo
    init_addr = start_addr + start_len
    lk_win.stub_base = init_addr + init_len
    table_addr = lk_win.stub_base + lk_win.STUB_SIZE * lk_win.stub_count
    return start_len + init_len + lk_win.STUB_SIZE * lk_win.stub_count + table_len


def jsr(addr):
    lk_out.put(0x20)
    lk_out.put_word(addr)


def entry(f, ctx):
    """Where fixed code calls function f's copy for context ctx: its stub, if it has one."""
    n = lk_tab.copy_node(f, ctx)
    if lk_win.has_stub(f):
        return lk_win.stub_addr(n)
    return lk_tab.work[lk_tab.W_ADDR + n]


def call_copy(ctx):
    """The address of the copy of FARCALL.call that a stub for context ctx calls: the copy for
    ctx, or the first if the context makes no far call itself."""
    f = lk_sym.row_of(lk_name.fc_call)
    if lk_tab.has_copy(f, ctx):
        return lk_tab.work[lk_tab.W_ADDR + lk_tab.copy_node(f, ctx)]
    return lk_tab.work[lk_tab.W_ADDR + lk_tab.first_node(f)]


def write_stubs():
    """Every stub, in the order of the copies, and the table."""
    for f in range(0, lk_tab.fn_count):
        if lk_win.has_stub(f):
            bank = lk_scan.fn_bank(f) - 1
            for ctx in range(0, lk_tab.ctx_count):
                if lk_tab.has_copy(f, ctx):
                    n = lk_tab.copy_node(f, ctx)
                    jsr(call_copy(ctx))
                    lk_out.put(lk_envf.bank_value[bank])
                    lk_out.put_word((lk_tab.work[lk_tab.W_ADDR + n] - 1) & 0xFFFF)
    w = lk_envf.window()
    lk_out.put_word(lk_envf.win_lo[w])
    lk_out.put(lk_win.table_count)
    entry_size = 3
    if lk_envf.is_overlay():
        entry_size = 2
    name_at = table_addr + 3 + entry_size * lk_win.table_count
    for i in range(0, lk_win.table_count):
        b = lk_win.table_bank(i)
        if not lk_envf.is_overlay():
            lk_out.put(lk_envf.bank_value[b])
        lk_out.put_word(name_at)
        name_at += lk_envf.text[lk_envf.bank_file[b] - 1] + 1
    for i in range(0, lk_win.table_count):
        name = lk_envf.bank_file[lk_win.table_bank(i)]
        for k in range(1, lk_envf.text[name - 1] + 1):
            lk_out.put(lk_envf.text[name - 1 + k])
        lk_out.put(0)


def write(main_fn):
    """Write both to the image. main_fn is the program's main function."""
    lk_out.seek(start_addr)
    if lk_envf.has_stack:
        lk_out.put(0xA2)            # LDX #stack
        lk_out.put(lk_envf.stack)
        lk_out.put(0x9A)            # TXS
    lk_out.put(0xD8)                # CLD
    if table_len != 0:
        lk_out.put(0xA9)            # LDA #<table
        lk_out.put(table_addr & 0xFF)
        lk_out.put(0xA2)            # LDX #>table
        lk_out.put(table_addr >> 8)
        jsr(lk_tab.work[lk_tab.W_ADDR + lk_tab.first_node(lk_sym.row_of(lk_name.fc_start))])
    if init_len != 0:
        jsr(init_addr)
    jsr(entry(main_fn, 0))
    if lk_envf.exit_kind == lk_envf.EXIT_CALL:
        lk_out.put(0xA9)            # LDA #$00
        lk_out.put(0)
        lk_out.put(0x4C)            # JMP addr
        lk_out.put_word(lk_envf.exit_addr)
    elif lk_envf.exit_kind == lk_envf.EXIT_LOOP:
        lk_out.put(0x4C)            # JMP to this JMP
        lk_out.put_word(start_addr + start_len - 3)
    elif lk_envf.exit_kind == lk_envf.EXIT_STOP:
        lk_out.put(0xDB)            # STP
    else:
        lk_out.put(0x60)            # RTS
    if init_len != 0:
        for f in range(0, lk_tab.fn_count):
            if is_init(f):
                jsr(entry(f, 0))
        lk_out.put(0x60)            # RTS
    if table_len != 0:
        write_stubs()
