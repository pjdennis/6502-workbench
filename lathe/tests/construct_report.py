"""Where the bytes of a Lathe program's code come from, by the construct that emitted them.

    python3 lathe/tests/construct_report.py OUT_DIR [--build] [--chains N] [--calls N]

Builds the compiler (lathe/src/lathec.lth with lathec-bbc.env) and the linker (link.lth with
linker-bbc.env) with lathe/tests/construct_lathec.py standing in for the host compiler (with
--build, or when OUT_DIR has no build yet), then reads each object file, the tags beside it and
the map, and attributes every byte of every function the map keeps, as placed (after zero page
shrinking), to a construct: the first rule of classify() that matches the chain of compiler functions
on the Python stack when the instruction was added. The report is a table per tool; with --calls N
the N callees with the most bytes at their calls; with
--chains N the N heaviest innermost chains that no rule names (to refine the rules).

A measuring tool (lathe/docs/spikes.md, "Size for a 128 KB ROM: the generated code, measured")."""
import collections
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.realpath(os.path.join(HERE, '..', '..'))
SRC = os.path.join(ROOT, 'lathe', 'src')
sys.path.insert(0, HERE)

import code_listing     # noqa: E402

TOOLS = (('compiler', 'lathec', 'lathec-bbc.env'), ('linker', 'link', 'linker-bbc.env'))
RUNTIME = ('bbc', 'rt_bbc', 'rt_math', 'rt_frame', 'sys', 'disk', 'bbcfs', 'host', 'rt_with')

# (construct, test): the first whose test is true of the chain (innermost first) names it.
# `has(c, name)`: name is somewhere on the chain; `inner(c, names)`: the innermost compiler
# function of GEN, COND, REG, PARTS or EXPR on the chain is one of names.


def has(c, *names):
    return any(n in c for n in names)


def first_of(c, names):
    """The first of c (innermost first) that is in names, or None."""
    for n in c:
        if n in names:
            return n
    return None


def nonreg(c):
    return [n for n in c if not n.startswith('reg.')]


MOVES = ('gen.copy_value', 'gen.store', 'gen.store_pair', 'gen.move', 'gen.to_temporary',
         'gen.zero', 'gen.store_arrow', 'gen.assign', 'gen.leaves', 'gen.hold', 'gen.accept')
ARITHMETIC = ('gen.combine', 'gen.step', 'gen.ripple', 'gen.operate', 'gen.negate', 'gen.complement',
              'gen.shift', 'gen.shift_a', 'gen.shift_bytes', 'gen.shift_copy', 'gen.shift_memory',
              'gen.variable_shift', 'gen.in_place', 'gen.reverse_subtract', 'gen.short_multiply',
              'gen.resolve', 'gen.binary', 'gen.small', 'gen.wraps')
LOOPS = ('parts.step_back', 'expr.for_statement', 'expr.while_statement', 'expr.loop_statement',
         'expr.limit_value', 'parts.compare_limit', 'parts.loop_variable', 'parts.restore_flags')


