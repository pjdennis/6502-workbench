"""The host compiler, lathe/host/lathec.py, with a name heap of LATHE_NAME_HEAP bytes instead of
kernel.NAME_HEAP_SIZE, and with LATHE_SAVED_TOKENS, room for that many bytes of INLINE's saved
tokens instead of inline.SAVED_SIZE: the capacities the image for every machine with sideways
RAM sets as the compiler starts (lathe/docs/bbc.md, "Capacities set at start-up"), for
test_bbc_rooms.py.

    LATHE_NAME_HEAP=16128 [LATHE_SAVED_TOKENS=1312] python3 lathe/tests/lathec_heap.py ARGS...

and LATHE_CAPACITIES, NAME=SIZE,... of the others Image A sets: `syms` (the rows of the symbol
table and of the members), `buffer` (FBUF's), `table` (OUT's constant table), `string` (LEX's).

With LATHE_NAME_HEAP_NEED=FILE it also writes to FILE the most the heap was asked to hold at the
start of a name (kernel.name_begin's test), so that a test can find the least heap a module
compiles with.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'host'))

import env  # noqa: E402
import fbuf  # noqa: E402
import inline  # noqa: E402
import kernel  # noqa: E402
import lathec  # noqa: E402
import lex  # noqa: E402
import out  # noqa: E402


def symbol_rows(rows):
    """The symbol table and the members with `rows` rows, as kernel lays them out."""
    kernel.MAX_SYMS = kernel.MAX_MEMBERS = rows
    for name in dir(kernel):
        if name.endswith('_AT') and name.startswith(('SCOPE', 'KIND', 'FLAGS', 'TYPE', 'WEIGHT', 'PARAMS',
                                                     'RESULTS', 'NAME', 'VALUE', 'OBJ', 'MEMBERS', 'LINK')):
            column = getattr(kernel, 'C_' + name[:-3])
            setattr(kernel, name, column * rows)
    kernel.SYM_BYTE_SIZE = kernel.BYTE_COLUMNS * rows
    kernel.SYM_WORD_SIZE = kernel.WORD_COLUMNS * rows
    kernel.sym_bytes = bytearray(kernel.SYM_BYTE_SIZE)
    kernel.sym_words = [0] * kernel.SYM_WORD_SIZE
    kernel.member_type = bytearray(rows)
    kernel.member_value = bytearray(rows)
    kernel.thaw_top = rows


def capacities(text):
    for item in text.split(','):
        name, size = item.split('=')
        size = int(size)
        if name == 'syms':
            symbol_rows(size)
        elif name == 'buffer':
            fbuf.BUFFER_SIZE = size
            fbuf.buffer = bytearray(size)
        elif name == 'table':
            out.MAX_TABLE = size
            out.table = bytearray(size)
        elif name == 'string':
            lex.MAX_STRING = size
            lex.string = bytearray(size)
        else:
            raise SystemExit('lathec_heap: no capacity ' + name)

size = int(os.environ['LATHE_NAME_HEAP'])
kernel.NAME_HEAP_SIZE = size
kernel.names = bytearray(size)
if os.environ.get('LATHE_SAVED_TOKENS'):
    inline.SAVED_SIZE = int(os.environ['LATHE_SAVED_TOKENS'])
    assert inline.SAVED_SIZE <= kernel.TOKEN_SIZE
need_file = os.environ.get('LATHE_NAME_HEAP_NEED')
if need_file:
    need = [0]
    name_begin = kernel.name_begin

    def measured_name_begin():
        need[0] = max(need[0], kernel.name_top + kernel.N_TEXT + kernel.MAX_NAME)
        name_begin()

    kernel.name_begin = measured_name_begin
    import atexit

    def write_need():
        with open(need_file, 'w') as f:
            f.write('%d\n' % need[0])

    atexit.register(write_need)
if os.environ.get('LATHE_CAPACITIES'):
    capacities(os.environ['LATHE_CAPACITIES'])
env.start(sys.argv[1:])
lathec.main()
