#!/usr/bin/env python3
"""Build (and run) a Lathe program.

    python3 lathe/host/driver/build.py SOURCE.lth -o OUT.bin [--env NAME] [--run] [--asm]
                                       [--naive] [--keep DIR] [--disk DIR]
                                       [--define NAME[=NUMBER]]...

1. Finds the modules the program imports: `import NAME` lines; NAME.lth beside SOURCE, then in
   lathe/rt/. Compiles them in dependency order with lathe/host/lathec.py into one directory,
   with the options compiler_options() gives: the environment's `cpu` and `define` entries,
   and each --define. Then the modules that the objects import without an `import` line (the
   IMP record the compiler writes for a run-time module its code calls, such as rt_frame),
   found and compiled the same way, after the others.
2. Links with lathe/host/link.py (ENV MAIN OUT.bin OUT.map OBJECTS...), if it exists.
3. With --asm, or when there is no linker: renders the objects and a map as asm17 text
   (lo2asm program mode) and assembles it with asm/pyasm.py. The map is the linker's when there
   is a linker, otherwise (or with --naive) naive.py's allocation.
4. With --run, runs the image on the emulator. With --env host (the default machine) it copies
   the program's output, and the exit status is the program's. With the environment of a board
   (--env michael, --env wendy2; boards.py) it prints the board's LCD, one line per row with
   trailing spaces removed; a run that does not end at the STP of `exit stop` is an error.
   With --env wendy2disk (Wendy 2 with --disk) it runs the program on the files of the
   directory --disk DIR (a temporary, empty one without it; the arguments are in its file
   `args`, one a line), prints the file `out` the program wrote, copies `errors` to the error
   output, and exits with the status in the file `status` (0 if there is none). With --env bbc
   (the BBC Model B+128) the build also writes OUT.bin.inf, the load and execution addresses,
   and --run runs `*RUN NAME` through the MOS on the files of --disk DIR (or a temporary
   directory), prints the output and exits with the program's status (boards.run_mos); a
   banked program (lathe/env/bbc-bank.env) runs with the module in RAM, its bank files in that
   directory.

--env NAME reads lathe/env/NAME.env (default host); a path to a .env file also works, and runs
on the board of the same name, if there is one, or else on the board its `define BOARD` and
`define DISK` entries name (boards.board_for).

An environment that places code in a window (lathe/docs/configurations.md) makes build add the
far-call module its `farcall` entry names, as it adds rt_frame; the linker writes a file for each
bank or overlay, which build copies beside OUT.bin and --run puts where the program reads it
(the --disk directory, or the default machine's working directory). Such a program cannot be
built by the assembler path (--asm).
--keep DIR keeps the objects, map and assembler text in DIR (default: a temporary directory).
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import boards  # noqa: E402
import lo  # noqa: E402
import lo2asm  # noqa: E402
import mapenv  # noqa: E402
import naive  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
LATHE = os.path.join(ROOT, 'lathe')
# LATHE_COMPILER and LATHE_LINKER replace the tools (the tests use a stand-in compiler).
COMPILER = os.environ.get('LATHE_COMPILER') or os.path.join(LATHE, 'host', 'lathec.py')
LINKER = os.environ.get('LATHE_LINKER') or os.path.join(LATHE, 'host', 'link.py')
RT = os.path.join(LATHE, 'rt')
ENVS = os.path.join(LATHE, 'env')
PYASM = os.path.join(ROOT, 'asm', 'pyasm.py')
FARCALL = 'rt_with'    # the module name the compiler gives the far-call module (with blocks)
EMULATOR = os.path.join(ROOT, 'emulator', 'emulator.out')

IMPORT_RE = re.compile(r'^\s*import\s+([A-Za-z_][A-Za-z0-9_]*)', re.IGNORECASE)


class BuildError(Exception):
    pass


def imports_of(path):
    """Module names imported by a source file, in order."""
    out = []
    with open(path, encoding='latin-1') as fh:
        for line in fh:
            m = IMPORT_RE.match(line.split(';', 1)[0])
            if m and m.group(1).lower() not in out:
                out.append(m.group(1).lower())
    return out


# Directories searched between the source's and lathe/rt/: those of the board being built for
# (boards.Board.rt), set by build() while it runs, for its own thread.
_building = threading.local()


def find_module(name, main_dir):
    # The board's directories come before lathe/rt/ also for a source in lathe/rt/ itself.
    first = [] if os.path.abspath(main_dir) == RT else [main_dir]
    for d in first + getattr(_building, 'dirs', []) + [RT]:
        p = os.path.join(d, name + '.lth')
        if os.path.isfile(p):
            return p
    raise BuildError(f'module {name} not found beside the source or in lathe/rt/')


def module_order(source):
    """[(module name, path)] with every module after the modules it imports; main last."""
    main_dir = os.path.dirname(os.path.abspath(source))
    order, state = [], {}

    def visit(name, path, chain):
        if state.get(name) == 'done':
            return
        if state.get(name) == 'active':
            raise BuildError('imports form a cycle: ' + ' -> '.join(chain + [name]))
        state[name] = 'active'
        for dep in imports_of(path):
            visit(dep, find_module(dep, main_dir), chain + [name])
        state[name] = 'done'
        order.append((name, path))

    visit(module_name(source), os.path.abspath(source), [])
    return order


def module_name(path):
    return os.path.splitext(os.path.basename(path))[0].lower()


def env_path(env):
    if os.path.isfile(env):
        return os.path.abspath(env)
    p = os.path.join(ENVS, env + '.env')
    if not os.path.isfile(p):
        raise BuildError(f'environment {env} not found ({p})')
    return p


def run(cmd, what, cwd=None):
    """Run a tool. If it fails, the BuildError says what failed and holds what the tool wrote
    to its error output, such as the compiler's `FILE:LINE:COL: error N: text` or the
    linker's `link error N: text`."""
    r = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        sys.stderr.buffer.write(r.stdout)
        said = r.stderr.decode('latin-1').strip()
        raise BuildError(f'{what} failed (status {r.returncode})' + (f':\n{said}' if said else ''))
    return r


