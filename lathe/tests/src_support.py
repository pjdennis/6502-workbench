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


def build_program(name, out_dir, small=False, banked=False):
    """Build lathe/src/NAME.lth into OUT_DIR/NAME.bin, keeping the work files (the map, the
    objects) in OUT_DIR/work. Returns the image's path. With `small`, the small build
    (compiler-small.env: lathe/host/README.md, "The small build"). With `banked`, the banked
    build on Wendy 2 (build_banked, below), which run_banked runs."""
    if banked:
        return build_banked(name, out_dir)
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


# ---- The banked build: the test programs on Wendy 2 with code in banks (lathe/host/README.md,
# "The banked build") ----------------------------------------------------------------------

BANK_ENV = os.path.join(SRC, 'compiler-bank.env')       # placement D on Wendy 2 with --disk
BANKED_CYCLE_CAP = 400000000    # oscillator ticks, 2 a CPU cycle: 200 million cycles a run
PLACE_RE = re.compile(r'^place\s+(\w+)\s', re.IGNORECASE)


def banked_env(name, path):
    """Write to PATH the environment of test program NAME banked: compiler-bank.env with
    `place NAME WIN 1` before its first `place` line (the test's main module stands in for the
    front end) and without the `place` lines of modules the program does not link (an unlinked
    placed module is link error 44). Returns PATH."""
    linked = {n for n, _ in build.module_order(os.path.join(SRC, name + '.lth'))}
    lines = []
    placed = False
    with open(BANK_ENV) as f:
        for line in f:
            m = PLACE_RE.match(line)
            if m and not placed:
                lines.append('place     %s WIN 1\n' % name)
                placed = True
            if m and m.group(1).lower() not in linked:
                continue
            lines.append(line)
    with open(path, 'w') as f:
        f.write(''.join(lines))
    return path


def build_banked(name, out_dir):
    """Build lathe/src/NAME.lth banked into OUT_DIR/NAME.bin, its bank files beside it, its
    environment in OUT_DIR/NAME.env (banked_env) and the work files in OUT_DIR/work. Returns
    the image's path, which run_banked() runs."""
    image = os.path.join(out_dir, name + '.bin')
    env = banked_env(name, os.path.join(out_dir, name + '.env'))
    build.build(os.path.join(SRC, name + '.lth'), image, env=env,
                keep=os.path.join(out_dir, 'work'))
    return image


def run_banked(image, args=(), timeout=None):
    """Run an image of build_banked() on Wendy 2 with --disk, in a directory made for the run,
    as run() runs one on the default machine: returns (status, output, error output, CPU
    cycles). An argument that names a file is copied into the directory and given to the
    program by its base name; after the run, each file of the directory that an argument
    names and that was not an input is copied back to the path the argument gave. So the
    program's messages name its files by their base names. `timeout` is not used: the cycle
    cap ends a run that does not stop."""
    import boards
    import dataclasses
    import mapenv
    import shutil
    import tempfile
    env = mapenv.read_env(os.path.splitext(image)[0] + '.env')
    board = dataclasses.replace(boards.BOARDS['wendy2disk'], cycle_cap=BANKED_CYCLE_CAP)
    with tempfile.TemporaryDirectory(prefix='lathe-banked-') as disk:
        build.window_files(env, os.path.dirname(os.path.abspath(image)), disk)
        names, inputs = [], set()
        for a in map(str, args):
            base = os.path.basename(a)
            if os.path.isfile(a):
                shutil.copyfile(a, os.path.join(disk, base))
                inputs.add(base)
            names.append(base)
        with open(os.path.join(disk, boards.ARGS_FILE), 'wb') as f:
            f.write(b''.join(n.encode('latin-1') + b'\n' for n in names))
        report = boards.emulate(board, image, env, disk)
        boards.read_report(board, report)
        for a in map(str, args):
            base = os.path.basename(a)
            if base not in inputs and os.path.isfile(os.path.join(disk, base)):
                shutil.copyfile(os.path.join(disk, base), a)
        m = re.search(r'cpu_cycles=(\d+)', report)
        return (boards.read_status(disk), boards.read_file(disk, boards.OUT_FILE),
                boards.read_file(disk, boards.ERRORS_FILE), int(m.group(1)) if m else 0)
