#!/usr/bin/env python3
"""Far calls between banks, counted on the BBC, for choosing which modules of a tool share a bank
(lathe/docs/bbc.md, "The 128 KB module": the tools' banks).

A layout's far calls are not measured by linking it: a layout in fewer banks may not fit them
yet. Instead a copy of the tool is linked with each group of modules (ATOMS) in a bank of its
own, in the developer's form (the module's RAM form, banks $81 to $8D), with a counting rt_bbc:
call() adds one to a counter for each pair (where the call comes from, the bank called), where
the call comes from being the bank in the window if the caller's return address is in it, or
fixed memory. Any layout that keeps each group whole then has as its far calls the sum of the
pairs it does not put in one bank, and the calls from fixed memory, which stay far whatever the
layout. (A tail call, `return f(...)`, reaches a stub by JMP: it is counted against the bank
its caller returns to, which is what back() switches to as well.)

    python3 lathe/tests/farcall_matrix.py [--dir DIR] linker|compiler LINK...

LINK is a link of test_bbc_toolchain (outtest, regtest) or `compiler` or `linker` for the links of
test_bbc_selflink; for the compiler tool, a module of lathe/src for a compile of it. Prints the
matrix and the far calls of the layouts in LAYOUTS. matrix(), far_calls() and LAYOUTS are what
test_bbc_rom128.py's report uses.
"""
import argparse
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import src_support as support  # noqa: E402
import test_bbc_selfhost as selfhost  # noqa: E402
import test_bbc_toolchain as chain  # noqa: E402
import boards  # noqa: E402
import build  # noqa: E402
import mapenv  # noqa: E402

FIXED = 'fixed'

# The groups of modules, each in a bank of its own for counting, numbered from 1 in this order.
ATOMS = {
    'linker': [['link', 'lk_err', 'lk_file'], ['lk_envf'], ['lk_scan'], ['lk_name'], ['lk_graph'],
               ['lk_win'], ['lk_boot'], ['lk_alloc'], ['lk_place'], ['lk_fix'], ['lk_map'],
               ['lk_emit'], ['lk_out', 'lk_op']],
    'compiler': [['expr'], ['gen'], ['lathec'], ['decl'], ['parts', 'out'], ['reg'], ['inlines'],
                 ['asmblock'], ['cond'], ['fold', 'typetab'], ['kernel', 'lex', 'fbuf', 'src', 'err']],
}

# Layouts, module -> bank (FIXED: in fixed memory). A module not named keeps the bank or the fixed
# place the tool's own environment gives it.
LAYOUTS = {
    'linker': {
        'five banks (linker-bbc.env)': {
            'link': 1, 'lk_err': 1, 'lk_file': 1, 'lk_envf': 1, 'lk_scan': 2, 'lk_name': 2,
            'lk_graph': 3, 'lk_win': 3, 'lk_boot': 3, 'lk_alloc': 4, 'lk_op': 5, 'lk_fix': 5,
            'lk_place': 5, 'lk_map': 5, 'lk_emit': 5, 'lk_out': 5},
        'three banks (linker-bbc.env, ROM128)': {
            'link': 1, 'lk_err': 1, 'lk_file': 1, 'lk_envf': 1, 'lk_win': 1, 'lk_place': 1,
            'lk_fix': 1, 'lk_emit': 1, 'lk_scan': 2, 'lk_name': 2, 'lk_boot': 2, 'lk_map': 2,
            'lk_graph': 3, 'lk_alloc': 3, 'lk_out': FIXED, 'lk_op': FIXED},
    },
    'compiler': {
        'five banks (lathec-bbc.env)': {
            'expr': 1, 'gen': 2, 'lathec': 2, 'decl': 3, 'parts': 3, 'out': 3, 'reg': 4,
            'inlines': 4, 'typetab': 5, 'asmblock': 5, 'cond': 5, 'fold': 5, 'kernel': 5,
            'lex': 5, 'fbuf': 5, 'src': 5, 'err': 5},
    },
}
TOOL_ENV = {'linker': ('link.lth', 'linker-bbc.env', 'LLINK'),
            'compiler': ('lathec.lth', 'lathec-bbc.env', 'LATHE')}

COUNTING_CALL = '''  STA stub+1
  STX cnt_x                         ; the far call's pair, for farcall_matrix.py
  LDA $0105,X                       ; the caller's return address, high
  BMI .cbank
  LDY #$01
  LDA (stub),Y
  AND #$0F
  TAX
  INC bbc.fx_lo,X
  BNE .cdone
  INC bbc.fx_mid,X
  BNE .cdone
  INC bbc.fx_hi,X
  JMP .cdone
.cbank
  LDA now
  ASL
  ASL
  ASL
  ASL
  STA cnt_row
  LDY #$01
  LDA (stub),Y
  AND #$0F
  ORA cnt_row
  TAX
  INC bbc.mx_lo,X
  BNE .cdone
  INC bbc.mx_mid,X
  BNE .cdone
  INC bbc.mx_hi,X
.cdone
  LDX cnt_x
'''

