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

VERSION = 2

# Record types
R_END = 0x00
R_MOD = 0x01
R_IMP = 0x02
R_SYM = 0x03
R_VAR = 0x04
R_DATA = 0x05
R_DFIX = 0x06
R_FUNC = 0x07
R_SLOT = 0x08
R_CALL = 0x09
R_FIX = 0x0A
R_CODE = 0x0B
R_ENDF = 0x0C
R_CLAS = 0x0D
R_MEMB = 0x0E
R_WGT = 0x0F

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

# CLAS flags
CLASS_RECURSIVE = 1

MAX_CALLS = 64
MAX_MEMBERS = 64            # MEMB records of one module
MAX_TABLE = 2048            # bytes of a constant table being made
MAX_TABLE_FIXES = 256         # addresses in one constant table
C_DOT = 0x2E

stream = 0
symbol_count = 0
call_callee = [0] * MAX_CALLS
call_flags = [0] * MAX_CALLS
call_outer = [0] * MAX_CALLS
call_count = 0
member_class = [0] * MAX_MEMBERS    # the MEMB records written, so that each is written once
member_function = [0] * MAX_MEMBERS
member_count = 0
table = bytearray(MAX_TABLE)        # a constant table: its bytes, and its fix-ups, until it ends
table_fix_offset = [0] * MAX_TABLE_FIXES
table_fix_kind = [0] * MAX_TABLE_FIXES
table_fix_symbol = [0] * MAX_TABLE_FIXES
table_fix_slot = [0] * MAX_TABLE_FIXES
table_fix_addend = [0] * MAX_TABLE_FIXES
table_fix_count = 0


def init():
    global symbol_count, call_count, member_count
    symbol_count = 0
    call_count = 0
    member_count = 0


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


def data(symbol_number, length):
    """Begin the constant data `symbol_number`: `length` calls of byte() follow."""
    begin_record(R_DATA, 2 + length)
    kernel.put_word(stream, symbol_number)


def data_byte(value):
    kernel.put(stream, value)


def table_begin(length):
    """Start a constant table of `length` bytes, all 0 until they are given."""
    global table_fix_count
    if length > MAX_TABLE:
        err.fatal(err.E_DATA_FULL)
    for i in range(0, length):
        table[i] = 0
    table_fix_count = 0


def table_fix(offset, kind, symbol_number, slot, addend):
    """Byte `offset` of the table is a byte of an address, which the linker fills in."""
    global table_fix_count
    if table_fix_count == MAX_TABLE_FIXES:
        err.fatal(err.E_DATA_FULL)
    table_fix_offset[table_fix_count] = offset
    table_fix_kind[table_fix_count] = kind
    table_fix_symbol[table_fix_count] = symbol_number
    table_fix_slot[table_fix_count] = slot
    table_fix_addend[table_fix_count] = addend
    table_fix_count += 1


def table_end(symbol_number, length):
    """Write the table as the constant data `symbol_number`, after its fix-ups, which are in
    order of offset: the table is filled element by element, and by column."""
    if table_fix_count != 0:
        begin_record(R_DFIX, 8 * table_fix_count)
        for where in range(0, length):
            for i in range(0, table_fix_count):
                if table_fix_offset[i] == where:
                    kernel.put_word(stream, where)
                    kernel.put(stream, table_fix_kind[i])
                    kernel.put_word(stream, table_fix_symbol[i])
                    kernel.put(stream, table_fix_slot[i])
                    kernel.put_word(stream, table_fix_addend[i])
    data(symbol_number, length)
    for i in range(0, length):
        data_byte(table[i])


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


def pointer_class(symbol_number, flags, count):
    """Describe the pointer class `symbol_number`, which has `count` parameters: as many calls
    of class_parameter() follow, with their sizes in order."""
    begin_record(R_CLAS, 4 + 3 * count)
    kernel.put_word(stream, symbol_number)
    kernel.put(stream, flags)
    kernel.put(stream, count)


def class_parameter(size):
    """A parameter's size, and its name, which is empty: the compiler does not keep the names
    of a function type's parameters."""
    kernel.put_word(stream, size)
    kernel.put(stream, 0)


def member(class_number, function_number):
    """The module takes the address of function `function_number` as pointer class
    `class_number`. Said once, however often it is done."""
    global member_count
    for i in range(0, member_count):
        if member_class[i] == class_number and member_function[i] == function_number:
            return
    if member_count == MAX_MEMBERS:
        err.fatal(err.E_CLASS_MEMBERS_FULL)
    member_class[member_count] = class_number
    member_function[member_count] = function_number
    member_count += 1
    begin_record(R_MEMB, 4)
    kernel.put_word(stream, class_number)
    kernel.put_word(stream, function_number)


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


def weights():
    """A WGT record of the weights FBUF counted for other functions' slots, if it counted any."""
    if fbuf.weight_count == 0:
        return
    begin_record(R_WGT, 4 * fbuf.weight_count)
    for i in range(0, fbuf.weight_count):
        kernel.put_word(stream, fbuf.weight_symbol[i])
        kernel.put(stream, fbuf.weight_slot[i])
        kernel.put(stream, fbuf.weight_value[i])


def function_end():
    """The rest of the function's records: the calls noted, and what FBUF finished."""
    calls()
    fixups()
    code()
    begin_record(R_ENDF, 0)
    weights()


def is_foreign_variable(s):
    """True if kernel symbol `s` is a variable of another module that this one used."""
    return kernel.sym_kind[s] == kernel.K_VAR and kernel.sym_scope[s] != kernel.SCOPE_MODULE \
        and kernel.sym_scope[s] != kernel.SCOPE_LOCAL and kernel.sym_obj[s] != kernel.NO_OBJ \
        and kernel.sym_weight[s] != 0


def foreign_weights():
    """A WGT record of the weight this module's uses gave the variables of other modules, if
    it used any."""
    count = 0
    for s in range(0, kernel.sym_count):
        if is_foreign_variable(s):
            count += 1
    if count == 0:
        return
    begin_record(R_WGT, 4 * count)
    for s in range(0, kernel.sym_count):
        if is_foreign_variable(s):
            kernel.put_word(stream, kernel.sym_obj[s])
            kernel.put(stream, fbuf.NO_SLOT)
            kernel.put(stream, kernel.sym_weight[s])


def end_module():
    """The weights of other modules' variables, and the last record. Closes the file."""
    foreign_weights()
    begin_record(R_END, 0)
    kernel.close(stream)