def classify(c, ins):
    """The construct of an instruction from its chain c (innermost first)."""
    n = nonreg(c)
    top = n[0] if n else ''
    if top.startswith('asmblock.'):
        return 'asm functions and blocks'
    if has(c, 'gen.init_function', 'gen.initial'):
        return 'initial values ($init)'
    if has(c, 'gen.save_frame', 'gen.restore_frame'):
        return 'saving calls: frame push and pop'
    if has(c, 'parts.map_bank', 'parts.unmap_bank'):
        return 'with blocks: map and unmap'
    if top == 'gen.receive':
        return 'function entry: register parameters stored'
    if top in ('gen.ret', 'gen.load_result', 'gen.function_end'):
        return 'return: result to A, X or C; RTS'
    if top == 'gen.call':
        if ins.mnemonic in ('JSR', 'JMP'):
            return 'call: JSR (JMP for a tail call)'
        return 'call: values saved before a call'
    if top == 'gen.load_registers':
        return 'call: register arguments loaded'
    if ins.mnemonic == 'JMP' and c and c[0] == 'reg.branch':
        return 'branches: the JMP of a long branch'
    if 'reg.memory' in c[:3] and 'reg.load_direct' in c[:2] and ins.mnemonic in ('LDX', 'LDY'):
        return 'arrays: index register loaded'
    if 'reg.point' in c[:3] and ins.mnemonic == 'LDY':
        return 'pointers: Y loaded for (zp),Y'
    if has(c, 'gen.element_pointer', 'gen.index_value', 'gen.index', 'gen.array_index'):
        return 'arrays: element address of a big array'
    if has(c, 'gen.to_zero_page') or ('reg.point' in c and top in MOVES + ('',)):
        return 'pointers: copied to a zero page temporary'
    if top in ('cond.equal_bytes', 'cond.equality'):
        return 'comparisons: == and !='
    if top in ('cond.subtract', 'cond.ordering', 'cond.turned', 'cond.arranged', 'cond.compare'):
        return 'comparisons: < <= > >='
    if top in ('cond.value', 'cond.carry', 'cond.make', 'gen.carry', 'gen.as_value'):
        return 'conditions: a bool as a value or in C'
    if top.startswith('cond.') or top in ('gen.test_left', 'gen.test_right', 'gen.jump_false'):
        return 'conditions: branches'
    if top in LOOPS or (top in MOVES and 'expr.for_statement' in n[:4]):
        return 'loops: for, while, loop'
    if top in ('expr.if_statement', 'expr.case_statement', 'expr.case_constants', 'expr.jump_statement',
               'expr.critical_statement'):
        return 'if, case, break: jumps and selectors'
    if top in ('gen.convert', 'gen.sign_extend'):
        return 'conversions'
    if top in ARITHMETIC or has(c, 'gen.library', 'gen.math_function'):
        if has(c, 'gen.library', 'gen.math_function'):
            return 'arithmetic: rt_math call set-up'
        return 'arithmetic: + - & | ^ shifts, INC/DEC'
    if top in MOVES or top == '':
        if has(c, 'expr.argument', 'expr.inline_argument', 'inline.argument_symbol'):
            return 'call: arguments stored in slots'
        return 'moves: assignment and other stores'
    return 'other: ' + top


def build(out_dir):
    for tool, main, env in TOOLS:
        where = os.path.join(out_dir, tool)
        os.makedirs(where, exist_ok=True)
        e = os.path.join(where, main + '.env')
        with open(os.path.join(SRC, env)) as f, open(e, 'w') as g:
            g.write(f.read())
        cmd = [sys.executable, os.path.join(ROOT, 'lathe', 'host', 'driver', 'build.py'),
               os.path.join(SRC, main + '.lth'), '-o', os.path.join(where, main + '.bin'),
               '--env', e, '--keep', os.path.join(where, 'work')]
        environment = dict(os.environ, LATHE_COMPILER=os.path.join(HERE, 'construct_lathec.py'))
        subprocess.run(cmd, check=True, env=environment)


def load(out_dir, tool, main):
    """The program and, for each instruction (by id), its chain."""
    work = os.path.join(out_dir, tool, 'work')
    prog = code_listing.Program(work, os.path.join(work, main + '.map'))
    chains = {}
    tagged = {}
    for name in prog.modules:
        path = os.path.join(work, name + '.tags')
        if not os.path.exists(path):
            continue
        t = json.load(open(path))
        keys = [tuple(k) for k in t['keys']]
        m = prog.modules[name]
        for symbol, rows in t['functions']:
            tagged[m.sym_name(symbol)] = [(o, s, k, keys[key] if key >= 0 else ()) for o, s, k, key in rows]
    for f in prog.functions:
        rows = tagged.get(f.name)
        if rows is None:
            for ins in f.instructions:
                chains[id(ins)] = ('(no tags: ' + f.module.name + ')',)
            continue
        i = 0
        for o, s, k, c in rows:
            while i < len(f.instructions) and f.instructions[i].offset < o + s:
                ins = f.instructions[i]
                chains[id(ins)] = c
                ins.kind = k
                i += 1
    return prog, chains


def callee_of(ins):
    """The function a JSR or JMP calls (through its stub or not), or None for one inside the
    function."""
    if ins.mnemonic not in ('JSR', 'JMP') or ins.target is None or ins.target[2] is not None:
        return None
    if ins.target[1] == ins.function.name:
        return None
    return ins.target[1]


