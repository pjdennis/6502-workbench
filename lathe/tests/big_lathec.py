"""A stand-in for lathe/host/lathec.py with a larger name heap and symbol table, for building
the test programs of REG and COND (lathe/tests/test_src_reg.py, test_src_cond.py).

The host compiler cannot compile lathe/src/reg.lth or cond.lth as they are: compiling reg.lth
needs 9059 bytes of the 8192 of kernel.NAME_HEAP_SIZE (error 70) and 578 of the 512 symbols
of kernel.MAX_SYMS (error 71), because every module it imports brings all its exported names
(err alone some 125). The capacities are the same in lathe/src/kernel.lth, so the Lathe
compiler would fail the same way; raising them is a decision about the target's memory, and
is left to be made. Until then the tests build these two modules with this compiler, which is
the host compiler with the tables made larger and nothing else changed (build.py's
LATHE_COMPILER)."""
import os
import sys

HOST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'host')
sys.path.insert(0, HOST)

import kernel  # noqa: E402

NAMES = 16384
SYMS = 1024

kernel.NAME_HEAP_SIZE = NAMES
kernel.names = bytearray(NAMES)
kernel.MAX_SYMS = SYMS
for column in ('sym_name', 'sym_scope', 'sym_kind', 'sym_flags', 'sym_type', 'sym_value', 'sym_obj',
               'sym_weight', 'sym_members', 'sym_params', 'sym_results', 'sym_link'):
    setattr(kernel, column, [0] * SYMS)

import env  # noqa: E402
import lathec  # noqa: E402

if env.is_program(__name__):
    lathec.main()
