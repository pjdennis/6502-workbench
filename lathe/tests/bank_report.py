"""What the banked build costs, measured on gentest (lathe/host/README.md, "The banked build";
lathe/docs/configurations.md, "Measured on the compiler's test programs").

    python3 lathe/tests/bank_report.py [OUT_DIR] [--program NAME] [--script NAME]
    python3 lathe/tests/bank_report.py [OUT_DIR] --program exprtest --script expr

Builds the test program (default gentest, script gen) three ways and runs every section of its
script with each:

1. banked on Wendy 2 (src_support.build_banked): from its map, the resident code (fixed code,
   fixed constant data with and without err's messages, stubs), the bytes of each bank and the
   stubs; from the runs, the CPU cycles;
2. the same with a counting far-call routine: copies of lathe/rt/rt_bank.lth, whose call()
   adds one to a 24-bit counter, and of lathe/rt/disk.lth, whose exit() writes the counter to
   the file named by the program's third argument (the test programs ignore it), beside copies
   of lathe/src/; the far calls of each run;
3. all in one: on the default machine, the small build (compiler-small.env), and on Wendy 2,
   compiler-bank.env without its window entries; the CPU cycles.

The start-up's loading of the banks is the banked run of an empty script less the all-in-one
Wendy 2 run of it and the far calls it makes (at 182 cycles each, test_farcall.py).

A program whose script's sections hold Lathe source after a line `--` (exprtest, SOURCES) gets
the section's commands and its source as two files, its first and third arguments, and the
counter goes to its fourth. Such a program does not fit the default machine or Wendy 2 all in one
(exprtest has about 68 KB of code), so only 1 and 2 are made.

With --compile PATH..., the program is the compiler itself, lathe/src/lathec.lth: it is built
banked and with the counting far-call routine, and compiles each module PATH (with the
interfaces of what it imports, made by the host compiler) as test_src_lathec.py runs it, the
counter's file given as an import directory after the output directory; and a command line
that stops at once, the start-up alone.

With --selfhost [--all-placed] NAME..., the compiler is built banked and with the counting
far-call routine, and compiles each lathe/src/NAME.lth as test_src_selfhost.py compiles it, with
the host's interfaces of its imports, checked to give the host compiler's files: the map, then
the CPU cycles, far calls and `with` blocks of each compile. With --all-placed, kernel, lex,
fbuf, err and src are placed too, in a seventh bank (ALL_PLACED), so that only what has to be
fixed stays fixed: the functions with a `with` block and those called inside one, which the
linker keeps in fixed memory (configurations.md, "Functions kept in fixed memory"); the regions
compiler-bank.env keeps fixed (SYMS) go in bank 7 too, apart from the others, as on the BBC; and
the report adds what main memory must hold where code banks are ROM (bbc.md, "Measured before
designing"): the variables not in a region, kept and other fixed code, stubs, fixed constants.

The map's report lists the fixed code by module, and the code each placed module has kept in
fixed memory (F lines that end in k=N).

OUT_DIR (default: a temporary directory) keeps the builds."""
import os
import re
import shutil
import sys
import tempfile

import src_support as support
import script_host

FAR_CALL = 182      # cycles more than a JSR and RTS (test_farcall.py)
WITH_BLOCK = 90     # cycles of a `with` block banked (configurations.md, "As built: banked data")

COUNTING_CALL = '''pub asm func call()
  PHP
  SEI
  INC disk.farcalls
  BNE .counted
  INC disk.farcalls+1
  BNE .counted
  INC disk.farcalls+2
.counted
'''

COUNTING_MAP = '''pub asm func map(value: byte in a): byte in a
  INC disk.withs
  BNE .counted
  INC disk.withs+1
  BNE .counted
  INC disk.withs+2
.counted
  CMP #$00                          ; the INCs changed the flags map() tests
  BEQ .fixed
  JMP select
'''

SOURCES = ('exprtest',)     # programs whose sections are commands, a line `--`, and Lathe source

COUNTING_EXIT = '''  h = open_out(argv(%d))              ; the far calls, for lathe/tests/bank_report.py
  write(farcalls[2], h)
  write(farcalls[1], h)
  write(farcalls[0], h)
  write(withs[2], h)                  ; and the with blocks entered
  write(withs[1], h)
  write(withs[0], h)
  close(h)
  for h = 1 to MAX_HANDLE do
'''


