"""The host compiler at the capacities of Image B's compiler, the image for machines with no
sideways RAM (script_host.image_b_capacities(): the 32K Model B's with Image B's own where they
differ), with the name heap begun where that compiler begins it on a machine of a given PAGE, as a
program:

    LATHE_PAGE=1F00 python3 lathe/tests/lathec_image_b.py [OPTION]... SOURCE.lth OUTDIR [IMPORTDIR...]

is lathe/host/lathec.py with the host modules' limits set as the twins' constants are with RAM32 1,
ADAPT 1 and SMALL 1, and with kernel.init beginning the heap at PAGE less the heap's address,
$1900, as the twin's init does from OSBYTE 131 (lathe/docs/bbc.md, "The image for machines with no
sideways RAM"): at offset 1 with PAGE $1900 (the default, a DFS machine), at 1,536 with $1F00
(ADFS). So it is the oracle of that compiler on each machine (test_bbc_image_b.py).
LATHE_NAME_START=N begins the heap at offset N instead, whatever the page (test_bbc_rooms.SameObjects).
"""
import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.append(os.path.join(os.path.dirname(HERE), 'host'))

import script_host  # noqa: E402
import env  # noqa: E402
import kernel  # noqa: E402
import lathec  # noqa: E402

HEAP_AT = 0x1900                # `region NAMES fixed $1900` in lathe/src/lathec-bbc.env


def heap_start(page):
    """name_top's first value on a machine whose PAGE is `page`: offset 0 is no name."""
    return max(1, page - HEAP_AT)


def begin_heap_at(start):
    """kernel.init, then the heap begun at offset `start`."""
    plain_init = kernel.init

    def init():
        plain_init()
        kernel.name_top = start
        kernel.local_names = start

    kernel.init = init


if __name__ == '__main__':
    for module, const, size in script_host.image_b_capacities():
        setattr(importlib.import_module(module), const, size)
    if os.environ.get('LATHE_NAME_START'):
        begin_heap_at(int(os.environ['LATHE_NAME_START']))
    else:
        begin_heap_at(heap_start(int(os.environ.get('LATHE_PAGE', '1900'), 16)))
    env.start(sys.argv[1:])
    lathec.main()