def compiler_options(env=None, defines=()):
    """lathec's options (lathe/host/README.md, "Command lines") for an environment (a
    mapenv.Env, or None for none) and further defines, each NAME or NAME=NUMBER. An environment
    with `define FIXED_REGIONS 1` also gives -fNAME for each of its `region NAME fixed` entries,
    so that the blocks of those regions map nothing (lathe/docs/language.md, "Banked data")."""
    options = []
    if env is not None:
        options.append('-c65c02' if env.cpu else '-c6502')
        options += ['-d' + name + ('' if value is None else f'={value}') for name, value in env.defines]
        told = [value for name, value in env.defines if name.upper() == 'FIXED_REGIONS']
        if told and told[-1] != 0:           # the last define counts; `define FIXED_REGIONS` is true
            options += ['-f' + name for name in env.fixed_regions]
    return options + ['-d' + d for d in defines]


def compile_all(order, outdir, options=()):
    if not os.path.isfile(COMPILER):
        raise BuildError(f'the compiler {os.path.relpath(COMPILER, ROOT)} does not exist yet')
    objects = []
    for name, path in order:
        run([sys.executable, COMPILER] + list(options) + [path, outdir],
            f'compiling {os.path.relpath(path, ROOT)}')
        obj = os.path.join(outdir, name + '.lo')
        if not os.path.isfile(obj):
            raise BuildError(f'the compiler did not write {obj}')
        objects.append(obj)
    return objects


def compile_implicit(order, outdir, options=(), main_dir='.', farcall=None):
    """Compile the modules that the compiled ones import without an `import` line: the
    compiler writes an IMP record for each run-time module its code calls (rt_frame, for the
    calls that save a recursive function's frame; `rt_with`, for `with` blocks, which is the
    environment's far-call module if it names one, and lathe/rt/rt_with.lth if not).
    They are found as imports are, and their own imports with them. Returns their objects,
    which go after the others."""
    return implicit_of([os.path.join(outdir, name + '.lo') for name, _ in order],
                       {name for name, _ in order}, outdir, options, main_dir, farcall)