def calls_table(prog, top):
    """Per callee: call sites, and the bytes at them of the JSR, of the register arguments
    loaded just before it and of the stores into its slots; with its entry stores."""
    rows = collections.defaultdict(lambda: [0, 0, 0, 0, 0, collections.Counter()])
    entry = collections.Counter()
    for f in prog.functions:
        run = []
        for ins in f.instructions:
            if ins.construct == 'call: register arguments loaded':
                run.append(ins)
                continue
            callee = callee_of(ins)
            if callee is not None and ins.construct.startswith('call: JSR'):
                r = rows[callee]
                r[0] += 1
                r[1] += ins.placed
                r[2] += sum(i.placed for i in run)
                r[5][' / '.join(shape(i) for i in run)] += 1
            if ins.target is not None and ins.target[2] is not None and ins.target[1] != f.name \
                    and ins.mnemonic in ('STA', 'STX', 'STY'):
                rows[ins.target[1]][3] += ins.placed
            run = []
            if ins.construct == 'function entry: register parameters stored':
                entry[f.name] += ins.placed
    for name in rows:
        rows[name][4] = entry[name]
    order = sorted(rows.items(), key=lambda kv: -(kv[1][1] + kv[1][2] + kv[1][3] + kv[1][4]))
    total = [sum(r[i] for n, r in rows.items()) for i in range(5)]
    print(f'   calls {total[0]}: JSR {total[1]}, register arguments {total[2]}, slot stores '
          f'{total[3]}, entry stores {total[4]}; {len(rows)} callees')
    print('   callee                            calls   JSR  regs slots entry  total  commonest set-up')
    for name, r in order[:top]:
        common = ', '.join(f'{k or "-"} x{v}' for k, v in r[5].most_common(2))
        print(f'   {name:34s}{r[0]:5d}{r[1]:6d}{r[2]:6d}{r[3]:6d}{r[4]:6d}{sum(r[1:5]):7d}  {common}')
    return rows


def shape(ins):
    """An instruction with its operand reduced to its kind: #c, a variable, a slot, a temporary."""
    if ins.target is None:
        if ins.mode == '#':
            return f'{ins.mnemonic} #{ins.operand}'
        return ins.mnemonic
    kind, name, slot, addend = ins.target
    if kind in (2, 3, 7, 8):
        return f'{ins.mnemonic} #addr'
    what = 'temp' if ins.temp else ('slot' if ins.slot_kind is not None else 'var')
    mode = '' if ins.mode in ('abs', 'zp') else ',' + ins.mode.split(',')[-1]
    return f'{ins.mnemonic} {what}{mode}'


def analyse(out_dir, tool, main_name):
    """The program of a tool with every instruction's chain and construct set."""
    prog, chains = load(out_dir, tool, main_name)
    for f in prog.functions:
        for ins in f.instructions:
            ins.chain = chains[id(ins)]
            ins.construct = classify(ins.chain, ins)
    return prog


def main(argv):
    out_dir = argv[0]
    if '--build' in argv or not os.path.isdir(os.path.join(out_dir, 'compiler', 'work')):
        build(out_dir)
    n_chains = int(argv[argv.index('--chains') + 1]) if '--chains' in argv else 0
    n_calls = int(argv[argv.index('--calls') + 1]) if '--calls' in argv else 0
    for tool, main_name, env in TOOLS:
        prog = analyse(out_dir, tool, main_name)
        by = collections.Counter()
        unnamed = collections.Counter()
        total = 0
        for f in prog.functions:
            if f.module.name in RUNTIME:
                continue
            for ins in f.instructions:
                if ins.construct.startswith('other'):
                    unnamed[ins.chain[:4]] += ins.placed
                by[ins.construct] += ins.placed
                total += ins.placed
        runtime = sum(f.size for f in prog.functions if f.module.name in RUNTIME)
        print(f'== {tool}: {total} bytes of code compiled from the tool\'s own modules '
              f'(and {runtime} of the run-time modules, not counted below); '
              f'{len(prog.stubs)} stubs, {sum(s for n, a, s in prog.stubs)} bytes')
        for name, b in by.most_common():
            print(f'{b:7d} {100 * b / total:5.1f}%  {name}')
        for c, b in unnamed.most_common(n_chains):
            print(f'   {b:6d}  {" < ".join(c)}')
        if n_calls:
            calls_table(prog, n_calls)


if __name__ == '__main__':
    main(sys.argv[1:])
