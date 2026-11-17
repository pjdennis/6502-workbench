"""Stage 12, step 4 of lathe/docs/bbc.md: the compiler written in Lathe (lathe/src/lathec.lth and
its seventeen modules), on the emulated BBC Model B+128 at its full capacities
(lathe/src/lathec-bbc.env, SMALL 0), compiles its own modules, as test_src_selfhost.py has the
banked compiler on Wendy 2 compile them: each in a directory of its own that holds its source
and the host compiler's interfaces of what it imports, with `lathec OPTIONS NAME.lth .`, every
run --bbc-strict. Status, output (the BBC has one stream: the host's output and error output
joined) and the files written must be the host compiler's.

The forms (bbc.md, "Step 4, as built"):

- rom: the ROM form, `*LATHE OPTIONS NAME.lth .`, from a module image (bbcrom.py) that holds the
  compiler alone, its environment made from lathec-bbc.env by bbcrom.rom_env: banks 1 to 5 of
  the image, read only; bank 0 copies the resident part to main RAM and the messages to slot 13;
- loader: the same image in the module's RAM form, filled by `*RUN LOADMOD MODULE` first;
- run: the developer's form linked with lathec-bbc.env itself, `*RUN LATHEC OPTIONS NAME.lth .`,
  its start-up code loading the banks into the RAM module and slot 13.

By default the five smallest modules (QUICK) in the ROM form, about 7 seconds.
LATHE_BBC_SELFHOST=1: every module in each of the three forms (90 s). LATHE_BBC_SELFHOST_REPORT=1 also
builds the counting copy (the run form with rt_bbc's call() and map() counting, and bbc.exit
writing the counts to the file its sixth argument names, as bank_report.py does on Wendy 2) and
prints, for each module, the cycles of each form, the far calls and `with` blocks, and the
bytes the compile reads and writes through the MOS (the exit report's file traffic: the
emulator's MOS charges no cycles for it)."""
import os
import re
import shutil
import sys
import tempfile
import unittest

import src_support as support
import memory_report
import test_src_selfhost as selfhost

import bbcrom
import boards
import build
import mapenv

ALL = os.environ.get('LATHE_BBC_SELFHOST') == '1'
REPORT = os.environ.get('LATHE_BBC_SELFHOST_REPORT') == '1'
ENV = os.path.join(support.SRC, 'lathec-bbc.env')
QUICK = selfhost.QUICK            # run by default: the five smallest, as on Wendy 2
FORMS = ('rom', 'loader', 'run')
BOARD = boards.BOARDS['bbc']
CAP = 2_000_000_000                 # CPU cycles a compile may take: gen takes 150 million
COMMAND = 'LATHE'
FILES_RE = re.compile(r'files: opened=(\d+)\s+bytes-read=(\d+)\s+bytes-written=(\d+)')
HAVE_TOOLS = os.path.isfile(support.EMULATOR) and os.path.isfile(build.COMPILER)


def build_rom(out_dir):
    """The ROM form in out_dir: the resident part LATHE, its banks, its environment lathec.env
    (rom_env of ENV), the image MODULE and the loader LOADMOD. Returns the image's path."""
    env = os.path.join(out_dir, 'lathec.env')
    bbcrom.rom_env(ENV, env, 1)
    resident = os.path.join(out_dir, COMMAND)
    build.build(os.path.join(support.SRC, 'lathec.lth'), resident, env=env,
                keep=os.path.join(out_dir, 'work'))
    image = os.path.join(out_dir, 'MODULE')
    bbcrom.image([(COMMAND, resident, env, os.path.join(out_dir, 'work', 'lathec.map'))], image,
                 os.path.join(out_dir, 'listing'))
    bbcrom.loader(os.path.join(out_dir, 'LOADMOD'))
    return image


def build_run(out_dir, source=None, env=ENV):
    """The developer's form, *RUN LATHEC, in out_dir: lathec.bin and its bank files beside it.
    Returns the program's path."""
    image = os.path.join(out_dir, 'lathec.bin')
    shutil.copy(env, os.path.join(out_dir, 'lathec.env'))
    build.build(source or os.path.join(support.SRC, 'lathec.lth'), image,
                env=os.path.join(out_dir, 'lathec.env'), keep=os.path.join(out_dir, 'work'))
    return image


# Memory as a language may leave it: every run starts with RAM filled with bytes that are not 0
# (the emulator's --fill-ram, which boards.run_mos and run_module pass), so that a variable that
# is used before it is set is found (sys.files was).


