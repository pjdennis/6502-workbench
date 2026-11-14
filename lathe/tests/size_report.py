"""Code size of the test programs of lathe/src/, read from the maps the linker writes.

    python3 lathe/tests/size_report.py [OUT_DIR] [--all]
    python3 lathe/tests/size_report.py [OUT_DIR] --program NAME... [--all]
    python3 lathe/tests/size_report.py [OUT_DIR] --report
    python3 lathe/tests/size_report.py [OUT_DIR] --linker

With no --program: builds lathe/src/lextest.lth, the measurement program for code generation,
and prints its code bytes per module and its largest functions (the 15 largest; --all, every
one). --program builds the test programs named instead and reports on each in turn: code, constant
data and variables per module, the zero page it uses, and the largest functions.

--report builds every test program and reports on the compiler's modules, each measured over
all of them: a function's size is the largest any map gives it, and a module's is the sum over
every function of it that some program keeps. Its tables are what the maps give, at full size
(regtest, condtest, gentest and asmtest are the small build, the others are not).
Then the lines of each Python module (all, and code only, without
blank lines, comments and docstrings) against the bytes of code, and the ten largest functions.

--linker does the same for the linker's twins (LINKER), over the linker's test programs built with
lathe/src/linker.env, and projects the size of the whole linker from the bytes per line of
Python code of the twins written so far.

OUT_DIR (default: a temporary directory) keeps each build in OUT_DIR/NAME, its objects and map
in OUT_DIR/NAME/work."""
import ast
import io
import os
import sys
import tempfile
import tokenize

import src_support as support
import script_host

LAYERS = ('err', 'kernel', 'src', 'lex')         # measured first, by lextest
MODULES = ('err', 'kernel', 'src', 'lex', 'typetab', 'fold', 'fbuf', 'out', 'reg', 'cond', 'gen',
           'asmblock', 'inline')
TWIN = {'inline': 'inlines'}    # a twin whose module has another name: `inline` is a keyword
PROGRAMS = ('lextest', 'errtest', 'kerneltest', 'srctest', 'typetest', 'foldtest', 'fbuftest',
            'outtest', 'regtest', 'condtest', 'gentest', 'asmtest', 'inlinetest')
SMALL = ('regtest', 'condtest', 'gentest', 'asmtest', 'inlinetest')    # the small build (src_support.build_program)


LINKER = ('lk_err', 'lk_op', 'lk_file', 'lk_rec', 'lk_sym', 'lk_envf', 'lk_tab', 'lk_name', 'lk_scan',
          'lk_out')
LINKER_PROGRAMS = ('lktest1', 'lktest2')
LINKER_LATER = ('lk_win', 'lk_boot', 'lk_graph', 'lk_alloc', 'lk_fix', 'lk_place', 'lk_map', 'lk_emit',
                'link')


def build(name, out_dir, env=None):
    """Build test program NAME in OUT_DIR/NAME, with the environment file `env` or the
    compiler's. Returns its map's path."""
    where = os.path.join(out_dir, name)
    os.makedirs(where, exist_ok=True)
    if env is None:
        support.build_program(name, where, small=name in SMALL)
    else:
        import build as driver
        driver.build(os.path.join(support.SRC, name + '.lth'), os.path.join(where, name + '.bin'),
                     env=env, keep=os.path.join(where, 'work'))
    work = os.path.join(where, 'work')
    return os.path.join(work, [f for f in os.listdir(work) if f.endswith('.map')][0])


def read_map(path):
    """[(kind, address, size, name)] of every line of a map."""
    items = []
    with open(path) as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 4:
                items.append((parts[0], int(parts[1], 16), int(parts[2], 16), parts[3]))
    return items


def module_of(name):
    return name.split('.')[0].split('@')[0]


def sizes(map_path):
    """[(name, size)] of every function in the map (the first report's form)."""
    return [(n, s) for k, a, s, n in read_map(map_path) if k == 'F']


def zero_page(items):
    """Bytes of zero page that some variable, slot or class parameter of the map uses."""
    used = set()
    for kind, address, size, name in items:
        if kind in 'VSC' and address < 0x100:
            used.update(range(address, min(address + size, 0x100)))
    return len(used)


