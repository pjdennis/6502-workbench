"""OUT: the object file writer.

Owns the object file (docs/object-format.md): the stream it is written to, the numbering of
its symbols, and the calls noted for the function being compiled, which are held until the
function ends because its records come after every SYM record its code refers to.

A record is a type byte, the length of its body in two bytes, and the body, so each writer
here works out the length first.
"""
import err
import fbuf
import kernel

VERSION = 1

# Record types
R_END = 0x00
R_MOD = 0x01
R_IMP = 0x02
R_SYM = 0x03
R_VAR = 0x04
R_DATA = 0x05               # not written yet: constant data
R_DFIX = 0x06               # not written yet: fix-ups in data
R_FUNC = 0x07
R_SLOT = 0x08
R_CALL = 0x09
R_FIX = 0x0A
R_CODE = 0x0B
R_ENDF = 0x0C
R_CLAS = 0x0D               # not written yet: pointer classes
R_MEMB = 0x0E               # not written yet: members of pointer classes

# Symbol kinds
SYM_FUNCTION = 1
SYM_VARIABLE = 2
SYM_DATA = 3
SYM_CLASS = 4

# FUNC flags
FUNC_RECURSIVE = 1
FUNC_INTERRUPT = 2
FUNC_EXPORTED = 4
FUNC_REGISTERS = 8

# CALL flags, and the `outer` of a call made while no arguments were being stored
CALL_SAVES = 1
CALL_POINTER = 2
NO_OUTER = 0xFFFF

MAX_CALLS = 64
C_DOT = 0x2E

stream = 0
symbol_count = 0
call_callee = [0] * MAX_CALLS
call_flags = [0] * MAX_CALLS
call_outer = [0] * MAX_CALLS
call_count = 0


def init():
    global symbol_count, call_count
    symbol_count = 0
    call_count = 0


def open(name):
    """Create the object file whose name is at `name`. False if it cannot be created."""
    global stream
    stream, ok = kernel.open_out(name)
    return ok


def begin_record(kind, length):
    """Begin a record whose body is `length` bytes."""
    kernel.put(stream, kind)
    kernel.put_word(stream, length)


def begin_module(cpu, name):
    """The first record: the module's name and the CPU it is compiled for (0 6502, 1 65C02)."""
    begin_record(R_MOD, 3 + kernel.name_length(name))
    kernel.put(stream, VERSION)
    kernel.put(stream, cpu)
    kernel.put_name(stream, name)


def imported(name):
    """The module imports the module called `name`."""
    begin_record(R_IMP, 1 + kernel.name_length(name))
    kernel.put_name(stream, name)


def symbol(kind, module_name, inner, name):
    """Introduce the symbol `module_name.name`, or `module_name.inner.name` if `inner` is a
    name and not 0, which the records after this one may refer to. Returns its number."""
    global symbol_count
    length = kernel.name_length(module_name) + 1 + kernel.name_length(name)
    if inner != 0:
        length += kernel.name_length(inner) + 1
    begin_record(R_SYM, 2 + length)
    kernel.put(stream, kind)
    kernel.put(stream, length)
    put_part(module_name)
    if inner != 0:
        put_part(inner)
    for i in range(0, kernel.name_length(name)):
        kernel.put(stream, kernel.name_char(name, i))
    symbol_count += 1
    return symbol_count - 1


def put_part(name):
    """A name and the dot that follows it in a longer one."""
    for i in range(0, kernel.name_length(name)):
        kernel.put(stream, kernel.name_char(name, i))
    kernel.put(stream, C_DOT)


def variable(symbol_number, size, zp_class, weight):
    """Define a variable that lives for the whole program."""
    begin_record(R_VAR, 7)
    kernel.put_word(stream, symbol_number)
    kernel.put_word(stream, size)
    kernel.put(stream, zp_class)
    kernel.put(stream, weight)
    kernel.put(stream, 0)


def call(callee, flags, outer):
    """Note that the function being compiled calls `callee`. The linker wants each different
    call once, however often the function makes it."""
    global call_count
    for i in range(0, call_count):
        if call_callee[i] == callee and call_flags[i] == flags and call_outer[i] == outer:
            return
    if call_count == MAX_CALLS:
        err.fatal(err.E_CALLS_FULL)
    call_callee[call_count] = callee
    call_flags[call_count] = flags
    call_outer[call_count] = outer
    call_count += 1


def function_begin(symbol_number, flags):
    """Begin the records of a finished function. Its slots follow, then function_end()."""
    begin_record(R_FUNC, 3)
    kernel.put_word(stream, symbol_number)
    kernel.put(stream, flags)


def slot(size, zp_class, weight, kind, name):
    """The next slot of the function's frame."""
    begin_record(R_SLOT, 6 + kernel.name_length(name))
    kernel.put_word(stream, size)
    kernel.put(stream, zp_class)
    kernel.put(stream, weight)
    kernel.put(stream, kind)
    kernel.put_name(stream, name)


def calls():
    global call_count
    for i in range(0, call_count):
        begin_record(R_CALL, 5)
        kernel.put_word(stream, call_callee[i])
        kernel.put(stream, call_flags[i])
        kernel.put_word(stream, call_outer[i])
    call_count = 0


def fixups():
    begin_record(R_FIX, 8 * fbuf.fix_count)
    for i in range(0, fbuf.fix_count):
        kernel.put_word(stream, fbuf.fix_offset[i])
        kernel.put(stream, fbuf.fix_kind[i])
        kernel.put_word(stream, fbuf.fix_symbol[i])
        kernel.put(stream, fbuf.fix_slot[i])
        kernel.put_word(stream, fbuf.fix_addend[i])


def code():
    begin_record(R_CODE, fbuf.code_length)
    for i in range(0, fbuf.code_length):
        kernel.put(stream, fbuf.code[i])


def function_end():
    """The rest of the function's records: the calls noted, and what FBUF finished."""
    calls()
    fixups()
    code()
    begin_record(R_ENDF, 0)


def end_module():
    """The last record. Closes the file."""
    begin_record(R_END, 0)
    kernel.close(stream)
