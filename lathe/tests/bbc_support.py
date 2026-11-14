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
import shutil
import tempfile

import src_support as support
import lathec_support
import script_host
import env

import boards
import build

ENV = os.path.join(support.SRC, 'compiler-bbc.env')
BOARD = boards.BOARDS['bbc']


def build_program(name, out_dir):
    """Build lathe/src/NAME.lth for the BBC into OUT_DIR/NAME.bin (and NAME.bin.inf), the work
    files in OUT_DIR/work. Returns the image's path."""
    image = os.path.join(out_dir, name + '.bin')
    build.build(os.path.join(support.SRC, name + '.lth'), image, env=ENV,
                keep=os.path.join(out_dir, 'work'))
    return image


def run(image, args=(), paths=()):
    """Run an image on the BBC with arguments: (status, output, error output, CPU cycles). The
    arguments whose numbers are in `paths` are files: one that exists is copied into the
    directory of the run, and each is given by its base name; after the run, each such file the
    program wrote is copied back to the path the argument gave."""
    with tempfile.TemporaryDirectory(prefix='lathe-bbc-run-') as disk:
        names, inputs = [], set()
        for n, a in enumerate(map(str, args)):
            if n in paths:
                base = os.path.basename(a)
                if os.path.isfile(a):
                    shutil.copyfile(a, os.path.join(disk, base))
                    inputs.add(base)
                a = base
            names.append(a)
        result = boards.run_mos(BOARD, image, disk, names)
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


def host_run(main, args, cwd=None):
    """main() of a Python twin with program arguments, at the small build's capacities, with its
    error output joined to its output, as on the BBC, in the directory cwd: (status, output)."""
    here = os.getcwd()
    lathec_support.fresh()
    env._out = io.BytesIO()
    env._err = env._out
    status = 0
    try:
        if cwd:
            os.chdir(cwd)
        env.start([str(a) for a in args])
        with small_capacities():
            main()
    except SystemExit as e:
        status = e.code
    finally:
        os.chdir(here)
        out = env._out.getvalue()
        env._err = io.BytesIO()
    return status, out
