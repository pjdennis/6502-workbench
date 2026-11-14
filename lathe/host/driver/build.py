#!/usr/bin/env python3
"""Build (and run) a Lathe program.

    python3 lathe/host/driver/build.py SOURCE.lth -o OUT.bin [--env NAME] [--run] [--asm]
                                       [--naive] [--keep DIR] [--define NAME[=NUMBER]]...

1. Finds the modules the program imports: `import NAME` lines; NAME.lth beside SOURCE, then in
   lathe/rt/. Compiles them in dependency order with lathe/host/lathec.py into one directory,
   with the options compiler_options() gives: the environment's `cpu` and `define` entries,
   and each --define.
2. Links with lathe/host/link.py (ENV MAIN OUT.bin OUT.map OBJECTS...), if it exists.
3. With --asm, or when there is no linker: renders the objects and a map as asm17 text
   (lo2asm program mode) and assembles it with asm/pyasm.py. The map is the linker's when there
   is a linker, otherwise (or with --naive) naive.py's allocation.
4. With --run, runs the image on the emulator. With --env host (the default machine) it copies
   the program's output, and the exit status is the program's. With the environment of a board
   (--env michael, --env wendy2; boards.py) it prints the board's LCD, one line per row with
   trailing spaces removed; a run that does not end at the STP of `exit stop` is an error.

--env NAME reads lathe/env/NAME.env (default host); a path to a .env file also works, and runs
on the board of the same name, if there is one.
--keep DIR keeps the objects, map and assembler text in DIR (default: a temporary directory).
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

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


def find_module(name, main_dir):
    for d in (main_dir, RT):
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
    r = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        sys.stderr.buffer.write(r.stdout + r.stderr)
        raise BuildError(f'{what} failed (status {r.returncode})')
    return r


def compiler_options(env=None, defines=()):
    """lathec's options (lathe/host/README.md, "Command lines") for an environment (a
    mapenv.Env, or None for none) and further defines, each NAME or NAME=NUMBER."""
    options = []
    if env is not None:
        options.append('-c65c02' if env.cpu else '-c6502')
        options += ['-d' + name + ('' if value is None else f'={value}') for name, value in env.defines]
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
    compiler. Returns the work directory (removed later unless keep)."""
    work = os.path.abspath(keep) if keep else tempfile.mkdtemp(prefix='lathe-build-')
    os.makedirs(work, exist_ok=True)
    env = env_path(env)
    order = module_order(source)
    main = module_name(source)          # the program is MAIN.main; the linker makes $start call it
    objects = compile_all(order, work, compiler_options(mapenv.read_env(env), defines))
    map_path = os.path.join(work, main + '.map')
    have_linker = os.path.isfile(LINKER) and not use_naive
    if have_linker:
        link_bin = os.path.join(work, main + '.link.bin')
        run([sys.executable, LINKER, env, main, link_bin, map_path] + objects, 'linking')
        if not use_asm:
            shutil.copyfile(link_bin, out)
            return work
    else:
        naive_map(objects, env, main, map_path)
    asm_bin = os.path.join(work, main + '.asm.bin')
    assembler_image(objects, env, main, map_path, os.path.join(work, main + '.asm'), asm_bin)
    shutil.copyfile(asm_bin, out)
    return work


def run_image(image, args=(), stdin=None):
    """Runs an image on the emulator's default machine. Returns (status, stdout bytes, stderr bytes)."""
    if not os.path.isfile(EMULATOR):
        raise BuildError('emulator/emulator.out is missing: run make at the repository root')
    cmd = [EMULATOR, os.path.abspath(image), '--output', '-', '--no-dump'] + list(args)
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, input=stdin)
    # The emulator reports the cycle count on its error output; keep anything else.
    err = b''.join(line for line in r.stderr.splitlines(True) if b' executed ' not in line)
    return r.returncode, r.stdout, err


def run_program(image, env='host', args=(), stdin=None):
    """Runs an image built for environment env: on its board (boards.py), or else on the
    default machine (run_image). Returns (status, output bytes, error output bytes); a board's
    output is its LCD text."""
    board = boards.board_for(env)
    if board is None:
        return run_image(image, args, stdin)
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
    ap.add_argument('--define', action='append', default=[], metavar='NAME[=NUMBER]',
                    help='a constant for #if, as the environment\'s define entries give')
    a = ap.parse_args(argv)
    work = None
    try:
        work = build(a.source, a.out, a.env, a.asm, a.naive, a.keep, defines=a.define)
        if a.run:
            status, out, err = run_program(a.out, a.env)
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