def counting_copies(where, count_argument=2):
    """Copies of lathe/src/*.lth, and the counting rt_bank.lth and disk.lth, in WHERE. The
    counter is written to the file the program's argument number `count_argument` names."""
    for f in os.listdir(support.SRC):
        if f.endswith('.lth'):
            shutil.copy(os.path.join(support.SRC, f), where)
    with open(os.path.join(support.LATHE, 'rt', 'rt_bank.lth')) as f:
        text = f.read()
    assert 'pub asm func call()\n  PHP\n  SEI\n' in text
    marker = 'pub asm func map(value: byte in a): byte in a\n  BEQ .fixed\n  JMP select\n'
    assert marker in text
    text = text.replace(marker, COUNTING_MAP)
    # The counters are disk's: add them to rt_bank's import list of disk.
    text = re.sub(r'(?m)^import disk \(', 'import disk (farcalls, withs, ', text, count=1)
    # The counters have no initial value, and every run starts on memory that is not 0 (the
    # emulator's --fill-ram): start(), which runs before any far call or block, clears them.
    # Without it each count began with what the fill left, and grew from run to run.
    old = '  direction = direction | BANK_BITS\n'
    assert text.count(old) == 1 and 'pub func start(table: ^byte)' in text
    text = text.replace(old, old + '  for i = 0 until 3 do\n    disk.farcalls[i] = 0\n    disk.withs[i] = 0\n  end\n')
    with open(os.path.join(where, 'rt_bank.lth'), 'w') as f:
        f.write(text.replace('pub asm func call()\n  PHP\n  SEI\n', COUNTING_CALL))
    with open(os.path.join(support.LATHE, 'rt', 'disk.lth')) as f:
        text = f.read()
    marker = '  for h = 1 to MAX_HANDLE do\n'
    assert text.count(marker) == 1 and '\nmodule disk\n' in text
    text = text.replace(marker, COUNTING_EXIT % count_argument)
    text = text.replace('\nmodule disk\n', '\nmodule disk\n\npub var farcalls: [3]byte\npub var withs: [3]byte\n')
    with open(os.path.join(where, 'disk.lth'), 'w') as f:
        f.write(text)


COUNTING_ROOM = 0x20     # bytes of fixed code the counters add, taken from the variables' range


def lower_split(path, room):
    """Move the split between the variables and the fixed code of the environment at PATH
    down by ROOM bytes: the counting copies' code is larger, and exprtest leaves little room."""
    with open(path) as f:
        text = f.read()
    m = re.search(r'(?m)^code\s+\$(\w+) \$7FFF', text)
    split = int(m.group(1), 16) - room
    text = re.sub(r'(?m)^code\s+\$\w+ \$7FFF', 'code      $%04X $7FFF' % split, text)
    text = re.sub(r'(?m)^data\s+\$0200 \$\w+', 'data      $0200 $%04X' % (split - 1), text)
    with open(path, 'w') as f:
        f.write(text)


def flat_wendy_env(name, path):
    """compiler-bank.env for NAME without the window entries: all in one on Wendy 2."""
    support.banked_env(name, path)
    with open(path) as f:
        lines = [l for l in f if not re.match(r'^(window|switch|bank|place|region|farcall)\s', l)]
    lines = [re.sub(r'^code\s+\$(\w+) \$7FFF', r'code      $\1 $EFFF', l) for l in lines]
    with open(path, 'w') as f:
        f.write(''.join(lines))


ALL_PLACED = ('kernel', 'lex', 'fbuf', 'err', 'src')    # typetab and out are placed already
ALL_PLACED_BANK = 'bank      WIN 7 $17 LATHE7.BIN   ; --all-placed: kernel, lex, fbuf, err, src\n'
# The regions that compiler-bank.env keeps fixed go in bank 7 too, apart from the names and the
# function buffer, as the BBC has them in a sideways bank of their own: so that a compile shows
# that nothing reads them outside their blocks. (Wendy 2 has banks 1 to 7 only.)
REGION_BANK = 7


def all_placed_env(name, path):
    """support.banked_env, with the modules of ALL_PLACED placed in bank 7, and the regions that
    are fixed there in bank REGION_BANK. Returns PATH."""
    support.banked_env(name, path)
    with open(path) as f:
        lines = f.readlines()
    at = next(i for i, l in enumerate(lines) if l.startswith('region'))
    lines[at:at] = [ALL_PLACED_BANK] + ['place     %s WIN 7\n' % m for m in ALL_PLACED]
    lines = [re.sub(r'^region(\s+)(\w+)(\s+)fixed', r'region\1\2\3WIN %d' % REGION_BANK, l) for l in lines]
    with open(path, 'w') as f:
        f.write(''.join(lines))
    return path


