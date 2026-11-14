"""The code the linker makes itself: `$start` and `$init`.

`$start` is the first thing in the code range and what the reset vector points at:

    LDX #stack / TXS            if the environment has a `stack` entry
    CLD
    JSR $init                   if there is one
    JSR MAINMODULE.main
    LDA #$00 / JMP addr         for `exit call addr`; a JMP to itself for `exit loop`;
                                RTS for `exit return`; STP ($DB, 65C02) for `exit stop`

`$init` follows it if any module has a function `MODULE.$init`, which is where the compiler
puts a module's initialisers: one JSR for each, in the order of the object files, and an RTS.
"""
import lk_envf
import lk_out
import lk_tab

start_addr = 0
start_len = 0
init_addr = 0
init_len = 0                        # 0 if no module has initialisers


def is_init(f):
    """True if function f is some module's `$init`: its name ends in `.$init` (lk_name)."""
    return (lk_tab.fn_flags[f] & lk_tab.F_INIT) != 0


def plan():
    """Work out the addresses and sizes of the two. Returns their size together."""
    global start_addr, start_len, init_addr, init_len
    init_len = 0
    for f in range(0, lk_tab.fn_count):
        if is_init(f):
            init_len += 3
    if init_len != 0:
        init_len += 1
    start_len = 4                   # CLD and JSR main
    if lk_envf.has_stack:
        start_len += 3
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
    return start_len + init_len


def jsr(addr):
    lk_out.put(0x20)
    lk_out.put_word(addr)


def write(main_fn):
    """Write both to the image. main_fn is the program's main function."""
    lk_out.seek(start_addr)
    if lk_envf.has_stack:
        lk_out.put(0xA2)            # LDX #stack
        lk_out.put(lk_envf.stack)
        lk_out.put(0x9A)            # TXS
    lk_out.put(0xD8)                # CLD
    if init_len != 0:
        jsr(init_addr)
    jsr(lk_tab.work[lk_tab.W_ADDR + lk_tab.copy_node(main_fn, 0)])
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
                jsr(lk_tab.work[lk_tab.W_ADDR + lk_tab.copy_node(f, 0)])
        lk_out.put(0x60)            # RTS