def report_run(form, image, disk, args):
    """The compiler in `form` ('rom', 'loader' or 'run') at `image`, with args, in the directory
    disk: (status, output, what the MOS said, {file: bytes} written, CPU cycles, (files opened,
    bytes read, bytes written))."""
    before = set(os.listdir(disk))
    lines = []
    copied = []
    if form == 'run':
        env = mapenv.read_env(os.path.join(os.path.dirname(image), 'lathec.env'))
        build.window_files(env, os.path.dirname(image), disk)
        copied += list(env.files)
        code, out, err, cycles = boards.run_mos(BOARD, image, disk, args, raw=True, cap=CAP,
                                                module=boards.module_options(env), report=True,
                                                before=lines)
    else:
        before_lines = lines
        if form == 'loader':
            for name in ('LOADMOD', 'LOADMOD.inf'):
                shutil.copy(os.path.join(os.path.dirname(image), name), disk)
            shutil.copy(image, os.path.join(disk, 'MODULE'))
            copied += ['LOADMOD', 'LOADMOD.inf', 'MODULE']
            before_lines = ['RUN LOADMOD MODULE'] + lines
        code, out, err, cycles = boards.run_module(BOARD, image, disk, COMMAND, args,
                                                   ram=form == 'loader', before=before_lines,
                                                   raw=True, cap=CAP)
    text = err.decode('latin-1')
    status, said, cycles = boards.bbc_status(code, text)
    m = FILES_RE.findall(text)
    traffic = tuple(int(n) for n in m[-1]) if m else (0, 0, 0)
    files = {}
    for f in sorted(os.listdir(disk)):
        if f not in before and f not in copied:
            files[f] = selfhost.read(os.path.join(disk, f))
    for f in copied:
        if os.path.exists(os.path.join(disk, f)):
            os.unlink(os.path.join(disk, f))
    return status, boards.bbc_output(out), said, files, cycles, traffic


# ---- The report (LATHE_BBC_SELFHOST_REPORT) ---------------------------------------------------

def read_map(path):
    """[(kind, address, size, name, bank or None, kept bank or None)] of a map's lines."""
    items = []
    with open(path) as f:
        for line in f:
            p = line.split()
            if len(p) >= 4 and len(p[0]) == 1:
                b = [int(r[2:]) for r in p[4:] if r.startswith('b=')]
                k = [int(r[2:]) for r in p[4:] if r.startswith('k=')]
                items.append((p[0], int(p[1], 16), int(p[2], 16), p[3], b[0] if b else None,
                              k[0] if k else None))
    return items


def summary(map_path, title):
    """The map's summary: each bank and slot, main RAM and zero page, as lines of text."""
    items = read_map(map_path)
    lines = [title]
    with open(map_path) as f:
        wlines = [l.split() for l in f if l.startswith('W ')]
    room = 0xBFE0 - int(wlines[0][1], 16)     # $8000-$BFDF, or $8050-$BFDF in the ROM form
    for w in wlines:
        n = int(w[3])
        inside = [i for i in items if i[4] == n]
        code = sum(i[2] for i in inside if i[0] == 'F')
        const = sum(i[2] for i in inside if i[0] == 'D')
        var = sum(i[2] for i in inside if i[0] == 'V')
        mods = {}
        for i in inside:
            if i[0] == 'F':
                m = i[3].split('.')[0]
                mods[m] = mods.get(m, 0) + i[2]
        what = 'slot %d' % {32: 12, 33: 13, 34: 0, 35: 1}[n] if n >= 32 else 'bank %d' % n
        lines.append('  %-8s code %5d  constants %5d  variables %5d  free %5d%s' % (
            what, code, const, var, room - code - const - var,
            '  (' + ', '.join('%s %d' % x for x in sorted(mods.items(), key=lambda x: -x[1])) + ')'
            if mods else ''))
    fixed = [i for i in items if i[4] is None]
    code = [i for i in fixed if i[0] in 'FTD' and 0x0800 <= i[1] < 0x8000]
    kept = sum(i[2] for i in code if i[0] == 'F' and i[5] is not None)
    data = [i for i in fixed if i[0] in 'VS' and 0x0800 <= i[1] < 0x8000]
    more = [i for i in fixed if i[0] in 'VS' and 0x0400 <= i[1] < 0x0800]
    zp = [i for i in fixed if i[0] in 'VS' and i[1] < 0x100]
    code_end = max(i[1] + i[2] for i in code)
    data_lo = min(i[1] for i in data)
    data_end = max(i[1] + i[2] for i in data)
    more_end = max(i[1] + i[2] for i in more) if more else 0x0401
    used = (code_end - 0x1900) + (data_end - data_lo) + (more_end - 0x0401)
    lines.append('  main RAM: code, constants and stubs $1900-$%04X (%d bytes: functions %d, of them '
                 'kept %d; stubs %d; constants %d), variables $%04X-$%04X (%d)%s: %d of 26111 used, '
                 '%d free'
                 % (code_end - 1, code_end - 0x1900, sum(i[2] for i in code if i[0] == 'F'), kept,
                    sum(i[2] for i in code if i[0] == 'T'), sum(i[2] for i in code if i[0] == 'D'),
                    data_lo, data_end - 1, data_end - data_lo,
                    ' and $0401-$%04X (%d)' % (more_end - 1, more_end - 0x0401) if more else
                    ', $0401-$06FF unused', used, 26111 - used))
    lines.append('  zero page: $00-$%02X used of $00-$8F' % (max(i[1] + i[2] for i in zp) - 1))
    return lines


