"""Object files as streams of records (object-format.md).

A stream reads one object file from its start to its end, a record at a time; the host interface
has no seek. The linker therefore reaches a place in a file by the number of the record there,
and uses several streams on the same file where it needs two places at once: a function's
fix-ups come before its code, and the fix-ups of constant data come after the data.
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

MAX_STREAMS = 3
MAIN = 0                # reads every record of the file in order
FIXES = 1               # reads the fix-ups that go with what MAIN or CODES is reading
CODES = 2               # reads a function's code while FIXES reads its fix-ups

st_handle = [0] * MAX_STREAMS
st_object = [0] * MAX_STREAMS       # object number + 1; 0 when the stream is closed
st_recno = [0] * MAX_STREAMS        # records started so far: the number of the current record
st_left = [0] * MAX_STREAMS         # bytes of the current record's body not yet read


def open_object(s, obj):
    """Start stream s at the beginning of object file obj."""
    close(s)
    st_handle[s] = lk_file.open_in(lk_file.ARG_OBJECT + obj)
    st_object[s] = obj + 1
    st_recno[s] = 0
    st_left[s] = 0


def close(s):
    if st_object[s] != 0:
        env.close(st_handle[s])
        st_object[s] = 0


def damaged(s):
    """The file stream s reads does not follow the format."""
    lk_file.fail(lk_err.E_DAMAGED, lk_file.ARG_OBJECT + st_object[s] - 1)


def raw(s):
    """The next byte of the file. A file never ends inside a record or before its END record."""
    b, at_end = env.read(st_handle[s])
    if at_end:
        damaged(s)
    return b


def advance(s):
    """Skip what is left of the current record and start the next. Returns its type."""
    while st_left[s] > 0:
        raw(s)
        st_left[s] -= 1
    kind = raw(s)
    low = raw(s)
    st_left[s] = low | (raw(s) << 8)
    st_recno[s] = (st_recno[s] + 1) & 0xFFFF
    return kind


def left(s):
    """Bytes of the current record not yet read."""
    return st_left[s]


def recno(s):
    """The number of the current record, counting from 1."""
    return st_recno[s]


def get_byte(s):
    """The next byte of the current record."""
    if st_left[s] == 0:
        damaged(s)
    st_left[s] -= 1
    return raw(s)


def get_word(s):
    low = get_byte(s)
    return low | (get_byte(s) << 8)


def goto(s, obj, number):
    """Make record `number` of object obj the current record of s, unread. Returns its type.

    Going back means reading the file again from the start; that happens only for the second
    and later copies of a function."""
    if st_object[s] != obj + 1 or st_recno[s] >= number:
        open_object(s, obj)
    kind = 0
    while st_recno[s] < number:
        kind = advance(s)
    return kind