def implicit_of(waiting, done, outdir, options, main_dir, farcall=None):
    """compile_implicit for the objects `waiting`, with the modules in `done` compiled
    already."""
    objects = []
    while waiting:
        for name in lo.load(waiting.pop(0)).imports:
            if name == FARCALL and farcall:
                name = farcall
            if name not in done:
                more = [(n, p) for n, p in module_order(find_module(name, main_dir)) if n not in done]
                done.update(n for n, _ in more)
                made = compile_all(more, outdir, options)
                objects += made
                waiting += made
    return objects


def compile_farcall(env, order, objects, outdir, options=(), main_dir='.'):
    """The far-call module an environment that places code in a window names (`farcall
    rt_bank`): compiled with its imports, as compile_implicit compiles rt_frame, if the program
    does not already have it. Returns its objects, which go after the others."""
    if not env.banked() or not env.farcall:
        return []
    done = {os.path.splitext(os.path.basename(p))[0] for p in objects}
    if env.farcall in done:
        return []
    more = [(n, p) for n, p in module_order(find_module(env.farcall, main_dir)) if n not in done]
    made = compile_all(more, outdir, options)
    return made + implicit_of(list(made), done | {n for n, _ in more}, outdir, options, main_dir,
                              env.farcall)


def compile_placer(env, objects, outdir, options=(), main_dir='.'):
    """The placer module of an environment with a dynamic region (`placer rt_place`: lathe/host/
    lk_dyn.py), which `$start` calls: compiled with its imports, as the far-call module is, if
    the program does not already have it. Returns its objects, which go after the others."""
    if not env.dynamic_regions or not env.placer:
        return []
    done = {os.path.splitext(os.path.basename(p))[0] for p in objects}
    if env.placer in done:
        return []
    more = [(n, p) for n, p in module_order(find_module(env.placer, main_dir)) if n not in done]
    made = compile_all(more, outdir, options)
    return made + implicit_of(list(made), done | {n for n, _ in more}, outdir, options, main_dir,
                              env.farcall)


def window_files(env, from_dir, to_dir):
    """Copy the files of the banks and overlays (env.files) that the linker wrote in from_dir
    to to_dir."""
    for name in env.files:
        src = os.path.join(from_dir, name)
        if os.path.isfile(src) and os.path.abspath(from_dir) != os.path.abspath(to_dir):
            shutil.copyfile(src, os.path.join(to_dir, name))


def assemble(asm_path, bin_path):
    """asm/pyasm.py, run in the directory of the source (asm17 resolves .include from there)."""
    d = os.path.dirname(os.path.abspath(asm_path))
    run([sys.executable, PYASM, os.path.abspath(asm_path), os.path.abspath(bin_path)],
        f'assembling {asm_path}', cwd=d)


def assembler_image(objects, env, main, map_path, asm_path, bin_path):
    """lo2asm program mode with the map at map_path, then pyasm. Returns the asm text."""
    modules = [lo.load(p) for p in objects]
    text = lo2asm.render_program(modules, mapenv.read_map(map_path), mapenv.read_env(env), main)
    with open(asm_path, 'w') as fh:
        fh.write(text)
    assemble(asm_path, bin_path)
    return text


def naive_map(objects, env, main, map_path):
    modules = [lo.load(p) for p in objects]
    mapenv.write_map(map_path, naive.allocate(modules, mapenv.read_env(env), main))


def build(source, out, env='host', use_asm=False, use_naive=False, keep=None, log=None, defines=()):
    """Builds source into the image out, with further defines (NAME or NAME=NUMBER) for the
    compiler. Returns the work directory (removed later unless keep). Modules are found beside
    source, then in the board's own directories (boards.Board.rt), then in lathe/rt/."""
    env = env_path(env)
    board = boards.board_for(env)
    _building.dirs = [os.path.join(RT, d) for d in (board.rt if board else ())]
    try:
        return build_with(source, out, env, use_asm, use_naive, keep, defines)
    finally:
        _building.dirs = []


