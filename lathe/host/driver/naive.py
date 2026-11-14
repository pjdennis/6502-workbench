#!/usr/bin/env python3
"""A stand-in for the linker's pass 1: a naive allocation, written as a map file.

    naive.py ENV MAINMODULE OUT.map OBJECT.lo...

Every slot and variable gets its own address: class 0 in zero page, everything else (class 1
and 2, class parameters) in the environment's data range. The code range starts with $start, then
$init if any module has a MODULE.$init function, then every function in file order (so every
MODULE.$init is kept); constant data follows the code. Sizes follow the shrink rule and the
start-up table of object-format.md, so lo2asm's program mode reproduces them.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lo  # noqa: E402
import lo2asm  # noqa: E402
import mapenv  # noqa: E402


class AllocError(Exception):
    pass


class _Range:
    def __init__(self, name, first, last):
        self.name, self.next, self.last = name, first, last

    def take(self, size, what):
        a = self.next
        if a + size - 1 > self.last:
            raise AllocError(f'{self.name} is full: no room for {what} ({size} bytes)')
        self.next += size
        return a


def allocate(modules, env, main_module):
    """Map entries for the program: F lines in placement order, then D, V, S and C."""
    if env.code[0] < 0x100:
        raise AllocError('code must start at $0100 or above')
    zp = _Range('zero page', *env.zeropage)
    data = _Range('the data range', *env.data)
    code = _Range('the code range', *env.code)
    program = lo2asm.Program(modules)
    f_lines, d_lines, v_lines, s_lines, c_lines = [], [], [], [], []
    parts = {}
    items = {}

    for m in modules:
        for x in m.items:
            name = m.sym_name(x.sym) if not isinstance(x, lo.Memb) else None
            if isinstance(x, lo.Func):
                for n, s in enumerate(x.slots):
                    r = zp if s.cls == 0 else data
                    a = r.take(s.size, f'slot {s.name} of {name}')
                    parts[(name, n)] = a
                    s_lines.append(mapenv.MapEntry(mapenv.M_SLOT, a, s.size, name, n, s.name))
            elif isinstance(x, lo.Var):
                r = zp if x.cls == 0 else data
                a = r.take(x.size, name)
                items[name] = a
                v_lines.append(mapenv.MapEntry(mapenv.M_VAR, a, x.size, name))

    for m in modules:
        for x in m.of_type(lo.Clas):
            name = m.sym_name(x.sym)
            if any(e.name == name for e in c_lines):
                continue
            for n, size in enumerate(x.params):
                a = data.take(size, f'parameter {n} of {name}')
                parts[(name, n)] = a
                c_lines.append(mapenv.MapEntry(mapenv.M_CLASS, a, size, name, n, f'p{n}'))

    def resolve(m, fx):
        s = m.symbols[fx.sym]
        if fx.slot == lo.NO_SLOT:
            return items.get(s.name)        # None for code and data: not placed yet, not in zp
        a = parts.get((s.name, fx.slot))
        if a is None:
            raise AllocError(f'{m.name}: {s.name} slot {fx.slot} is not defined by any object')
        return a

    main = f'{main_module}.main'
    if program.func(main) is None:
        raise AllocError(f'no object defines {main}')
    inits = lo2asm.init_functions(program, modules)
    _, size = lo2asm.start_function(env, bool(inits), main, lo2asm.Renderer(program))
    f_lines.append(mapenv.MapEntry(mapenv.M_FUNC, code.take(size, lo2asm.START), size, lo2asm.START))
    if inits:
        _, size = lo2asm.init_function(inits)
        f_lines.append(mapenv.MapEntry(mapenv.M_FUNC, code.take(size, lo2asm.INIT), size, lo2asm.INIT))
    for m in modules:
        for f in m.functions():
            name = m.sym_name(f.sym)
            size = lo2asm.final_size(m, f, resolve)
            f_lines.append(mapenv.MapEntry(mapenv.M_FUNC, code.take(size, name), size, name))
    for m in modules:
        for x in m.of_type(lo.Data):
            name = m.sym_name(x.sym)
            d_lines.append(mapenv.MapEntry(mapenv.M_DATA, code.take(len(x.data), name), len(x.data), name))
    return f_lines + d_lines + v_lines + s_lines + c_lines


def main(argv):
    if len(argv) < 4:
        sys.stderr.write('usage: naive.py ENV MAINMODULE OUT.map OBJECT.lo...\n')
        return 2
    try:
        env = mapenv.read_env(argv[0])
        modules = [lo.load(p) for p in argv[3:]]
        mapenv.write_map(argv[2], allocate(modules, env, argv[1]))
    except (lo.LoError, lo2asm.RenderError, mapenv.FormatError, AllocError, OSError) as e:
        sys.stderr.write(f'naive: {e}\n')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