# ---- The counting copy (LATHE_BBC_SELFHOST_REPORT) ------------------------------------------

COUNTING_CALL = '''pub asm func call()
  PHP
  SEI
  INC bbc.farcalls
  BNE .counted
  INC bbc.farcalls+1
  BNE .counted
  INC bbc.farcalls+2
.counted
'''

COUNTING_MAP = '''pub asm func map(value: byte in a): byte in a
  INC bbc.withs
  BNE .counted
  INC bbc.withs+1
  BNE .counted
  INC bbc.withs+2
.counted
  LDY now                           ; what is there
'''

COUNTING_EXIT = '''  var h: byte
  h = open_out(argv(%d))             ; the far calls and blocks, for test_bbc_selfhost.py
  write(farcalls[2], h)
  write(farcalls[1], h)
  write(farcalls[0], h)
  write(withs[2], h)
  write(withs[1], h)
  write(withs[0], h)
  close(h)
  osfind_close(0, 0)                ; every file
'''

COUNTING_ROOM = 0x80        # bytes of fixed code the counters add, taken from the variables


def counting_copies(where, argument):
    """Copies of lathe/src/*.lth and of the counting rt_bbc.lth and bbc.lth in where; the
    counts go to the file the compiler's argument number `argument` names."""
    for f in os.listdir(support.SRC):
        if f.endswith('.lth'):
            shutil.copy(os.path.join(support.SRC, f), where)
    rt = os.path.join(support.LATHE, 'rt')
    with open(os.path.join(rt, 'rt_bbc.lth')) as f:
        text = f.read()
    for old, new in (('pub asm func call()\n  PHP\n  SEI\n', COUNTING_CALL),
                     ('pub asm func map(value: byte in a): byte in a\n  LDY now                           ; what is there\n',
                      COUNTING_MAP)):
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    text = re.sub(r'(?m)^import bbc \(', 'import bbc (farcalls, withs, ', text, count=1)
    # The counters have no initial value (one would be a function more, and the compiler links
    # 800, the linker's limit): start(), which runs first, clears them.
    old = '  now = mos_copy\n  if bbc.from_rom() then\n'
    assert text.count(old) == 1
    text = text.replace(old, '  now = mos_copy\n  for i = 0 until 3 do\n    bbc.farcalls[i] = 0\n'
                             '    bbc.withs[i] = 0\n  end\n  if bbc.from_rom() then\n')
    with open(os.path.join(where, 'rt_bbc.lth'), 'w') as f:
        f.write(text)
    with open(os.path.join(rt, 'bbc.lth')) as f:
        text = f.read()
    old = '  osfind_close(0, 0)                ; every file\n  if code == 0 then\n'
    # The counters go after the imports (bbc imports bbcfs since 2026-11-16: before it they
    # were error 33, declaration expected).
    first = '\nextern func osrdch('
    assert text.count(old) == 1 and text.count(first) == 1
    text = text.replace(old, COUNTING_EXIT % argument + '  if code == 0 then\n')
    text = text.replace(first, '\npub var farcalls: [3]byte\npub var withs: [3]byte\n' + first)
    with open(os.path.join(where, 'bbc.lth'), 'w') as f:
        f.write(text)
    with open(ENV) as f:
        env = f.read()
    with open(os.path.join(where, 'counting.env'), 'w') as f:
        f.write(moved_split(env, COUNTING_ROOM))
    return os.path.join(where, 'counting.env')


