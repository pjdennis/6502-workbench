"""The environment file: the CPU, the address ranges, how a program starts and ends, and
(version 2) the windows whose contents are switched and what goes in them.

    cpu       6502          ; or 65c02
    zeropage  $00 $FF       ; first and last address the linker may use
    code      $0200 $BFFF
    data      $C000 $EFFF
    more      data $F810 $FFF9  ; optional: a second range for variables
    stack     $FF           ; optional: the start-up code sets the stack pointer to this
    exit      call $F00F    ; what follows main: or `exit loop`, `exit return`, `exit stop`
    output    image         ; the default: code start to $FFFF with the reset vector; or `raw`

    window    WIN $8000 $EFFF       ; an address range whose contents are switched
    switch    WIN bank $F000 $1F    ; by the bits $1F of the register at $F000; or `overlay`
    bank      WIN 1 $11 LATHE1.BIN  ; bank 1: the register's value, and the file written for it
    overlay   WIN 1 L5OV1.BIN       ; (a window switched by `overlay`) overlay 1 and its file
    place     MODULE WIN 1          ; the module's code goes in bank or overlay 1 of WIN
    region    NAMES WIN 4           ; read and checked; not yet used (`region NAMES fixed` too)
    farcall   rt_bank               ; the run-time module the stubs call (configurations.md)

A window, its banks or overlays and the switch must come before the entries that name them.
Names (windows, modules, regions) are folded to lower case; file names are kept as written.

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
WORDS = (b"cpu zeropage code data stack exit 6502 65c02 call loop return start output image raw stop "
         b"window switch bank overlay place region more farcall fixed ")
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
W_WINDOW = 17
W_SWITCH = 18
W_BANK = 19
W_OVERLAY = 20
W_PLACE = 21
W_REGION = 22
W_MORE = 23
W_FARCALL = 24
W_FIXED = 25

HAVE_ZEROPAGE = 1
HAVE_CODE = 2
HAVE_DATA = 4
HAVE_EXIT = 8
HAVE_CPU = 16
HAVE_STACK = 32
HAVE_OUTPUT = 64
HAVE_MORE = 128
HAVE_FARCALL = 256
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
has_more = False                    # `more data FIRST LAST`
more_lo = 0
more_hi = 0

# Version 2. Names are held in `text`, each as its length and its characters; an entry names
# one by where it is held, + 1 (0: none).
TEXT_SIZE = 384
text = bytearray(TEXT_SIZE)
text_top = 0
farcall = 0                         # the far-call module's name + 1, or 0

SWITCH_NONE = 0
SWITCH_BANK = 1
SWITCH_OVERLAY = 2

MAX_WINDOWS = 4
win_count = 0
win_name = [0] * MAX_WINDOWS
win_lo = [0] * MAX_WINDOWS
win_hi = [0] * MAX_WINDOWS
win_switch = bytearray(MAX_WINDOWS) # SWITCH_
win_reg = [0] * MAX_WINDOWS         # the bank register's address
win_mask = bytearray(MAX_WINDOWS)   # and its bits

MAX_BANKS = 16                      # banks and overlays of all windows together
bank_count = 0
bank_win = bytearray(MAX_BANKS)
bank_n = bytearray(MAX_BANKS)       # its number in its window, 1 to 255
bank_value = bytearray(MAX_BANKS)   # the register value; for an overlay its number
bank_file = [0] * MAX_BANKS         # its file's name + 1, or 0

MAX_PLACES = 32
place_count = 0
place_name = [0] * MAX_PLACES       # a module's name + 1
place_bank = bytearray(MAX_PLACES)  # its bank, and P_LINKED
P_BANK = 0x7F
P_LINKED = 0x80                     # lk_scan: an object file is this module

MAX_REGIONS = 16
region_count = 0
region_name = [0] * MAX_REGIONS
region_bank = bytearray(MAX_REGIONS)    # the bank + 1, or 0 for fixed memory

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
    """Read the next word of the line into token, in lower case. False at the end of the line."""
    return read_word(True)


def read_word(fold):
    """Read the next word of the line into token, in lower case if `fold`. False at the end of
    the line."""
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
        if fold and c >= 65 and c <= 90:
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


# ---- version 2: windows, banks and what goes in them

def end_of_line():
    """Nothing may follow the entry on its line."""
    if read_token():
        bad()


def put_token():
    for i in range(0, token_len):
        lk_err.put(token[i])


def put_text(name):
    """The name held at `name` + 1, as part of an error message."""
    for i in range(1, text[name - 1] + 1):
        lk_err.put(text[name - 1 + i])


def put_bank(b):
    """`WIN N`: bank or overlay b, as part of an error message."""
    put_text(win_name[bank_win[b]])
    lk_err.put(32)
    lk_err.put_number(bank_n[b])


def fail_token(n):
    """Error n about the word just read."""
    lk_err.begin(n)
    lk_err.colon()
    put_token()
    lk_err.finish()


def fail_bank(n, b):
    lk_err.begin(n)
    lk_err.colon()
    put_bank(b)
    lk_err.finish()


def fail_text(n, name):
    lk_err.begin(n)
    lk_err.colon()
    put_text(name)
    lk_err.finish()


def is_token(name):
    """True if the word just read is the name held at `name` + 1."""
    if name == 0 or text[name - 1] != token_len:
        return False
    for i in range(0, token_len):
        if text[name + i] != token[i]:
            return False
    return True


def hold_token():
    """Hold the word just read. Returns where, + 1."""
    global text_top
    if text_top + token_len + 1 > TEXT_SIZE:
        lk_err.fail(lk_err.E_ENV_FULL)
    pos = text_top
    text[pos] = token_len
    for i in range(0, token_len):
        text[pos + 1 + i] = token[i]
    text_top = pos + token_len + 1
    return pos + 1


def name_token():
    """Read a name that must be there."""
    if not read_token():
        bad()


def find_window():
    """The window named by the word just read."""
    for w in range(0, win_count):
        if is_token(win_name[w]):
            return w
    fail_token(lk_err.E_ENV_UNKNOWN)
    return 0


def find_bank(w, n):
    """The bank or overlay n of window w, or MAX_BANKS."""
    for b in range(0, bank_count):
        if bank_win[b] == w and bank_n[b] == n:
            return b
    return MAX_BANKS


def bank_number():
    """A bank's or overlay's number: 1 to 255."""
    n = number()
    if n == 0 or n > 0xFF:
        bad()
    return n


def window_and_bank():
    """Read `WIN N`, which must name a bank or overlay. Returns it."""
    name_token()
    w = find_window()
    n = bank_number()
    b = find_bank(w, n)
    if b == MAX_BANKS:
        lk_err.begin(lk_err.E_ENV_UNKNOWN)
        lk_err.colon()
        put_text(win_name[w])
        lk_err.put(32)
        lk_err.put_number(n)
        lk_err.finish()
    return b


def window_entry():
    global win_count
    name_token()
    for w in range(0, win_count):
        if is_token(win_name[w]):
            fail_token(lk_err.E_ENV_TWICE)
    if win_count == MAX_WINDOWS:
        lk_err.fail(lk_err.E_ENV_FULL)
    w = win_count
    win_count += 1
    win_name[w] = hold_token()
    win_lo[w] = number()
    win_hi[w] = number()
    win_switch[w] = SWITCH_NONE
    end_of_line()


def switch_entry():
    name_token()
    w = find_window()
    if win_switch[w] != SWITCH_NONE:
        fail_token(lk_err.E_ENV_TWICE)
    name_token()
    which = keyword()
    if which == W_BANK:
        win_switch[w] = SWITCH_BANK
        win_reg[w] = number()
        mask = number()
        if mask == 0 or mask > 0xFF:
            bad()
        win_mask[w] = mask
    elif which == W_OVERLAY:
        win_switch[w] = SWITCH_OVERLAY
    else:
        bad()
    end_of_line()


def bank_entry(kind):
    """A `bank` (kind SWITCH_BANK) or `overlay` (SWITCH_OVERLAY) line."""
    global bank_count
    name_token()
    w = find_window()
    if win_switch[w] != kind:
        bad()
    n = bank_number()
    if find_bank(w, n) != MAX_BANKS:
        lk_err.begin(lk_err.E_ENV_TWICE)
        lk_err.colon()
        put_text(win_name[w])
        lk_err.put(32)
        lk_err.put_number(n)
        lk_err.finish()
    if bank_count == MAX_BANKS:
        lk_err.fail(lk_err.E_ENV_FULL)
    b = bank_count
    bank_count += 1
    bank_win[b] = w
    bank_n[b] = n
    bank_value[b] = n
    if kind == SWITCH_BANK:
        value = number()
        if value > 0xFF:
            bad()
        bank_value[b] = value
    bank_file[b] = 0
    if read_word(False):
        bank_file[b] = hold_token()
    elif kind == SWITCH_OVERLAY:
        bad()
    end_of_line()


def place_entry():
    global place_count
    name_token()
    for i in range(0, place_count):
        if is_token(place_name[i]):
            fail_token(lk_err.E_ENV_TWICE)
    if place_count == MAX_PLACES:
        lk_err.fail(lk_err.E_ENV_FULL)
    i = place_count
    place_count += 1
    place_name[i] = hold_token()
    b = window_and_bank()
    if bank_file[b] == 0:
        fail_bank(lk_err.E_NO_FILE, b)
    place_bank[i] = b
    end_of_line()


def region_entry():
    global region_count
    name_token()
    for i in range(0, region_count):
        if is_token(region_name[i]):
            fail_token(lk_err.E_ENV_TWICE)
    if region_count == MAX_REGIONS:
        lk_err.fail(lk_err.E_ENV_FULL)
    i = region_count
    region_count += 1
    region_name[i] = hold_token()
    name_token()
    if keyword() == W_FIXED:
        region_bank[i] = 0
    else:
        w = find_window()
        n = bank_number()
        b = find_bank(w, n)
        if b == MAX_BANKS:
            lk_err.begin(lk_err.E_ENV_UNKNOWN)
            lk_err.colon()
            put_text(win_name[w])
            lk_err.put(32)
            lk_err.put_number(n)
            lk_err.finish()
        region_bank[i] = b + 1
    end_of_line()


def more_entry():
    global has_more, more_lo, more_hi
    once(HAVE_MORE)
    name_token()
    if keyword() != W_DATA:
        bad()
    more_lo = number()
    more_hi = number()
    has_more = True
    end_of_line()


def farcall_entry():
    global farcall
    once(HAVE_FARCALL)
    name_token()
    farcall = hold_token()
    end_of_line()


def overlaps(lo1, hi1, lo2, hi2):
    return not (hi1 < lo2 or hi2 < lo1)


def check_windows():
    """Windows lie above zero page and the stack's page, the right way round, and share no
    address with code, data, more or each other. Code goes in at most one window, the far-call
    module is fixed, and the overlays of a window are numbered from 1 with none missing."""
    ok = True
    for w in range(0, win_count):
        ok = ok and win_lo[w] <= win_hi[w] and win_lo[w] >= 0x100
        ok = ok and not overlaps(win_lo[w], win_hi[w], code_lo, code_hi)
        ok = ok and not overlaps(win_lo[w], win_hi[w], data_lo, data_hi)
        ok = ok and not (has_more and overlaps(win_lo[w], win_hi[w], more_lo, more_hi))
        for v in range(0, w):
            ok = ok and not overlaps(win_lo[w], win_hi[w], win_lo[v], win_hi[v])
    if not ok:
        lk_file.fail(lk_err.E_ENV_RANGE, lk_file.ARG_ENV)
    for w in range(0, win_count):
        if win_switch[w] == SWITCH_OVERLAY:
            count = 0
            for b in range(0, bank_count):
                if bank_win[b] == w:
                    count += 1
            for n in range(1, count + 1):
                if find_bank(w, n) == MAX_BANKS:
                    fail_text(lk_err.E_OVERLAY_NUMBERS, win_name[w])
    for i in range(0, place_count):
        if bank_win[place_bank[i] & P_BANK] != bank_win[place_bank[0] & P_BANK]:
            lk_err.fail(lk_err.E_TWO_WINDOWS)
    if place_count != 0 and farcall == 0:
        lk_err.fail(lk_err.E_FARCALL_MISSING)
    for i in range(0, place_count):
        if text[farcall - 1] == text[place_name[i] - 1]:
            same = True
            for k in range(0, text[farcall - 1]):
                if text[farcall + k] != text[place_name[i] + k]:
                    same = False
            if same:
                fail_text(lk_err.E_FARCALL_PLACED, farcall)


def placed():
    """True if some module's code is placed in a window: the program makes far calls."""
    return place_count != 0


def window():
    """The window code is placed in. Only when placed()."""
    return bank_win[place_bank[0] & P_BANK]


def in_window(addr):
    """True if addr is in the window code is placed in."""
    w = window()
    return addr >= win_lo[w] and addr <= win_hi[w]


def is_overlay():
    """True if the window code is placed in is filled by loading files."""
    return win_switch[window()] == SWITCH_OVERLAY


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
    elif which == W_WINDOW:
        window_entry()
    elif which == W_SWITCH:
        switch_entry()
    elif which == W_BANK:
        bank_entry(SWITCH_BANK)
    elif which == W_OVERLAY:
        bank_entry(SWITCH_OVERLAY)
    elif which == W_PLACE:
        place_entry()
    elif which == W_REGION:
        region_entry()
    elif which == W_MORE:
        more_entry()
    elif which == W_FARCALL:
        farcall_entry()


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
    if has_more:
        ok = ok and more_lo <= more_hi and more_lo >= 0x100
        ok = ok and not overlaps(more_lo, more_hi, code_lo, code_hi)
        ok = ok and not overlaps(more_lo, more_hi, data_lo, data_hi)
    if not ok:
        lk_file.fail(lk_err.E_ENV_RANGE, lk_file.ARG_ENV)
    check_windows()
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