COUNTING_EXIT = '''  var h: byte
  var k: byte
  h = open_out(argv(%d))             ; the far calls by pair, for farcall_matrix.py
  k = 0
  loop
    write(mx_hi[k], h)
    write(mx_mid[k], h)
    write(mx_lo[k], h)
    k += 1
    if k == 0 then
      break
    end
  end
  for k = 0 until 16 do
    write(fx_hi[k], h)
    write(fx_mid[k], h)
    write(fx_lo[k], h)
  end
  close(h)
  osfind_close(0, 0)                ; every file
'''

COUNTERS = ('\npub var mx_lo: [256]byte\npub var mx_mid: [256]byte\npub var mx_hi: [256]byte\n'
            'pub var fx_lo: [16]byte\npub var fx_mid: [16]byte\npub var fx_hi: [16]byte\n')
ROOM = 0x100            # bytes of fixed code the counters add, taken from the variables


def counting_copies(where, argument):
    """Copies of lathe/src/*.lth and of a counting rt_bbc.lth and bbc.lth in where (as
    test_bbc_selfhost.counting_copies, counting pairs); the counts go to the file the tool's
    argument number `argument` names."""
    for f in os.listdir(support.SRC):
        if f.endswith('.lth'):
            shutil.copy(os.path.join(support.SRC, f), where)
    rt = os.path.join(support.LATHE, 'rt')
    with open(os.path.join(rt, 'rt_bbc.lth')) as f:
        text = f.read()
    old = '  STA stub+1\n  LDY #$03\n  LDA (stub),Y                      ; f-1, high'
    assert text.count(old) == 1
    text = text.replace(old, COUNTING_CALL + '  LDY #$03\n  LDA (stub),Y                      ; f-1, high')
    text = re.sub(r'(?m)^import bbc \(', 'import bbc (mx_lo, mx_mid, mx_hi, fx_lo, fx_mid, fx_hi, ', text, count=1)
    text = text.replace('var now: byte ', 'var cnt_x: byte\nvar cnt_row: byte\nvar now: byte ', 1)
    old = '  now = mos_copy\n  if bbc.from_rom() then\n'
    assert text.count(old) == 1
    text = text.replace(old, '  now = mos_copy\n  k = 0\n  loop\n    bbc.mx_lo[k] = 0\n'
                             '    bbc.mx_mid[k] = 0\n    bbc.mx_hi[k] = 0\n    k += 1\n    if k == 0 then\n'
                             '      break\n    end\n  end\n  for k = 0 until 16 do\n'
                             '    bbc.fx_lo[k] = 0\n    bbc.fx_mid[k] = 0\n    bbc.fx_hi[k] = 0\n  end\n'
                             '  if bbc.from_rom() then\n')
    text = text.replace('  var i: byte\n  now = mos_copy', '  var i: byte\n  var k: byte\n  now = mos_copy', 1)
    with open(os.path.join(where, 'rt_bbc.lth'), 'w') as f:
        f.write(text)
    with open(os.path.join(rt, 'bbc.lth')) as f:
        text = f.read()
    old = '  osfind_close(0, 0)                ; every file\n  if code == 0 then\n'
    first = '\nextern func osrdch('
    assert text.count(old) == 1 and text.count(first) == 1
    text = text.replace(old, COUNTING_EXIT % argument + '  if code == 0 then\n')
    text = text.replace(first, COUNTERS + first)
    with open(os.path.join(where, 'bbc.lth'), 'w') as f:
        f.write(text)


COND = r'(?:(?:when|unless)\s+\w+\s+)*'
BANK_LINE = re.compile(r'(?mi)^' + COND + r'bank\s+WIN\s+\d+\s+\$8[0-9A-F]\s+\S+.*\n')
PLACE_LINE = re.compile(r'(?mi)^' + COND + r'place\s+(?!bbcfs)(\w+)\s+WIN\s+\d+.*\n')


def atoms_env(tool, env_path, out, file_prefix):
    """The tool's environment with each group of ATOMS in a bank of its own, the split moved up
    by ROOM for the counters."""
    with open(env_path) as f:
        text = f.read()
    text = BANK_LINE.sub('', text)
    text = PLACE_LINE.sub('', text)
    text = selfhost.moved_split(text, ROOM)
    lines = []
    for n, group in enumerate(ATOMS[tool], 1):
        lines.append(f'bank      WIN {n} ${0x80 + n:02X} {file_prefix}{n}.BIN\n')
        lines += [f'place     {m} WIN {n}\n' for m in group]
    with open(out, 'w') as f:
        f.write(text + ''.join(lines))
    return out


def build_counting(tool, where):
    """The counting copy of the tool in its developer's form, ATOMS banks: its image."""
    os.makedirs(where)
    counting_copies(where, 0)
    path = os.path.join(where, 'bbc.lth')
    with open(path) as f:
        text = f.read()
    old = '  h = open_out(argv(0))'
    assert text.count(old) == 1
    with open(path, 'w') as f:
        f.write(text.replace(old, '  h = open_out("COUNTS")'))
    source, env_name, prefix = TOOL_ENV[tool]
    env = atoms_env(tool, os.path.join(support.SRC, env_name), os.path.join(where, 'tool.env'), prefix)
    image = os.path.join(where, 'tool.bin')
    build.build(os.path.join(where, source), image, env=env, keep=os.path.join(where, 'work'))
    return image