REGION_VAR = re.compile(r'^(?:pub )?var (\w+):[^;\n]*\bin [A-Za-z_]\w*', re.M)


def region_variables():
    """{'module.name'} of every variable declared `in` a region in lathe/src/ and lathe/rt/."""
    found = set()
    for d in (support.SRC, os.path.join(support.LATHE, 'rt')):
        for f in os.listdir(d):
            if f.endswith('.lth'):
                with open(os.path.join(d, f), encoding='latin-1') as source:
                    for m in REGION_VAR.finditer(source.read()):
                        found.add((f[:-4] + '.' + m.group(1)).lower())
    return found


def budget_report(path):
    """What main memory must hold on a machine whose code banks are ROM and whose regions are
    in sideways RAM (bbc.md, "Measured before designing"): every variable not in a region, the
    code kept in fixed memory and the other fixed code, the stubs and the fixed constant data.
    Returns the rows, (what, bytes), and the total."""
    items = read_map(path)
    regions = region_variables()

    def banked(i):
        return any(r.startswith('b=') for r in i[4])
    fixed = [i for i in items if i[0] in 'FDT' and i[1] < 0x8000 and not banked(i)]
    variables = sum(i[2] for i in items if i[0] == 'V' and i[3].lower() not in regions)
    kept = sum(i[2] for i in fixed if i[0] == 'F' and any(r.startswith('k=') for r in i[4]))
    rows = [('variables not in a region', variables), ('kept code', kept),
            ('other fixed code', sum(i[2] for i in fixed if i[0] == 'F') - kept),
            ('stubs', 6 * sum(1 for i in fixed if i[0] == 'T')),
            ('fixed constants', sum(i[2] for i in fixed if i[0] == 'D'))]
    total = sum(n for _, n in rows)
    print('main memory: %s: %d bytes' % (', '.join('%s %d' % r for r in rows), total))
    return rows, total


def read_map(path):
    items = []
    with open(path) as f:
        for line in f:
            p = line.split()
            if len(p) >= 4:
                items.append((p[0], int(p[1], 16), int(p[2], 16), p[3], p[4:]))
    return items


def map_report(path):
    items = read_map(path)
    fixed = [i for i in items if i[0] in 'FDT' and i[1] < 0x8000 and not any(r.startswith('b=') for r in i[4])]
    code = sum(i[2] for i in fixed if i[0] == 'F')
    stubs = [i for i in fixed if i[0] == 'T']
    data = sum(i[2] for i in fixed if i[0] == 'D')
    messages = sum(i[2] for i in fixed if i[0] == 'D' and i[3].startswith(('err.$', 'err.messages_')))
    print('resident: code %d, stubs %d (%d bytes), constant data %d (%d of it err\'s messages)'
          % (code, len(stubs), 6 * len(stubs), data, messages))
    print('resident code, stubs and constants but the messages: %d bytes' % (code + 6 * len(stubs) + data - messages))
    for i in items:
        if i[0] == 'W':
            b = i[3]
            inside = [j for j in items if 'b=' + b in j[4]]
            print('bank %s (%s): file %d bytes; code %d, constants %d, variables %d'
                  % (b, i[4][0], i[2], sum(j[2] for j in inside if j[0] == 'F'),
                     sum(j[2] for j in inside if j[0] == 'D'), sum(j[2] for j in inside if j[0] == 'V')))
    top = max(i[1] + i[2] for i in items if i[0] in 'VSC' and 0x200 <= i[1] < 0x8000)
    high = [i[1] + i[2] for i in items if i[0] in 'VSC' and i[1] >= 0xF810]
    lo = min(i[1] for i in fixed)
    hi = max(i[1] + i[2] for i in fixed)
    print('fixed memory: variables $0200-$%04X, code $%04X-$%04X: %d bytes free below the code, '
          '%d above it; %d bytes of variables at $F810 and up, %d free there'
          % (top - 1, lo, hi - 1, lo - top, 0x8000 - hi, (max(high) - 0xF810) if high else 0,
             0xFFFA - (max(high) if high else 0xF810)))
    by_module = {}
    for i in fixed:
        if i[0] == 'F':
            module = i[3].split('.')[0] if '.' in i[3] else i[3]
            kept = 'kept' if any(r.startswith('k=') for r in i[4]) else 'fixed'
            by_module.setdefault(module, {'kept': 0, 'fixed': 0, 'functions': 0})
            by_module[module][kept] += i[2]
            by_module[module]['functions'] += kept == 'kept'
    print('fixed code by module (bytes; kept: of a placed module, k=N in the map):')
    for module, n in sorted(by_module.items(), key=lambda x: -(x[1]['kept'] + x[1]['fixed'])):
        print('  %-10s %6d%s' % (module, n['kept'] + n['fixed'],
                                 ' kept, %d functions' % n['functions'] if n['kept'] else ''))
    print('  kept code in all: %d bytes; other fixed code %d; stubs %d'
          % (sum(n['kept'] for n in by_module.values()), sum(n['fixed'] for n in by_module.values()),
             6 * len(stubs)))
    for kind, letter in (('constant data', 'D'), ('variables', 'V')):
        fixed_of = {}
        for i in items:
            if i[0] == letter and not any(r.startswith('b=') for r in i[4]) and i[1] < 0x8000 or \
                    i[0] == letter and i[1] >= 0xF810:
                module = i[3].split('.')[0] if '.' in i[3] else i[3]
                fixed_of[module] = fixed_of.get(module, 0) + i[2]
        print('fixed %s by module: %s' % (kind, ', '.join('%s %d' % x for x in sorted(fixed_of.items(), key=lambda x: -x[1]))))


