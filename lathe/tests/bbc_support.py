"""Shared by the tests that run the compiler's test programs on the emulated BBC
(test_bbc_src.py): building one with lathe/src/compiler-bbc.env, running it with *RUN through
the MOS on a directory of files, and running its Python twin the same way.

On the BBC the error output is the output (lathe/rt/bbc.lth), so a twin is run with the two
streams joined (env._err is env._out), and the program's files are named by their base names,
in the directory it runs on; the twin is run in a directory that holds them under the same
names, so that messages naming a file agree."""
import contextlib
import importlib
import io
import os
import re
import shutil
import tempfile

import src_support as support
import lathec_support
import script_host
import env

import boards
import build
import mapenv

ENV = os.path.join(support.SRC, 'compiler-bbc.env')
BANK_ENV = os.path.join(support.SRC, 'compiler-bbc-bank.env')     # the banked build (step 3)
BOARD = boards.BOARDS['bbc']


def build_program(name, out_dir):
    """Build lathe/src/NAME.lth for the BBC into OUT_DIR/NAME.bin (and NAME.bin.inf), the work
    files in OUT_DIR/work. Returns the image's path."""
    image = os.path.join(out_dir, name + '.bin')
    build.build(os.path.join(support.SRC, name + '.lth'), image, env=ENV,
                keep=os.path.join(out_dir, 'work'))
    return image


# The modules with `with` blocks, which compiler-bbc-bank.env keeps fixed, and where bank_env(...,
# kept=True) places them: the linker then keeps in fixed memory only their functions that have
# a block or run inside one (configurations.md, "Functions kept in fixed memory, and read-only
# banks").
KEPT_PLACES = (('kernel', 4), ('lex', 4), ('src', 4), ('fbuf', 5), ('err', 5))


def bank_env(name, path, split=None, kept=False):
    """Write to PATH the environment of test program NAME banked on the BBC: compiler-bbc-bank.env
    with `place NAME WIN 1` before its first `place` line (the test's main module stands with the
    drivers) and without the `place` lines of modules the program does not link (link error 44),
    as src_support.banked_env makes Wendy 2's. With `split`, the address where the fixed variables
    start instead of the file's, and SMALL 0: the full capacities. With `kept`, the modules of
    KEPT_PLACES are placed too. Returns PATH."""
    linked = {n for n, _ in build.module_order(os.path.join(support.SRC, name + '.lth'))}
    lines = []
    placed = False
    with open(BANK_ENV) as f:
        for line in f:
            m = support.PLACE_RE.match(line)
            if m and not placed:
                lines.append('place     %s WIN 1\n' % name)
                placed = True
            if m and m.group(1).lower() not in linked:
                continue
            if kept and re.match(r'region\s', line):
                lines += ['place     %s WIN %d\n' % (m, b) for m, b in KEPT_PLACES if m in linked]
                kept = False
            if split is not None and re.match(r'code\s', line):
                line = 'code      $1900 $%04X\n' % (split - 1)
            if split is not None and re.match(r'data\s', line):
                line = 'data      $%04X $7BFF\n' % split
            if split is not None and re.match(r'define\s+SMALL\s', line):
                line = 'define    SMALL 0 ; the full capacities (bbc_support.bank_env)\n'
            lines.append(line)
    with open(path, 'w') as f:
        f.write(''.join(lines))
    return path


def build_banked(name, out_dir, split=None, kept=False):
    """Build lathe/src/NAME.lth banked for the BBC into OUT_DIR/NAME.bin, its bank files beside
    it, its environment in OUT_DIR/NAME.env (bank_env) and the work files in OUT_DIR/work.
    Returns the image's path, which run() runs with run(..., banked=True). `split`: at the full
    capacities, and `kept` (bank_env)."""
    image = os.path.join(out_dir, name + '.bin')
    env = bank_env(name, os.path.join(out_dir, name + '.env'), split, kept)
    build.build(os.path.join(support.SRC, name + '.lth'), image, env=env,
                keep=os.path.join(out_dir, 'work'))
    return image


def run(image, args=(), paths=(), banked=False):
    """Run an image on the BBC with arguments: (status, output, error output, CPU cycles). The
    arguments whose numbers are in `paths` are files: one that exists is copied into the
    directory of the run, and each is given by its base name; after the run, each such file the
    program wrote is copied back to the path the argument gave. `banked`: an image of
    build_banked, run with the module in RAM and its bank files in the directory."""
    module = None
    with tempfile.TemporaryDirectory(prefix='lathe-bbc-run-') as disk:
        if banked:
            described = mapenv.read_env(os.path.splitext(image)[0] + '.env')
            build.window_files(described, os.path.dirname(os.path.abspath(image)), disk)
            module = boards.module_options(described)
        names, inputs = [], set()
        for n, a in enumerate(map(str, args)):
            if n in paths:
                base = os.path.basename(a)
                if os.path.isfile(a):
                    shutil.copyfile(a, os.path.join(disk, base))
                    inputs.add(base)
                a = base
            names.append(a)
        result = boards.run_mos(BOARD, image, disk, names, module=module)
        for n, a in enumerate(map(str, args)):
            base = os.path.basename(a)
            if n in paths and base not in inputs and os.path.isfile(os.path.join(disk, base)):
                shutil.copyfile(os.path.join(disk, base), a)
        return result


@contextlib.contextmanager
def small_capacities():
    """The host modules with the capacities of the small build (script_host.SMALL)."""
    saved = []
    for module, const, size in script_host.SMALL:
        m = importlib.import_module(module)
        saved.append((m, const, getattr(m, const)))
        setattr(m, const, size)
    try:
        yield
    finally:
        for m, const, size in saved:
            setattr(m, const, size)


def host_run(main, args, cwd=None, small=True):
    """main() of a Python twin with program arguments, at the small build's capacities (or its
    own, without `small`), with its error output joined to its output, as on the BBC, in the
    directory cwd: (status, output)."""
    here = os.getcwd()
    lathec_support.fresh()
    env._out = io.BytesIO()
    env._err = env._out
    status = 0
    try:
        if cwd:
            os.chdir(cwd)
        env.start([str(a) for a in args])
        if small:
            with small_capacities():
                main()
        else:
            main()
    except SystemExit as e:
        status = e.code
    finally:
        os.chdir(here)
        out = env._out.getvalue()
        env._err = io.BytesIO()
    return status, out
