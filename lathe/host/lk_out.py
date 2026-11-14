"""The image file: memory from the start of the `code` range to $FFFF, written in address order.

With `output raw` the file ends with the last byte the linker placed, and has no vectors.

A bank or overlay is a file of its own, beside the image (in the directory of OUT.bin), named
by its `bank` or `overlay` entry: the bytes from the window's first address through the last
byte placed in it, the raw form. One file is written at a time.

Nothing of the image is held in memory. Whatever is written must come at or after what was
written before it; the gaps are filled with zeros.
"""
import env
import lk_envf
import lk_err
import lk_file

handle = 0
written = 0                         # bytes written so far: the next address is base + written
base = 0                            # the address of the file's first byte
is_bank = False                     # the file is a bank's or an overlay's


def open_image():
    global handle, written, base, is_bank
    handle = lk_file.open_out(lk_file.ARG_BIN)
    written = 0
    base = lk_envf.code_lo
    is_bank = False


def open_bank(b):
    """Create the file of bank or overlay b, in the directory of the image."""
    global handle, written, base, is_bank
    size = lk_file.arg_length(lk_file.ARG_BIN)
    cut = 0
    for i in range(0, size):
        if env.mem[lk_file.PATH + i] == 47:
            cut = i + 1
    name = lk_envf.bank_file[b]
    for i in range(0, lk_envf.text[name - 1]):
        env.mem[lk_file.PATH + cut + i] = lk_envf.text[name + i]
    env.mem[lk_file.PATH + cut + lk_envf.text[name - 1]] = 0
    handle = env.open_out(lk_file.PATH)
    if handle == 0:
        lk_envf.fail_text(lk_err.E_OPEN, name)
    written = 0
    base = lk_envf.win_lo[lk_envf.bank_win[b]]
    is_bank = True


def put(value8):
    global written
    env.write(handle, value8)
    written = (written + 1) & 0xFFFF


def seek(addr):
    """Fill with zeros up to address addr, which must not be behind what is written."""
    if addr < base or addr - base < written:
        lk_err.fail(lk_err.E_OVERLAP)
    while written != addr - base:
        put(0)


def put_word(value):
    put(value & 0xFF)
    put(value >> 8)


def close_image(reset):
    """Put the address `reset` in the reset vector, fill the image to $FFFF and close it.

    With `output raw`, and for a bank's file, only close it."""
    if lk_envf.raw or is_bank:
        env.close(handle)
        return
    seek(0xFFFC)
    put_word(reset)
    while written != (0 - lk_envf.code_lo) & 0xFFFF:
        put(0)
    env.close(handle)