def build_with(source, out, env, use_asm, use_naive, keep, defines):
    work = os.path.abspath(keep) if keep else tempfile.mkdtemp(prefix='lathe-build-')
    os.makedirs(work, exist_ok=True)
    order = module_order(source)
    main = module_name(source)          # the program is MAIN.main; the linker makes $start call it
    described = mapenv.read_env(env)
    if described.banked() and (use_asm or use_naive):
        raise BuildError(f'{env} places code or a region in a window: the assembler path renders '
                         f'only programs linked all in one')
    options = compiler_options(described, defines)
    main_dir = os.path.dirname(os.path.abspath(source))
    objects = compile_all(order, work, options)
    objects += compile_implicit(order, work, options, main_dir, described.farcall)
    objects += compile_farcall(described, order, objects, work, options, main_dir)
    objects += compile_placer(described, objects, work, options, main_dir)
    map_path = os.path.join(work, main + '.map')
    have_linker = os.path.isfile(LINKER) and not use_naive
    if have_linker:
        link_bin = os.path.join(work, main + '.link.bin')
        run([sys.executable, LINKER, env, main, link_bin, map_path] + objects, 'linking')
        if not use_asm:
            shutil.copyfile(link_bin, out)
            _built[os.path.abspath(out)] = described
            window_files(described, work, os.path.dirname(os.path.abspath(out)))
            write_inf(out, env, described)
            return work
    else:
        naive_map(objects, env, main, map_path)
    asm_bin = os.path.join(work, main + '.asm.bin')
    assembler_image(objects, env, main, map_path, os.path.join(work, main + '.asm'), asm_bin)
    shutil.copyfile(asm_bin, out)
    _built[os.path.abspath(out)] = described
    write_inf(out, env, described)
    return work


def write_inf(out, env, described):
    """For the BBC (a board with `mos`): OUT.inf beside OUT, the load and execution addresses
    that *RUN reads (boards.inf_text), both the start of the code range."""
    board = boards.board_for(env)
    if board is not None and board.mos:
        with open(out + '.inf', 'w') as fh:
            fh.write(boards.inf_text(boards.bbc_name(out), described.code[0], os.path.getsize(out)))


# The environment of each image build() wrote in this process, by its absolute path, so that
# run_image knows where an image's code range ends (load_file).
_built = {}


def load_file(image, described, where):
    """What the default machine is given to load: an image (`output image`) is code start to
    $FFFF, with 0s where nothing is placed, the data ranges included, and loading it would put
    0s over the memory the emulator filled (boards.FILL). So only the code range is given, in
    the file WHERE, with the reset vector in its last two bytes, which the emulator reads as the
    vector (emulator/README.md, `--load`); those two bytes are the code range's last two, and
    must be unplaced (0 in the image). Returns (the file to load, its load address), or (image,
    None) when the image cannot be cut so: then it is loaded whole, as before."""
    if described is None or described.output != mapenv.OUTPUT_IMAGE:
        return image, None
    lo, hi = described.code
    with open(image, 'rb') as fh:
        data = fh.read()
    if len(data) != 0x10000 - lo or hi - lo < 2 or data[hi - 1 - lo:hi + 1 - lo] != bytes(2):
        return image, None
    with open(where, 'wb') as fh:
        fh.write(data[:hi - 1 - lo] + data[0xFFFC - lo:0xFFFE - lo])
    return where, lo


def run_image(image, args=(), stdin=None, cwd=None, env=None):
    """Runs an image on the emulator's default machine, in the directory cwd (overlays are
    files there), on memory that is not 0 (boards.FILL): only its code range is loaded
    (load_file) if its environment is known (env, a mapenv.Env, or the one build() built it
    with). Returns (status, stdout bytes, stderr bytes)."""
    if not os.path.isfile(EMULATOR):
        raise BuildError('emulator/emulator.out is missing: run make at the repository root')
    with tempfile.TemporaryDirectory(prefix='lathe-load-') as d:
        cmd = image_command(image, env, d) + ['--output', '-', '--no-dump'] + list(args)
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, input=stdin, cwd=cwd)
    # The emulator reports the cycle count on its error output; keep anything else.
    err = b''.join(line for line in r.stderr.splitlines(True) if b' executed ' not in line)
    return r.returncode, r.stdout, err


