"""What the banked build costs, measured on gentest (lathe/host/README.md, "The banked build";
lathe/docs/configurations.md, "Measured on the compiler's test programs").

    python3 lathe/tests/bank_report.py [OUT_DIR] [--program NAME] [--script NAME]

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

OUT_DIR (default: a temporary directory) keeps the builds."""
import os
import re
import shutil
import sys
import tempfile

import src_support as support
import script_host

FAR_CALL = 182      # cycles more than a JSR and RTS (test_farcall.py)

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

COUNTING_EXIT = '''  h = open_out(argv(2))              ; the far calls, for lathe/tests/bank_report.py
  write(farcalls[2], h)
  write(farcalls[1], h)
  write(farcalls[0], h)
  close(h)
  for h = 1 to MAX_HANDLE do
'''


def counting_copies(where):
    """Copies of lathe/src/*.lth, and the counting rt_bank.lth and disk.lth, in WHERE."""
    for f in os.listdir(support.SRC):
        if f.endswith('.lth'):
            shutil.copy(os.path.join(support.SRC, f), where)
    with open(os.path.join(support.LATHE, 'rt', 'rt_bank.lth')) as f:
        text = f.read()
    assert 'pub asm func call()\n  PHP\n  SEI\n' in text
    with open(os.path.join(where, 'rt_bank.lth'), 'w') as f:
        f.write(text.replace('pub asm func call()\n  PHP\n  SEI\n', COUNTING_CALL))
    with open(os.path.join(support.LATHE, 'rt', 'disk.lth')) as f:
        text = f.read()
    marker = '  for h = 1 to MAX_HANDLE do\n'
    assert text.count(marker) == 1 and '\nmodule disk\n' in text
    text = text.replace(marker, COUNTING_EXIT)
    text = text.replace('\nmodule disk\n', '\nmodule disk\n\npub var farcalls: [3]byte\n')
    with open(os.path.join(where, 'disk.lth'), 'w') as f:
        f.write(text)


def flat_wendy_env(name, path):
    """compiler-bank.env for NAME without the window entries: all in one on Wendy 2."""
    support.banked_env(name, path)
    with open(path) as f:
        lines = [l for l in f if not re.match(r'^(window|switch|bank|place|farcall)\s', l)]
    lines = [re.sub(r'^code\s+\$3A00 \$7FFF', 'code      $3A00 $EFFF', l) for l in lines]
    with open(path, 'w') as f:
        f.write(''.join(lines))


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
    messages = sum(i[2] for i in fixed if i[0] == 'D' and i[3].startswith('err.$'))
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


def runs(image, run, sections, work, tag, extra=False):
    """[(cycles, far calls)] of every section."""
    found = []
    for n, (title, text) in enumerate(sections):
        path = os.path.join(work, '%s-%d.txt' % (tag, n))
        with open(path, 'wb') as f:
            f.write(text)
        args = [path, os.path.join(work, '%s-%d.lo' % (tag, n))]
        count = os.path.join(work, '%s-%d.far' % (tag, n))
        if extra:
            args.append(count)
        status, out, err, cycles = run(image, args)
        far = 0
        if extra and os.path.isfile(count):
            with open(count, 'rb') as f:
                far = int.from_bytes(f.read(), 'big')
        found.append((cycles, far))
    return found


def main(argv):
    out_dir = None
    name, script = 'gentest', 'gen'
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
    counting_copies(counting)
    cimage = os.path.join(counting, name + '.bin')
    support.banked_env(name, os.path.join(counting, name + '.env'))
    support.build.build(os.path.join(counting, name + '.lth'), cimage,
                        env=os.path.join(counting, name + '.env'), keep=os.path.join(counting, 'work'))

    flat = os.path.join(out_dir, 'flat')
    os.makedirs(flat, exist_ok=True)
    fimage = support.build_program(name, flat, small=True)

    wendy = os.path.join(out_dir, 'wendy')
    os.makedirs(wendy, exist_ok=True)
    wimage = os.path.join(wendy, name + '.bin')
    flat_wendy_env(name, os.path.join(wendy, name + '.env'))
    support.build.build(os.path.join(support.SRC, name + '.lth'), wimage,
                        env=os.path.join(wendy, name + '.env'), keep=os.path.join(wendy, 'work'))

    b = runs(image, support.run_banked, sections + empty, banked, 'b')
    c = runs(cimage, support.run_banked, sections + empty, counting, 'c', extra=True)
    f = runs(fimage, support.run, sections + empty, flat, 'f')
    w = runs(wimage, support.run_banked, sections + empty, wendy, 'w')
    n = len(sections)
    bc, cc, fc, wc = (sum(x[0] for x in r[:n]) for r in (b, c, f, w))
    far = sum(x[1] for x in c[:n])
    print('%s, %d sections of %s.txt:' % (name, n, script))
    print('  banked on Wendy 2:      %12d cycles, %d far calls (%d at %d cycles)'
          % (bc, far, far * FAR_CALL, FAR_CALL))
    print('  all in one, Wendy 2:    %12d cycles' % wc)
    print('  all in one, default:    %12d cycles' % fc)
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
