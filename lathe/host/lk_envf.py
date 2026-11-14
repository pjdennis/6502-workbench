"""The environment file: the CPU, the three address ranges, and how a program starts and ends.

    cpu       6502          ; or 65c02
    zeropage  $00 $FF       ; first and last address the linker may use
    code      $0200 $BFFF
    data      $C000 $EFFF
    stack     $FF           ; optional: the start-up code sets the stack pointer to this
    exit      call $F00F    ; what follows main: or `exit loop`, `exit return`, `exit stop`
    output    image         ; the default: code start to $FFFF with the reset vector; or `raw`

Entries this version does not know are skipped, because the file is to grow (architecture.md)
and the compiler reads it too. An entry given twice is an error, and so is `start`, which an
earlier version of the file had: the linker makes the start-up code itself now (lk_boot).
`exit stop` (the 65C02's STP) needs `cpu 65c02`, wherever in the file the two are.
"""
import env
import lk_err
import lk_file
import lk_op

# The words the linker knows, each followed by a space; a word's number is its place, from 1.
WORDS = b"cpu zeropage code data stack exit 6502 65c02 call loop return start output image raw stop "
W_CPU = 1
W_ZEROPAGE = 2
W_CODE = 3
W_DATA = 4
W_STACK = 5
W_EXIT = 6
W_6502 = 7
W_65C02 = 8
W_CALL = 9
W_LOOP = 10
W_RETURN = 11
W_START = 12
W_OUTPUT = 13
W_IMAGE = 14
W_RAW = 15
W_STOP = 16

HAVE_ZEROPAGE = 1
HAVE_CODE = 2
HAVE_DATA = 4
HAVE_EXIT = 8
HAVE_CPU = 16
HAVE_STACK = 32
HAVE_OUTPUT = 64
NEEDED = 15                         # the entries a file must have

EXIT_CALL = 1                       # LDA #0 and jump to exit_addr
EXIT_LOOP = 2                       # jump to itself for ever
EXIT_RETURN = 3                     # RTS
EXIT_STOP = 4                       # STP (65C02)

cpu = lk_op.CPU_6502
zp_lo = 0
zp_hi = 0
code_lo = 0
code_hi = 0
data_lo = 0
data_hi = 0
have = 0                            # HAVE_ bits of the entries given
has_stack = False
stack = 0
exit_kind = 0
exit_addr = 0
raw = False                         # `output raw`: the file ends with the last byte placed

TOKEN_SIZE = 64
token = bytearray(TOKEN_SIZE)       # the word being read, in lower case
token_len = 0

handle = 0
cur = 0                             # the character not yet used
at_end = False


def bad():
    lk_file.fail(lk_err.E_ENV_ENTRY, lk_file.ARG_ENV)


def next_char():
    global cur, at_end
    cur, at_end = env.read(handle)


def read_token():
    """Read the next word of the line into token. False at the end of the line."""
    global token_len
    while not at_end and (cur == 32 or cur == 9 or cur == 13):
        next_char()
    if at_end or cur == 10 or cur == 59:
        return False
    token_len = 0
    while not at_end and cur > 32 and cur != 59:
        if token_len == TOKEN_SIZE:
            bad()
        c = cur
        if c >= 65 and c <= 90:
            c += 32
        token[token_len] = c
        token_len += 1
        next_char()
    return True


def skip_line():
    while not at_end and cur != 10:
        next_char()
    if not at_end:
        next_char()


def keyword():
    """The number of the token in WORDS, or 0."""
    number = 1
    i = 0
    while i < len(WORDS):
        k = 0
        while k < token_len and WORDS[i + k] == token[k]:
            k += 1
        if k == token_len and WORDS[i + k] == 32:
            return number
        while WORDS[i] != 32:
            i += 1
        i += 1
        number += 1
    return 0


