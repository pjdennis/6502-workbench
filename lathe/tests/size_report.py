"""Code size of lathe/src/lextest.lth, the measurement program for code generation: total code
bytes per module and the largest functions, read from the F lines of the linker's map.

    python3 lathe/tests/size_report.py [OUT_DIR] [--all]

Builds lextest into OUT_DIR (default: a temporary directory) the way the tests do, keeping the
work files (the objects, the map). --all lists every function, not only the 15 largest."""
import os
import sys
import tempfile

import src_support as support

MODULES = ('err', 'kernel', 'src', 'lex')     # the ported compiler layers


def sizes(map_path):
    """[(name, size)] of every function in the map."""
    out = []
    with open(map_path) as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 4 and parts[0] == 'F':
                out.append((parts[3], int(parts[2], 16)))
    return out


def main(argv):
    show_all = '--all' in argv
    args = [a for a in argv if a != '--all']
    out_dir = args[0] if args else tempfile.mkdtemp()
    os.makedirs(out_dir, exist_ok=True)
    support.build_program('lextest', out_dir)
    work = os.path.join(out_dir, 'work')
    maps = [f for f in os.listdir(work) if f.endswith('.map')]
    funcs = sizes(os.path.join(work, maps[0]))
    per = {}
    for name, size in funcs:
        mod = name.split('.')[0]
        per[mod] = per.get(mod, 0) + size
    for mod in sorted(per):
        print('%-10s %6d' % (mod, per[mod]))
    print('%-10s %6d' % ('layers', sum(per.get(m, 0) for m in MODULES)))
    print('%-10s %6d' % ('total', sum(per.values())))
    print()
    ranked = sorted(funcs, key=lambda f: -f[1])
    for name, size in ranked if show_all else ranked[:15]:
        print('%6d %s' % (size, name))


if __name__ == '__main__':
    main(sys.argv[1:])