def image_command(image, env, where):
    """The emulator's command line for an image on the default machine, before the other
    options: the file to load (load_file, in the directory where), --load and boards.FILL."""
    described = env if env is not None else _built.get(os.path.abspath(image))
    path, load = load_file(image, described, os.path.join(where, os.path.basename(image)))
    return ([EMULATOR, os.path.abspath(path)] + (['--load', f'{load:04X}'] if load is not None else [])
            + list(boards.FILL))


def run_program(image, env='host', args=(), stdin=None, disk=None):
    """Runs an image built for environment env: on its board (boards.py), or else on the
    default machine (run_image). Returns (status, output bytes, error output bytes); a board's
    output is its LCD text.

    On a disk board (wendy2disk) the program runs on the files of the directory disk (a
    temporary one if None), which the caller may have filled with input files; args, if any,
    are written to its file `args`, one a line. The output is the file `out`, the error output
    the file `errors` and the status the file `status` (boards.run_disk); any other file the
    program wrote is left in disk for the caller to read."""
    board = boards.board_for(env_path(env))
    described = mapenv.read_env(env_path(env))
    beside = os.path.dirname(os.path.abspath(image))     # where build() left the bank files
    if board is None:
        return run_image(image, args, stdin, beside if described.files else None, described)
    if board.mos:
        if disk is None:
            with tempfile.TemporaryDirectory(prefix='lathe-bbc-') as d:
                return run_program(image, env, args, stdin, d)
        window_files(described, beside, disk)
        return boards.run_mos(board, image, disk, args, stdin,
                              module=boards.module_options(described))[:3]
    if board.disk:
        if disk is None:
            with tempfile.TemporaryDirectory(prefix='lathe-disk-') as d:
                return run_program(image, env, args, stdin, d)
        if args:
            with open(os.path.join(disk, boards.ARGS_FILE), 'wb') as fh:
                fh.write(b''.join(a.encode('latin-1') + b'\n' for a in args))
        window_files(described, beside, disk)
        return boards.run_disk(board, image, described, disk)
    text = boards.run(board, image, mapenv.read_env(env_path(env)))
    return 0, text.encode('latin-1'), b''


def main(argv):
    ap = argparse.ArgumentParser(prog='build.py', description='Build and run a Lathe program.')
    ap.add_argument('source')
    ap.add_argument('-o', dest='out', required=True)
    ap.add_argument('--env', default='host')
    ap.add_argument('--run', action='store_true')
    ap.add_argument('--asm', action='store_true', help='build the image by the assembler path')
    ap.add_argument('--naive', action='store_true', help='naive allocation instead of the linker')
    ap.add_argument('--keep', metavar='DIR')
    ap.add_argument('--disk', metavar='DIR', help='with --env wendy2disk or bbc: the directory of '
                    'the program\'s files, which it reads and writes')
    ap.add_argument('--define', action='append', default=[], metavar='NAME[=NUMBER]',
                    help='a constant for #if, as the environment\'s define entries give')
    a = ap.parse_args(argv)
    work = None
    try:
        work = build(a.source, a.out, a.env, a.asm, a.naive, a.keep, defines=a.define)
        if a.run:
            status, out, err = run_program(a.out, a.env, disk=a.disk)
            sys.stdout.buffer.write(out)
            sys.stdout.flush()
            sys.stderr.buffer.write(err)
            return status
    except (BuildError, boards.RunError, lo.LoError, lo2asm.RenderError, mapenv.FormatError, naive.AllocError, OSError) as e:
        sys.stderr.write(f'build: {e}\n')
        return 1
    finally:
        if work and not a.keep:
            shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