def digit(c, base):
    """The value of a digit, and whether c is one in this base."""
    if c >= 48 and c <= 57:
        return c - 48, True
    if base == 16 and c >= 97 and c <= 102:
        return c - 87, True
    return 0, False


def number():
    """Read a number: `$` and hex digits, or decimal digits. At most $FFFF."""
    if not read_token():
        bad()
    base = 10
    i = 0
    if token[0] == 36:
        base = 16
        i = 1
    if i == token_len:
        bad()
    value = 0
    while i < token_len:
        d, ok = digit(token[i], base)
        if not ok or value > (0xFFFF - d) // base:
            bad()
        value = value * base + d
        i += 1
    return value


def once(entry_bit):
    """Note that an entry is given; it may be given only once."""
    global have
    if (have & entry_bit) != 0:
        bad()
    have |= entry_bit


def exit_entry():
    """The rest of an `exit` line."""
    global exit_kind, exit_addr
    once(HAVE_EXIT)
    if not read_token():
        bad()
    which = keyword()
    if which == W_CALL:
        exit_kind = EXIT_CALL
        exit_addr = number()
    elif which == W_LOOP:
        exit_kind = EXIT_LOOP
    elif which == W_RETURN:
        exit_kind = EXIT_RETURN
    elif which == W_STOP:
        exit_kind = EXIT_STOP
    else:
        bad()


def output_entry():
    """The rest of an `output` line."""
    global raw
    once(HAVE_OUTPUT)
    if not read_token():
        bad()
    which = keyword()
    if which == W_IMAGE:
        raw = False
    elif which == W_RAW:
        raw = True
    else:
        bad()
    if read_token():
        bad()


def entry():
    """One line whose first word is in token."""
    global cpu, zp_lo, zp_hi, code_lo, code_hi, data_lo, data_hi, has_stack, stack
    which = keyword()
    if which == W_CPU:
        once(HAVE_CPU)
        if not read_token():
            bad()
        which = keyword()
        if which == W_6502:
            cpu = lk_op.CPU_6502
        elif which == W_65C02:
            cpu = lk_op.CPU_65C02
        else:
            bad()
    elif which == W_ZEROPAGE:
        once(HAVE_ZEROPAGE)
        zp_lo = number()
        zp_hi = number()
    elif which == W_CODE:
        once(HAVE_CODE)
        code_lo = number()
        code_hi = number()
    elif which == W_DATA:
        once(HAVE_DATA)
        data_lo = number()
        data_hi = number()
    elif which == W_STACK:
        once(HAVE_STACK)
        stack = number()
        has_stack = True
        if stack > 0xFF:
            bad()
    elif which == W_EXIT:
        exit_entry()
    elif which == W_OUTPUT:
        output_entry()
    elif which == W_START:
        bad()


def check():
    """The entries must be there, and the ranges the right way round and usable."""
    if (have & NEEDED) != NEEDED:
        lk_file.fail(lk_err.E_ENV_MISSING, lk_file.ARG_ENV)
    ok = zp_lo <= zp_hi and zp_hi <= 0xFF and code_lo <= code_hi and data_lo <= data_hi
    # Code below $100 would make the size of an instruction depend on where code is placed.
    ok = ok and code_lo >= 0x100
    # Data below $100 would be zero page that the linker does not count as zero page.
    ok = ok and data_lo >= 0x100
    # Code and data must not share an address.
    ok = ok and (data_hi < code_lo or code_hi < data_lo)
    if not ok:
        lk_file.fail(lk_err.E_ENV_RANGE, lk_file.ARG_ENV)
    if exit_kind == EXIT_STOP and cpu != lk_op.CPU_65C02:
        lk_file.fail(lk_err.E_STOP_6502, lk_file.ARG_ENV)


def read():
    """Read the environment file named by the first argument."""
    global handle
    handle = lk_file.open_in(lk_file.ARG_ENV)
    next_char()
    while not at_end:
        if read_token():
            entry()
        skip_line()
    env.close(handle)
    check()