# The developer's form's `code` and `data` entries: in lathec-bbc.env `unless ROMFORM` ones.
SPLIT_CODE = re.compile(r'(?mi)^((?:unless\s+ROMFORM\s+)?)code\s.*$')
SPLIT_DATA = re.compile(r'(?mi)^((?:unless\s+ROMFORM\s+)?)data\s+\$(\w+)')


def moved_split(env, room):
    """The text of a tool's environment file with the split between code and data of its
    developer's form moved up by room bytes."""
    split = int(SPLIT_DATA.search(env).group(2), 16) + room
    env = SPLIT_CODE.sub(lambda m: m.group(1) + 'code      $1900 $%04X' % (split - 1), env)
    return SPLIT_DATA.sub(lambda m: m.group(1) + 'data      $%04X' % split, env)


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class BBCSelfHost(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-bbc-selfhost-')
        cls.images = {}
        rom = os.path.join(cls.dir, 'rom')
        os.makedirs(rom)
        cls.images['rom'] = cls.images['loader'] = build_rom(rom)
        if ALL or REPORT:
            d = os.path.join(cls.dir, 'run')
            os.makedirs(d)
            cls.images['run'] = build_run(d)
        if REPORT:
            d = os.path.join(cls.dir, 'counting')
            os.makedirs(d)
            env = counting_copies(d, 5)     # OPTIONS (three) NAME.lth . COUNTS
            cls.images['counting'] = build_run(d, os.path.join(d, 'lathec.lth'), env)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def compile(self, form, name, n=0):
        options = tuple(memory_report.options_of(os.path.join(support.SRC, name + '.lth')))
        disk, host = selfhost.prepare(name, os.path.join(self.dir, 'work-%s-%d' % (form, n)), options)
        return run_form(form, self.images[form], disk, list(options) + [name + '.lth', '.']), host

    def test_the_compiler_compiles_itself_as_the_host_does(self):
        rows = {}
        for form in FORMS if ALL else ('rom',):
            for name in selfhost.MODULES if ALL else QUICK:
                got, host = self.compile(form, name)
                rows.setdefault(name, {})[form] = got
                with self.subTest(form=form, module=name):
                    self.assertEqual(got[:3], (host[0], host[1] + host[2], b''))
                    self.assertEqual(sorted(got[3]), sorted(host[3]))
                    for f in host[3]:
                        self.assertTrue(got[3][f] == host[3][f], f + ' differs')
        if REPORT:
            self.report(rows)

    def report(self, rows):
        print()
        for form, d in (('rom', 'rom'), ('run', 'run')):
            print('\n'.join(summary(os.path.join(self.dir, d, 'work', 'lathec.map'),
                                    'the %s form:' % form)))
        print('%-9s %13s %13s %13s %9s %9s %7s %8s %8s' % ('module', 'rom cycles', 'loader', 'run',
                                                          'far calls', 'blocks', 'opened', 'read',
                                                          'written'))
        total = [0] * 8
        for name in rows:
            options = tuple(memory_report.options_of(os.path.join(support.SRC, name + '.lth')))
            disk, _ = selfhost.prepare(name, os.path.join(self.dir, 'count-' + name), options)
            counted = run_form('counting', self.images['counting'], disk,
                               list(options) + [name + '.lth', '.', 'COUNTS'])
            data = counted[3].get('COUNTS', b'')
            far, withs = int.from_bytes(data[:3], 'big'), int.from_bytes(data[3:6], 'big')
            r = rows[name]
            traffic = r['rom'][5]
            line = [r.get(f, (0,) * 5)[4] for f in FORMS] + [far, withs] + list(traffic)
            total = [a + b for a, b in zip(total, line)]
            print('%-9s %13d %13d %13d %9d %9d %7d %8d %8d' % ((name,) + tuple(line)))
        print('%-9s %13d %13d %13d %9d %9d %7d %8d %8d' % (('total',) + tuple(total)))
        print('the ROM form at 2 MHz: %.1f minutes' % (total[0] / 2e6 / 60))


def run_form(form, image, disk, args):
    """report_run; the counting copy is the run form."""
    return report_run('run' if form == 'counting' else form, image, disk, args)


if __name__ == '__main__':
    unittest.main()
