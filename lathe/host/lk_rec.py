"""Object files as a stream of records (object-format.md).

The stream reads one object file from its start to its end, a record at a time; the host
interface has no seek. Everything the linker needs before a record comes before it in the file
(a function's fix-ups before its code, those of constant data before the data), so each pass
reads each file once, in order, and one stream is all there is. The one exception: a function
linked for several contexts is written once for each, and the stream goes back to its code, by
the number of the record, for each copy after the first.
"""
import env
import lk_err
import lk_file

# Record types.
R_END = 0
R_MOD = 1
R_IMP = 2
R_SYM = 3
R_VAR = 4
R_DATA = 5
R_DFIX = 6
R_FUNC = 7
R_SLOT = 8
R_CALL = 9
R_FIX = 10
R_CODE = 11
R_ENDF = 12
R_CLAS = 13
R_MEMB = 14
R_WGT = 15

VERSION = 2             # of the object format

handle = 0
cur_object = 0          # object number + 1; 0 when the stream is closed
cur_recno = 0           # records started so far: the number of the current record
cur_left = 0            # bytes of the current record's body not yet read


def open_object(obj):
    """Start the stream at the beginning of object file obj."""
    global handle, cur_object, cur_recno, cur_left
    close()
    handle = lk_file.open_in(lk_file.ARG_OBJECT + obj)
    cur_object = obj + 1
    cur_recno = 0
    cur_left = 0


def close():
    global cur_object
    if cur_object != 0:
        env.close(handle)
        cur_object = 0


def damaged():
    """The file being read does not follow the format."""
    lk_file.fail(lk_err.E_DAMAGED, lk_file.ARG_OBJECT + cur_object - 1)


def raw():
    """The next byte of the file. A file never ends inside a record or before its END record."""
    b, at_end = env.read(handle)
    if at_end:
        damaged()
    return b


def advance():
    """Skip what is left of the current record and start the next. Returns its type."""
    global cur_left, cur_recno
    while cur_left > 0:
        raw()
        cur_left -= 1
    kind = raw()
    low = raw()
    cur_left = low | (raw() << 8)
    cur_recno = (cur_recno + 1) & 0xFFFF
    return kind


def left():
    """Bytes of the current record not yet read."""
    return cur_left


def recno():
    """The number of the current record, counting from 1."""
    return cur_recno


def get_byte():
    """The next byte of the current record."""
    global cur_left
    if cur_left == 0:
        damaged()
    cur_left -= 1
    return raw()


def get_word():
    low = get_byte()
    return low | (get_byte() << 8)


def goto(obj, number):
    """Make record `number` of object obj the current record, unread. Returns its type.

    Going back means reading the file again from the start; that happens only for the second
    and later copies of a function."""
    if cur_object != obj + 1 or cur_recno >= number:
        open_object(obj)
    kind = 0
    while cur_recno < number:
        kind = advance()
    return kind