def runs(image, run, sections, work, tag, extra=False, sources=False):
    """[(cycles, far calls, with blocks entered)] of every section."""
    found = []
    for n, (title, text) in enumerate(sections):
        path = os.path.join(work, '%s-%d.txt' % (tag, n))
        commands, _, source = text.partition(b'\n--\n')
        with open(path, 'wb') as f:
            f.write(commands + b'\n' if sources else text)
        args = [path, os.path.join(work, '%s-%d.lo' % (tag, n))]
        if sources:
            args.append(os.path.join(work, '%s-%d.lth' % (tag, n)))
            with open(args[-1], 'wb') as f:
                f.write(source)
        count = os.path.join(work, '%s-%d.far' % (tag, n))
        if extra:
            args.append(count)
        status, out, err, cycles = run(image, args)
        far = withs = 0
        if extra and os.path.isfile(count):
            with open(count, 'rb') as f:
                data = f.read()
            far, withs = int.from_bytes(data[:3], 'big'), int.from_bytes(data[3:6], 'big')
        found.append((cycles, far, withs))
    return found


def compile_report(out_dir, paths):
    """The compiler's own banked build: its map, and the cycles and far calls of compiling each
    of `paths`."""
    import test_src_lathec as lathec
    banked = os.path.join(out_dir, 'banked')
    os.makedirs(banked, exist_ok=True)
    image = support.build_banked('lathec', banked)
    map_report(os.path.join(banked, 'work', 'lathec.map'))
    counting = os.path.join(out_dir, 'counting')
    os.makedirs(counting, exist_ok=True)
    counting_copies(counting, 2)
    cimage = os.path.join(counting, 'lathec.bin')
    support.banked_env('lathec', os.path.join(counting, 'lathec.env'))
    support.build.build(os.path.join(counting, 'lathec.lth'), cimage,
                        env=os.path.join(counting, 'lathec.env'), keep=os.path.join(counting, 'work'))
    corpus = lathec.Corpus.__new__(lathec.Corpus)
    corpus.work, corpus.done = os.path.join(out_dir, 'corpus'), {}
    os.makedirs(corpus.work, exist_ok=True)
    # The start-up alone: options, and a source name that is not one (error 61)
    items = [('start-up', 'the start-up', ['-c6502', '-c6502', 'farcalls'], [])]
    for path in paths:
        files = [(os.path.basename(path), path)]
        for name, dep in lathec.imports_of(path) or []:
            li = corpus.interface(dep, ())
            files.append((os.path.basename(li), li))
        with open(path, 'rb') as f:
            lines = f.read().count(b'\n')
        items.append(('%d lines' % lines, path, [os.path.basename(path), '.', 'farcalls'], files))
    for kind, path, args, files in items:
        status, out, err, written, cycles = lathec.run_lathe(image, (kind, path, args, files), out_dir,
                                                             cycles=True)
        got = lathec.run_lathe(cimage, (kind, path, args, files), out_dir)
        far_file = got[3].get('farcalls')
        far = int.from_bytes(far_file, 'big') if far_file else 0
        print('%s (%s): status %d, %d cycles banked, %d far calls (%d cycles at %d), %s'
              % (os.path.relpath(path, support.LATHE) if os.path.isfile(path) else path, kind,
                 status, cycles, far, far * FAR_CALL, FAR_CALL, ' '.join(sorted(written)) or '-'))


