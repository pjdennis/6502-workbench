"""Report the variables a Lathe program reads that nothing ever assigns (lathe/docs/language.md,
"Declarations": a variable with no initial value is undefined until the program assigns it).

    python3 lathe/tests/unset_vars.py [--env ENV] [--define NAME[=N]]... FILE.lth...

Each FILE is compiled as a program for ENV (default host) by the host compiler, as build.py
compiles it (not linked), and the object files of every module it links (its own, the run-time's) are read together. A variable of a module
(or a `static` one) is reported when some instruction reads it and none stores to it, nor is its
address taken: no STA, STX, STY or STZ names it, in any module, `$init` included (an initial
value is stored there), and no `#<`, `#>`, reach or constant-data fix-up names it (its address
may be written through). INC, DEC and the shifts read before they write, so they count as reads
only. Prints `MODULE.NAME` for each, and exits with status 1 if there is any.

It is rough, and says only what it can be sure of: it sees no order, so a variable stored
somewhere but read first on some path (a counter that only `+= 1` changes, compiled as a load
and a store) is not reported; and a variable reached only through its address is passed over.
What it reports is a fault on any machine, since memory is not 0 when a program starts. It is a
test tool, not a compiler error: the compiler sees one module at a time, and another module may
assign an exported variable.
"""
import argparse
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LATHE = os.path.dirname(HERE)
for p in (os.path.join(LATHE, 'host'), os.path.join(LATHE, 'host', 'driver')):
    if p not in sys.path:
        sys.path.append(p)

import boards  # noqa: E402
import build  # noqa: E402
import cpu6502  # noqa: E402
import lo  # noqa: E402
import mapenv  # noqa: E402

STORES = ('STA', 'STX', 'STY', 'STZ')
OPERAND = (lo.FX_WORD, lo.FX_SHRINK, lo.FX_ZP)      # the fix-up is an instruction's operand
ESCAPES = (lo.FX_LO, lo.FX_HI, lo.FX_REACH_LO, lo.FX_REACH_HI)


def unset(objects):
    """The names of the variables of the object files that are read and never assigned."""
    defined, read, stored, escaped = set(), set(), set(), set()
    for path in objects:
        m = lo.load(path)
        for item in m.items:
            if isinstance(item, lo.Var):
                defined.add(m.sym_name(item.sym))
            elif isinstance(item, lo.Data):
                escaped.update(m.sym_name(f.sym) for f in item.fixes)
            elif isinstance(item, lo.Func):
                for f in item.fixes:
                    if f.slot != lo.NO_SLOT or m.symbols[f.sym].kind != lo.K_VAR:
                        continue
                    name = m.sym_name(f.sym)
                    if f.kind in ESCAPES:
                        escaped.add(name)
                    elif f.kind in OPERAND:
                        mnemonic = cpu6502.decode(m.cpu, item.code, f.offset - 1)[0]
                        (stored if mnemonic in STORES else read).add(name)
    return sorted((defined & read) - stored - escaped)


def check(source, env='host', defines=()):
    """unset() of the modules the program built from source for env links, with the
    compiler's defines: compiled as build.py compiles them, not linked (so that a program too
    large for an environment is still read)."""
    env = build.env_path(env)
    described = mapenv.read_env(env)
    board = boards.board_for(env)
    work = tempfile.mkdtemp(prefix='lathe-unset-vars-')
    build._building.dirs = [os.path.join(build.RT, d) for d in (board.rt if board else ())]
    try:
        options = build.compiler_options(described, defines)
        order = build.module_order(source)
        main_dir = os.path.dirname(os.path.abspath(source))
        objects = build.compile_all(order, work, options)
        objects += build.compile_implicit(order, work, options, main_dir, described.farcall)
        objects += build.compile_farcall(described, order, objects, work, options, main_dir)
        return unset(objects)
    finally:
        build._building.dirs = []
        shutil.rmtree(work, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--env', default='host')
    parser.add_argument('--define', action='append', default=[], help='NAME or NAME=NUMBER')
    parser.add_argument('files', nargs='+')
    args = parser.parse_args()
    found = False
    for source in args.files:
        for name in check(source, args.env, args.define):
            print(f'{source}: {name} is read and never assigned')
            found = True
    sys.exit(1 if found else 0)


if __name__ == '__main__':
    main()
