"""The host compiler at the capacities of the small build (script_host.SMALL), as a program:

    python3 lathe/tests/lathec_small.py [OPTION]... SOURCE.lth OUTDIR [IMPORTDIR...]

is lathe/host/lathec.py with the host modules' limits set as the twins' `#if SMALL` constants
set them (lathe/host/README.md, "The small build"), so that it is the oracle of the Lathe-written
compiler built small (test_src_lathec.py). Each run is a process of its own, as a run of the
compiler on the emulator starts from nothing."""
import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.append(os.path.join(os.path.dirname(HERE), 'host'))

import script_host  # noqa: E402
import env  # noqa: E402
import lathec  # noqa: E402

if __name__ == '__main__':
    for module, const, size in script_host.SMALL:
        setattr(importlib.import_module(module), const, size)
    env.start(sys.argv[1:])
    lathec.main()
