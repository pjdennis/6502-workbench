"""Link errors: the numbered messages, and the one way out when linking fails.

A link error is written to the error output as `link error N: text`, followed by the names
involved, and the linker exits with status 1. Nothing catches an error. A message is put together
from begin(), the callers' own names and separators, and end(); fail() is the two in one.
"""
import env

E_USAGE = 1
E_OPEN = 2
E_ENV_ENTRY = 3
E_ENV_MISSING = 4
E_VERSION = 5
E_DAMAGED = 6
E_NEEDS_65C02 = 7
E_OBJECTS = 8
E_SYMBOLS = 9
E_NAMES = 10
E_FUNCTIONS = 11
E_SLOTS = 12
E_CALLS = 13
E_CLASSES = 14
E_COPIES = 15
E_CONTEXTS = 16
E_DUPLICATE = 17
E_UNDEFINED = 18
E_KIND = 19
E_NO_MAIN = 20
E_CYCLE = 21
E_CLASS_CONTEXTS = 22
E_CLASS_DIFFERS = 23
E_MEMBER = 24
E_ZP_FULL = 25
E_DATA_FULL = 26
E_CODE_FULL = 27
E_FIXES = 28
E_FIXUP = 29
E_NOT_ZP = 30
E_NOT_LINKED = 31
E_OVERLAP = 32
E_LOCALS = 33
E_ENV_RANGE = 34
E_MEMBERS = 35
E_DEFS = 36
E_SIZE = 37
E_REFS = 38                         # no longer reported: what fix-ups name is not held
E_STOP_6502 = 39
E_MEMBER_CYCLE = 40
E_WEIGHTS = 41

# One message per line, in the order of the numbers above.
MESSAGES = (
    b"usage: link ENV MAINMODULE OUT.bin OUT.map OBJECT.lo...\n"
    b"cannot open file\n"
    b"environment file: bad entry\n"
    b"environment file: zeropage, code, data and exit must all be given\n"
    b"unsupported object version: this linker reads version 2\n"
    b"object file is damaged\n"
    b"object file needs a 65C02 and the environment has a 6502\n"
    b"too many object files\n"
    b"too many symbols\n"
    b"too many or too long names\n"
    b"too many functions\n"
    b"too many slots\n"
    b"too many calls\n"
    b"too many pointer classes or class parameters\n"
    b"too many functions and copies of functions\n"
    b"too many interrupt functions\n"
    b"symbol defined twice\n"
    b"undefined symbol\n"
    b"symbol used as two kinds of thing\n"
    b"no main function\n"
    b"recursion through a call or function not marked recursive\n"
    b"pointer class called through pointers from two contexts\n"
    b"pointer class declared with different parameters\n"
    b"function does not have the parameters of its pointer class\n"
    b"zero page is full\n"
    b"variables do not fit in the data range\n"
    b"code does not fit in the code range\n"
    b"too many fix-ups in one function or table\n"
    b"bad fix-up\n"
    b"address must be in zero page\n"
    b"call of a function that was not linked\n"
    b"parts of the image overlap\n"
    b"too many symbols in the object files together\n"
    b"environment file: bad address range\n"
    b"too many functions whose address is taken\n"
    b"too many variables and constants\n"
    b"internal error: a function is not the size that was planned\n"
    b"too many symbols named by fix-ups\n"                  # 38: no longer reported
    b"environment file: exit stop needs cpu 65c02\n"
    b"functions of one pointer class share their parameters: one that calls another must be recursive, as must the one it calls, or the function type it calls through\n"
    b"too many weights for slots of functions not read yet\n"
)

PREFIX = b"link error "


def put(ch):
    """One character of a message."""
    env.put_error(ch)


def put_number(n):
    """n in decimal. Error and context numbers are below 1000."""
    if n >= 100:
        put(48 + n // 100)
    if n >= 10:
        put(48 + (n // 10) % 10)
    put(48 + n % 10)


def put_word(n):
    """n, 0 to 65535, in decimal."""
    div = 10000
    started = False
    while div > 1:
        if started or n >= div:
            put(48 + (n // div) % 10)
            started = True
        div = div // 10
    put(48 + n % 10)


OVER_TEXT = b" over"
BYTES_TEXT = b" bytes"
WRAP_TEXT = b", more than 64K in all"


def over(amount, wrapped):
    """After a message about a range that is too small: by how much, or that what it needs
    is more than 16 bits can count."""
    if wrapped:
        for i in range(0, len(WRAP_TEXT)):
            put(WRAP_TEXT[i])
        return
    put(44)
    put(32)
    put_word(amount)
    size = len(BYTES_TEXT)
    if amount == 1:
        size -= 1
    for i in range(0, size):
        put(BYTES_TEXT[i])
    for i in range(0, len(OVER_TEXT)):
        put(OVER_TEXT[i])


def begin(n):
    """Start error n: `link error N: text`."""
    for i in range(0, len(PREFIX)):
        put(PREFIX[i])
    put_number(n)
    put(58)
    put(32)
    i = 0
    line = 1
    while line < n:
        if MESSAGES[i] == 10:
            line += 1
        i += 1
    while MESSAGES[i] != 10:
        put(MESSAGES[i])
        i += 1


def colon():
    """Separates the text from the first name."""
    put(58)
    put(32)


def comma():
    put(44)
    put(32)


def arrow():
    """Separates the functions of a call chain."""
    put(32)
    put(45)
    put(62)
    put(32)


def finish():
    """Finish the message and stop the linker."""
    put(10)
    env.exit(1)


def fail(n):
    """Report error n, which involves no names."""
    begin(n)
    finish()