def per_module(items):
    """{module: [code, data, variables]} of a map. Slots are not counted: they are shared."""
    found = {}
    for kind, address, size, name in items:
        m = module_of(name)
        row = found.setdefault(m, [0, 0, 0])
        if kind == 'F':
            row[0] += size
        elif kind == 'D':
            row[1] += size
        elif kind == 'V':
            row[2] += size
    return found


def python_lines(module):
    """(all lines, lines of code) of lathe/host/MODULE.py: code is not blank, not only a
    comment, and not part of a docstring."""
    path = os.path.join(support.LATHE, 'host', module + '.py')
    with open(path) as f:
        text = f.read()
    lines = text.split('\n')
    if lines and lines[-1] == '':
        lines.pop()
    skip = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                skip.update(range(first.lineno, first.end_lineno + 1))
    code_lines = set()
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type not in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                            tokenize.DEDENT, tokenize.ENDMARKER, tokenize.STRING):
            code_lines.update(range(tok.start[0], tok.end[0] + 1))
        elif tok.type == tokenize.STRING and tok.start[0] not in skip:
            code_lines.update(range(tok.start[0], tok.end[0] + 1))
    return len(lines), len(code_lines - skip)


def show_program(name, map_path, show_all):
    items = read_map(map_path)
    rows = per_module(items)
    print('%s: bytes by module' % name)
    print('%-10s %6s %6s %6s' % ('module', 'code', 'data', 'vars'))
    for m in sorted(rows):
        print('%-10s %6d %6d %6d' % (m, *rows[m]))
    total = [sum(r[i] for r in rows.values()) for i in range(3)]
    print('%-10s %6d %6d %6d' % ('total', *total))
    print('zero page used: %d bytes' % zero_page(items))
    funcs = sorted(((s, n) for k, a, s, n in items if k == 'F'), reverse=True)
    for size, fname in funcs if show_all else funcs[:15]:
        print('%6d %s' % (size, fname))
    print()


def report(out_dir):
    maps = {name: read_map(build(name, out_dir)) for name in PROGRAMS}
    function_size = {}
    twins = [TWIN.get(m, m) for m in MODULES]
    for items in maps.values():
        for kind, address, size, name in items:
            if kind == 'F' and module_of(name) in twins and '@' not in name:
                function_size[name] = max(size, function_size.get(name, 0))
    data_size = {}
    var_size = {}
    for items in maps.values():
        for kind, address, size, name in items:
            if kind == 'D':
                data_size[name] = max(size, data_size.get(name, 0))
            elif kind == 'V':
                var_size[name] = max(size, var_size.get(name, 0))

    def total(table, m):
        return sum(s for n, s in table.items() if module_of(n) == m)

    print('Each module over all the test programs (bytes)')
    print('%-9s %6s %6s %6s %6s %6s %6s %6s' % ('module', 'code', 'data', 'vars', 'py', 'py code',
                                                'b/line', 'b/code'))
    sums = [0] * 6
    for m in MODULES:
        twin = TWIN.get(m, m)
        code, data, var = total(function_size, twin), total(data_size, twin), total(var_size, twin)
        lines, code_lines = python_lines(m)
        print('%-9s %6d %6d %6d %6d %6d %6.2f %6.2f' % (m, code, data, var, lines, code_lines,
                                                       code / lines, code / code_lines))
        for i, v in enumerate((code, data, var, lines, code_lines)):
            sums[i] += v
        if m == LAYERS[-1]:
            print('%-9s %6d %6d %6d %6d %6d %6.2f %6.2f' % ('(layers)', *sums[:5], sums[0] / sums[3],
                                                           sums[0] / sums[4]))
    print('%-9s %6d %6d %6d %6d %6d %6.2f %6.2f' % ('total', *sums[:5], sums[0] / sums[3],
                                                   sums[0] / sums[4]))
    print()
    print('Zero page each program uses (bytes)')
    for name, items in maps.items():
        print('%-10s %4d' % (name, zero_page(items)))
    print()
    print('Functions no test program keeps (bytes in the object file, before zero page forms)')
    import lo
    for m in twins:
        for name, items in maps.items():
            path = os.path.join(out_dir, name, 'work', m + '.lo')
            if os.path.exists(path):
                module = lo.load(path)
                break
        for f in module.functions():
            n = module.sym_name(f.sym)
            if n not in function_size:
                print('%6d %s' % (len(f.code), n))
    print()
    print('The ten largest functions')
    for name, size in sorted(function_size.items(), key=lambda x: -x[1])[:10]:
        print('%6d %s' % (size, name))