def counted(image, disk, args):
    """(the pair matrix {(from, to): n}, cycles) of one run of the counting copy on disk."""
    env = mapenv.read_env(os.path.splitext(image)[0] + '.env')
    build.window_files(env, os.path.dirname(image), disk)
    try:
        status, out, err, cycles = boards.run_mos(chain.BOARD, image, disk, args, cap=chain.CAP * 4,
                                                  module=boards.module_options(env))
        assert status == 0, (status, out, err)
        with open(os.path.join(disk, 'COUNTS'), 'rb') as f:
            data = f.read()
    finally:
        for name in list(env.files) + ['COUNTS']:
            if os.path.exists(os.path.join(disk, name)):
                os.unlink(os.path.join(disk, name))
    pairs = {}
    for i in range(256):
        n = int.from_bytes(data[3 * i:3 * i + 3], 'big')
        if n:
            pairs[(i >> 4, i & 15)] = n
    for j in range(16):
        n = int.from_bytes(data[768 + 3 * j:768 + 3 * j + 3], 'big')
        if n:
            pairs[(FIXED, j)] = n
    return pairs, cycles


def far_calls(tool, pairs, layout):
    """The far calls of a layout (module -> bank or FIXED) from the pair matrix: calls between
    groups in different banks, calls from fixed memory into a bank, and none into fixed memory."""
    where = {}
    for n, group in enumerate(ATOMS[tool], 1):
        banks = {layout.get(m) for m in group}
        assert len(banks) == 1, (group, banks)
        where[n] = banks.pop()
    total = 0
    for (a, b), n in pairs.items():
        if where[b] == FIXED:
            continue
        if a == FIXED or where[a] != where[b]:
            total += n
    return total


def disk_for(name, work, tool='linker'):
    """(disk, the arguments) of a link: outtest or regtest (test_bbc_toolchain.link_alone), or the
    compiler's or the linker's own (test_bbc_selflink.prepare, with its command file); for the
    compiler tool, of the compile of lathe/src/NAME.lth (test_bbc_selfhost.py's)."""
    if tool == 'compiler':
        import memory_report
        import test_src_selfhost
        options = list(memory_report.options_of(os.path.join(support.SRC, name + '.lth')))
        disk, host = test_src_selfhost.prepare(name, work, options)
        return disk, options + [name + '.lth', '.']
    if name in ('compiler', 'linker'):
        import test_bbc_selflink as selflink
        tool = {'compiler': selflink.TOOLS[0], 'linker': selflink.TOOLS[1]}[name]
        disk, compiles, link, files = selflink.prepare(tool[0], tool[1], tool[2], work)
        for f in files:
            if f.endswith('.lo'):
                shutil.copy(os.path.join(work, 'host', f), disk)
        return disk, ['@' + selflink.COMMAND_FILE]
    files, link, disk = chain.link_alone(name, work)
    return disk, link


def show(tool, title, pairs):
    print(title)
    for (x, y), n in sorted(pairs.items(), key=lambda kv: -kv[1]):
        names = lambda k: FIXED if k == FIXED else '+'.join(ATOMS[tool][k - 1])
        print(f'  {names(x):>22} -> {names(y):<22} {n:10d}')
    for name, layout in LAYOUTS[tool].items():
        print(f'  {name}: {far_calls(tool, pairs, layout)} far calls')


def main(argv):
    ap = argparse.ArgumentParser(prog='farcall_matrix.py')
    ap.add_argument('--dir', help='where to work (default: a temporary directory, removed)')
    ap.add_argument('tool', choices=sorted(ATOMS))
    ap.add_argument('runs', nargs='+', help='links (linker), or modules of lathe/src (compiler); '
                    '`all` for every module the compiler compiles itself')
    a = ap.parse_args(argv)
    if a.runs == ['all']:
        import test_src_selfhost
        a.runs = list(test_src_selfhost.MODULES)
    d = a.dir or tempfile.mkdtemp(prefix='lathe-farcall-')
    total, cycles_all = {}, 0
    try:
        image = build_counting(a.tool, os.path.join(d, 'counting'))
        for name in a.runs:
            disk, args = disk_for(name, os.path.join(d, 'run-' + name), a.tool)
            pairs, cycles = counted(image, disk, args)
            show(a.tool, f'{name}: {cycles} cycles in the counting copy; pairs (from, to): calls', pairs)
            for k, n in pairs.items():
                total[k] = total.get(k, 0) + n
            cycles_all += cycles
        if len(a.runs) > 1:
            show(a.tool, f'all {len(a.runs)}: {cycles_all} cycles in the counting copy; pairs (from, to): calls',
                 total)
    finally:
        if not a.dir:
            shutil.rmtree(d, ignore_errors=True)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
