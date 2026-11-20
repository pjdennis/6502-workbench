"""The host compiler, lathe/host/lathec.py, with a name heap of LATHE_NAME_HEAP bytes instead of
kernel.NAME_HEAP_SIZE: the capacity the image for every machine with sideways RAM sets as the
compiler starts (lathe/docs/bbc.md, "Capacities set at start-up"), for test_bbc_rooms.py.

    LATHE_NAME_HEAP=16128 python3 lathe/tests/lathec_heap.py ARGS...

With LATHE_NAME_HEAP_NEED=FILE it also writes to FILE the most the heap was asked to hold at the
start of a name (kernel.name_begin's test), so that a test can find the least heap a module
compiles with.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'host'))

import env  # noqa: E402
import kernel  # noqa: E402
import lathec  # noqa: E402

size = int(os.environ['LATHE_NAME_HEAP'])
kernel.NAME_HEAP_SIZE = size
kernel.names = bytearray(size)
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
env.start(sys.argv[1:])
lathec.main()