def linker_report(out_dir):
    """The linker's twins, measured over its test programs."""
    import lo
    env = os.path.join(support.SRC, 'linker.env')
    maps = {name: read_map(build(name, out_dir, env)) for name in LINKER_PROGRAMS}
    function_size = {}
    for items in maps.values():
        for kind, address, size, name in items:
            if kind == 'F' and module_of(name) in LINKER and '@' not in name:
                function_size[name] = max(size, function_size.get(name, 0))
    unkept = {}
    for m in LINKER:
        for name in LINKER_PROGRAMS:
            path = os.path.join(out_dir, name, 'work', m + '.lo')
            if os.path.exists(path):
                module = lo.load(path)
                break
        for f in module.functions():
            n = module.sym_name(f.sym)
            if n not in function_size:
                unkept[n] = len(f.code)
    print("The linker's twins over %s (bytes of code; a function no program keeps counts its"
          % ', '.join(LINKER_PROGRAMS))
    print('written size)')
    print('%-9s %6s %6s %6s %6s %6s' % ('module', 'code', 'py', 'py code', 'b/line', 'b/code'))
    sums = [0, 0, 0]
    for m in LINKER:
        code = sum(sz for n, sz in list(function_size.items()) + list(unkept.items()) if module_of(n) == m)
        lines, code_lines = python_lines(m)
        print('%-9s %6d %6d %6d %6.2f %6.2f' % (m, code, lines, code_lines, code / lines, code / code_lines))
        for i, v in enumerate((code, lines, code_lines)):
            sums[i] += v
    print('%-9s %6d %6d %6d %6.2f %6.2f' % ('total', sums[0], sums[1], sums[2], sums[0] / sums[1],
                                           sums[0] / sums[2]))
    print('not kept by any program: %s' % (' '.join(sorted(unkept)) or '-'))
    later = [python_lines(m) for m in LINKER_LATER]
    later_code = sum(c for _, c in later)
    per = sums[0] / sums[2]
    print('the rest of the linker (%s): %d lines of code; at %.2f bytes a line %d bytes, '
          'so %d in all' % (' '.join(LINKER_LATER), later_code, per, later_code * per,
                            sums[0] + later_code * per))
    print()
    print('The ten largest functions')
    for name, size in sorted(function_size.items(), key=lambda x: -x[1])[:10]:
        print('%6d %s' % (size, name))


def main(argv):
    show_all = '--all' in argv
    programs = []
    if '--program' in argv:
        programs = argv[argv.index('--program') + 1:]
        programs = [p for p in programs if not p.startswith('--')]
        argv = argv[:argv.index('--program')]
    args = [a for a in argv if not a.startswith('--')]
    out_dir = args[0] if args else tempfile.mkdtemp()
    os.makedirs(out_dir, exist_ok=True)
    if '--report' in argv:
        report(out_dir)
        return
    if '--linker' in argv:
        linker_report(out_dir)
        return
    if programs:
        for name in programs:
            show_program(name, build(name, out_dir), show_all)
        return
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
    print('%-10s %6d' % ('layers', sum(per.get(m, 0) for m in LAYERS)))
    print('%-10s %6d' % ('total', sum(per.values())))
    print()
    ranked = sorted(funcs, key=lambda f: -f[1])
    for name, size in ranked if show_all else ranked[:15]:
        print('%6d %s' % (size, name))


if __name__ == '__main__':
    main(sys.argv[1:])