def selfhost_report(out_dir, names, all_placed):
    """The compiler banked (with --all-placed, ALL_PLACED placed too) compiling lathe/src/NAME.lth
    for each of `names`, as test_src_selfhost.py does: its map, and each compile's cycles, far
    calls and blocks, after checking that it gives the host's files."""
    import memory_report
    import test_src_selfhost as selfhost
    make_env = all_placed_env if all_placed else support.banked_env
    banked = os.path.join(out_dir, 'banked')
    os.makedirs(banked, exist_ok=True)
    image = os.path.join(banked, 'lathec.bin')
    make_env('lathec', os.path.join(banked, 'lathec.env'))
    support.build.build(os.path.join(support.SRC, 'lathec.lth'), image,
                        env=os.path.join(banked, 'lathec.env'), keep=os.path.join(banked, 'work'))
    map_report(os.path.join(banked, 'work', 'lathec.map'))
    if all_placed:
        budget_report(os.path.join(banked, 'work', 'lathec.map'))
    counting = os.path.join(out_dir, 'counting')
    os.makedirs(counting, exist_ok=True)
    counting_copies(counting, 5)       # OPTIONS (three: memory_report.options_of) NAME.lth . farcalls
    cimage = os.path.join(counting, 'lathec.bin')
    make_env('lathec', os.path.join(counting, 'lathec.env'))
    lower_split(os.path.join(counting, 'lathec.env'), COUNTING_ROOM)
    support.build.build(os.path.join(counting, 'lathec.lth'), cimage,
                        env=os.path.join(counting, 'lathec.env'), keep=os.path.join(counting, 'work'))
    for name in names:
        options = tuple(memory_report.options_of(os.path.join(support.SRC, name + '.lth')))
        work = os.path.join(out_dir, 'work-' + name)
        disk, host = selfhost.prepare(name, work, options)
        assert len(options) == 3, options
        got = selfhost.run_lathe(image, disk, list(options) + [name + '.lth', '.'])
        same = got[:3] == host[:3] and got[3] == host[3]
        cdisk, _ = selfhost.prepare(name, os.path.join(out_dir, 'cwork-' + name), options)
        counted = selfhost.run_lathe(cimage, cdisk, list(options) + [name + '.lth', '.', 'farcalls'])
        data = counted[3].get('farcalls', b'')
        far, withs = int.from_bytes(data[:3], 'big'), int.from_bytes(data[3:6], 'big')
        # A count the run's cycles cannot hold is not a count: a counter that nothing cleared.
        if far * FAR_CALL > counted[4] or withs * 32 > counted[4]:
            raise AssertionError('%s: %d far calls and %d blocks in %d cycles: the counters were not '
                                 'cleared' % (name, far, withs, counted[4]))
        print('%s: %d cycles banked (%s the host\'s files), %d far calls (%d cycles at %d), '
              '%d with blocks' % (name, got[4], 'gives' if same else 'does NOT give', far,
                                  far * FAR_CALL, FAR_CALL, withs))


