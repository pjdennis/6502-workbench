"""The host compiler at the capacities of the tools' 32K form (script_host.ram32_capacities(): the
small build's with RAM32's own where they differ), as a program:

    python3 lathe/tests/lathec_ram32.py [OPTION]... SOURCE.lth OUTDIR [IMPORTDIR...]

is lathe/host/lathec.py with the host modules' limits set as the twins' constants are with
RAM32 1 and SMALL 1 (lathe/docs/bbc.md, "The 32K Model B"), so that it is the oracle of the
compiler's 32K form (test_bbc_ram32.py), and says which modules that form compiles."""
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
    for module, const, size in script_host.ram32_capacities():
        setattr(importlib.import_module(module), const, size)
    env.start(sys.argv[1:])
    lathec.main()
