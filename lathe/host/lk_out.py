"""The image file: memory from the start of the `code` range to $FFFF, written in address order.

Nothing of the image is held in memory. Whatever is written must come at or after what was
written before it; the gaps are filled with zeros.
"""
import env
import lk_envf
import lk_err
import lk_file

handle = 0
written = 0                         # bytes written so far: the next address is code_lo + written


def open_image():
    global handle, written
    handle = lk_file.open_out(lk_file.ARG_BIN)
    written = 0


def put(value8):
    global written
    env.write(handle, value8)
    written = (written + 1) & 0xFFFF


def seek(addr):
    """Fill with zeros up to address addr, which must not be behind what is written."""
    if addr < lk_envf.code_lo or addr - lk_envf.code_lo < written:
        lk_err.fail(lk_err.E_OVERLAP)
    while written != addr - lk_envf.code_lo:
        put(0)


def put_word(value):
    put(value & 0xFF)
    put(value >> 8)


def close_image(reset):
    """Put the address `reset` in the reset vector, fill the image to $FFFF and close it."""
    seek(0xFFFC)
    put_word(reset)
    while written != (0 - lk_envf.code_lo) & 0xFFFF:
        put(0)
    env.close(handle)