def main(argv):
    out_dir = None
    name, script = 'gentest', 'gen'
    if '--selfhost' in argv:
        names = argv[argv.index('--selfhost') + 1:]
        argv = argv[:argv.index('--selfhost')]
        all_placed = '--all-placed' in names
        names = [n for n in names if n != '--all-placed']
        out_dir = argv[0] if argv else tempfile.mkdtemp(prefix='lathe-bank-report-')
        selfhost_report(out_dir, names, all_placed)
        return
    if '--compile' in argv:
        paths = argv[argv.index('--compile') + 1:]
        argv = argv[:argv.index('--compile')]
        out_dir = argv[0] if argv else tempfile.mkdtemp(prefix='lathe-bank-report-')
        compile_report(out_dir, paths)
        return
    while argv:
        a = argv.pop(0)
        if a == '--program':
            name = argv.pop(0)
        elif a == '--script':
            script = argv.pop(0)
        else:
            out_dir = a
    out_dir = out_dir or tempfile.mkdtemp(prefix='lathe-bank-report-')
    sections = script_host.sections(script)
    empty = [(b'empty', b'\n')]

    banked = os.path.join(out_dir, 'banked')
    os.makedirs(banked, exist_ok=True)
    image = support.build_banked(name, banked)
    map_report(os.path.join(banked, 'work', name + '.map'))

    counting = os.path.join(out_dir, 'counting')
    os.makedirs(counting, exist_ok=True)
    sources = name in SOURCES
    counting_copies(counting, 3 if sources else 2)
    cimage = os.path.join(counting, name + '.bin')
    support.banked_env(name, os.path.join(counting, name + '.env'))
    lower_split(os.path.join(counting, name + '.env'), COUNTING_ROOM)
    support.build.build(os.path.join(counting, name + '.lth'), cimage,
                        env=os.path.join(counting, name + '.env'), keep=os.path.join(counting, 'work'))

    if sources:
        b = runs(image, support.run_banked, sections + empty, banked, 'b', sources=True)
        c = runs(cimage, support.run_banked, sections + empty, counting, 'c', extra=True, sources=True)
        n = len(sections)
        far = sum(x[1] for x in c[:n])
        withs = sum(x[2] for x in c[:n])
        print('%s, %d sections of %s.txt:' % (name, n, script))
        print('  banked on Wendy 2: %d cycles, %d far calls (%d at %d cycles), %d with blocks (%d at %d)'
              % (sum(x[0] for x in b[:n]), far, far * FAR_CALL, FAR_CALL, withs, withs * WITH_BLOCK,
                 WITH_BLOCK))
        print('  an empty script: %d cycles, %d far calls' % (b[n][0], c[n][1]))
        worst = max(range(n), key=lambda i: c[i][1])
        print('  most far calls in a section: %d (section %d, %d cycles banked); %.0f a section'
              % (c[worst][1], worst, b[worst][0], far / n))
        return
    flat = os.path.join(out_dir, 'flat')
    os.makedirs(flat, exist_ok=True)
    fimage = support.build_program(name, flat, small=True)

    wendy = os.path.join(out_dir, 'wendy')
    os.makedirs(wendy, exist_ok=True)
    wimage = os.path.join(wendy, name + '.bin')
    flat_wendy_env(name, os.path.join(wendy, name + '.env'))
    try:
        support.build.build(os.path.join(support.SRC, name + '.lth'), wimage,
                            env=os.path.join(wendy, name + '.env'), keep=os.path.join(wendy, 'work'))
    except support.build.BuildError as e:     # gentest no longer fits Wendy 2 all in one
        print('all in one on Wendy 2: not built (%s)' % str(e).splitlines()[-1])
        wimage = None

    b = runs(image, support.run_banked, sections + empty, banked, 'b')
    c = runs(cimage, support.run_banked, sections + empty, counting, 'c', extra=True)
    f = runs(fimage, support.run, sections + empty, flat, 'f')
    w = runs(wimage, support.run_banked, sections + empty, wendy, 'w') if wimage else None
    n = len(sections)
    bc, cc, fc, wc = (sum(x[0] for x in r[:n]) if r else 0 for r in (b, c, f, w))
    far = sum(x[1] for x in c[:n])
    withs = sum(x[2] for x in c[:n])
    print('%s, %d sections of %s.txt:' % (name, n, script))
    print('  banked on Wendy 2:      %12d cycles, %d far calls (%d at %d cycles), %d with blocks (%d at %d)'
          % (bc, far, far * FAR_CALL, FAR_CALL, withs, withs * WITH_BLOCK, WITH_BLOCK))
    print('  all in one, default:    %12d cycles' % fc)
    if w is None:
        return
    load = b[n][0] - w[n][0] - c[n][1] * FAR_CALL
    with open(os.path.join(banked, 'work', name + '.map')) as fh:
        banks = sum(int(l.split()[2], 16) for l in fh if l.startswith('W '))
    print('  start-up: an empty script, banked %d, all in one on Wendy 2 %d, %d far calls:'
          % (b[n][0], w[n][0], c[n][1]))
    print('  loading %d bytes of banks takes about %d cycles (%.1f a byte), %d for all %d runs'
          % (banks, load, load / banks, load * n, n))
    print('  banked less all in one on Wendy 2, less the loads: %d cycles; far calls x %d: %d'
          % (bc - wc - load * n, FAR_CALL, far * FAR_CALL))
    worst = max(range(n), key=lambda i: c[i][1])
    print('  most far calls in a section: %d (section %d, %d cycles banked)' % (c[worst][1], worst, b[worst][0]))


if __name__ == '__main__':
    main(sys.argv[1:])
