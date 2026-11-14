"""Shared by the tests of the Lathe-written compiler (lathe/src/): building one of its programs
with the host tools, and running it on the emulator's default machine with arguments."""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LATHE = os.path.dirname(HERE)
ROOT = os.path.dirname(LATHE)
SRC = os.path.join(LATHE, 'src')
DRIVER = os.path.join(LATHE, 'host', 'driver')
EMULATOR = os.path.join(ROOT, 'emulator', 'emulator.out')
ENV = os.path.join(SRC, 'compiler.env')     # where code and variables go
SMALL_ENV = os.path.join(SRC, 'compiler-small.env')     # the same with SMALL: the small build

if DRIVER not in sys.path:
    sys.path.append(DRIVER)

import build  # noqa: E402

# The emulator ends its error output with this report, after whatever the program wrote there.
# It begins with its echo of the command line, and a line feed once the program has written there.
REPORT = re.compile(rb'(?:Exit code -?\d+; )?[Ee]xecuted (\d+) cycles[^\n]*\n?\Z')


def build_program(name, out_dir, small=False):
    """Build lathe/src/NAME.lth into OUT_DIR/NAME.bin, keeping the work files (the map, the
    objects) in OUT_DIR/work. Returns the image's path. With `small`, the small build
    (compiler-small.env: lathe/host/README.md, "The small build")."""
    image = os.path.join(out_dir, name + '.bin')
    build.build(os.path.join(SRC, name + '.lth'), image, env=SMALL_ENV if small else ENV,
                keep=os.path.join(out_dir, 'work'))
    return image


CYCLE_CAP = 2000000000      # ten times the emulator's own: a source of 64K lines needs more


def run(image, args=(), timeout=60, cwd=None):
    """Run an image with program arguments, in the directory `cwd` if one is given. Returns
    (status, output, error output, cycles): the error output without the emulator's own lines."""
    cmd = [EMULATOR, os.path.abspath(image), '--output', '-', '--no-dump',
           '--cycle-cap', str(CYCLE_CAP)] + [str(a) for a in args]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, cwd=cwd)
    err = r.stderr
    echo = ' '.join(cmd[1:]).encode() + b' '
    if err.startswith(echo):
        err = err[len(echo):]
        if err.startswith(b'\n'):
            err = err[1:]
    m = REPORT.search(err)
    cycles = 0
    if m:
        cycles = int(m.group(1))
        err = err[:m.start()]
    return r.returncode, r.stdout, err, cycles
