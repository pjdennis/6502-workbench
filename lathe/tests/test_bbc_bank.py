"""Banked programs on the emulated BBC Model B+128 (lathe/docs/bbc.md, step 3): code in banks of
the module, in its developer's form (RAM, scheme direct16), and regions in sideways RAM slots,
both in the one window $8000-$BFDF, switched by lathe/rt/rt_bbc.lth. Each program is built with
lathe/env/bbc-bank.env and the `bank`, `place` and `region` lines of its own (bank_env), and run
with *RUN through the MOS with --bbc-strict (build.run_program, boards.module_options).

- The far-call and banked-data cases of lathe/tests/cases/e2e-config/ give the output they give
  on Wendy 2: farcall.lth (nested calls, recursion across banks, pointers), bankdata.lth
  (constants and a variable in a bank), regions.lth (a region of variables in one sideways slot,
  a region of constants in another, loaded at start-up). Not here: farirq.lth and withirq.lth,
  which need a timer interrupt (the emulator's BBC has none, and their `timer` is Wendy 2's
  VIA); inbank.lth, which switches Wendy 2's port and loads its bank itself through `disk`.
- A program of this file's own: regions in two sideways slots at the same addresses, nested
  blocks; a `with` block entered from code in two banks at each level of a recursion between
  them; a far call made inside a block and back, as an interrupt handler's would be (the
  linker keeps fixed whatever a call inside a block reaches, so the call is made through an
  address taken in asm, which the linker does not follow); MOS file calls from a bank of the
  module and inside a block, a name the filing system refuses among them.
- All sixteen banks of the module, in a chain of far calls.
- What a far call and a `with` block cost, against the same objects all in one, measured as
  test_farcall.py measures Wendy 2's.
"""
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
CASES = os.path.join(HERE, 'cases', 'e2e-config')
sys.path.insert(0, os.path.join(ROOT, 'lathe', 'host', 'driver'))

import boards  # noqa: E402
import build  # noqa: E402
import mapenv  # noqa: E402

BANK_ENV = os.path.join(ROOT, 'lathe', 'env', 'bbc-bank.env')
FLAT_ENV = os.path.join(ROOT, 'lathe', 'env', 'bbc.env')
HAVE_TOOLS = os.path.isfile(build.COMPILER) and os.path.isfile(boards.EMULATOR)


def bank_env(path, lines, base=BANK_ENV, ports=None):
    """Write to PATH the environment `base` (bbc-bank.env) with `lines` after it: a program's
    own `bank`, `place` and `region` lines. With `ports`, its `define PORTS` says that instead
    (0 for the cases of e2e-config, whose libfco calls `host`: on the BBC lathe/rt/bbc/host.lth).
    Returns PATH."""
    with open(base) as f:
        text = f.read()
    if ports is not None:
        text, n = re.subn(r'(?m)^define\s+PORTS\s+\d+', 'define    PORTS %d' % ports, text)
        assert n == 1
    with open(path, 'w') as f:
        f.write(text + ''.join(line + '\n' for line in lines))
    return path


def build_and_run(source, env, work, args=(), files=None):
    """Build source with env into WORK/NAME.bin (the work files in WORK/work) and run it on the
    BBC on a directory that holds `files` (name -> bytes). Returns (status, output, error
    output, the directory, the map's entries)."""
    name = os.path.splitext(os.path.basename(source))[0]
    image = os.path.join(work, name + '.bin')
    build.build(source, image, env, keep=os.path.join(work, 'work'))
    disk = os.path.join(work, 'disk')
    os.makedirs(disk, exist_ok=True)
    for n, data in (files or {}).items():
        with open(os.path.join(disk, n), 'wb') as f:
            f.write(data)
    status, out, err = build.run_program(image, env, args, disk=disk)
    return status, out, err, disk, mapenv.read_map(os.path.join(work, 'work', name + '.map'))


def cycles(source, env, work, defines=()):
    """The CPU cycles of a run of source built with env and defines."""
    name = os.path.splitext(os.path.basename(source))[0]
    image = os.path.join(work, name + '.bin')
    build.build(source, image, env, keep=os.path.join(work, 'work'), defines=list(defines))
    described = mapenv.read_env(env)
    disk = os.path.join(work, 'disk')
    os.makedirs(disk, exist_ok=True)
    build.window_files(described, work, disk)
    status, out, err, n = boards.run_mos(boards.BOARDS['bbc'], image, disk,
                                         module=boards.module_options(described))
    assert (status, err) == (0, b''), (status, out, err)
    return n


def read(path, mode='rb'):
    with open(path, mode) as f:
        return f.read()


# ---- The cases of e2e-config ---------------------------------------------------------------

FARCALL = ['bank      WIN 1 $81 FCBANK1.BIN', 'bank      WIN 2 $82 FCBANK2.BIN',
           'place     libfca WIN 1', 'place     libfcc WIN 1', 'place     libfcb WIN 2']
BANKDATA = ['bank      WIN 3 $83 BKDATA3.BIN', 'place     libbkd WIN 3']
REGIONS = ['bank      WIN 32 $0C', 'bank      WIN 33 $0D REGTEXT.BIN',
           'region    work WIN 32', 'region    text WIN 33']


@unittest.skipUnless(HAVE_TOOLS, 'compiler or emulator missing')
class Cases(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lathe-bbc-bank-')
        self.addCleanup(shutil.rmtree, self.dir, True)

    def run_case(self, name, lines):
        env = bank_env(os.path.join(self.dir, name + '.env'), lines, ports=0)
        status, out, err, disk, entries = build_and_run(os.path.join(CASES, name + '.lth'), env,
                                                        os.path.join(self.dir, name))
        self.assertEqual(out, read(os.path.join(CASES, name + '.expected.out')))
        self.assertEqual((status, err), (0, b''))
        return {(e.kind, e.name): e for e in entries}

    def test_farcall(self):
        m = self.run_case('farcall', FARCALL)
        self.assertEqual(m['F', 'libfca.entry'].bank, 1)
        self.assertEqual(m['F', 'libfcb.mid'].bank, 2)
        self.assertEqual(m['D', 'libfcb.sig'].bank, 2)
        self.assertLess(m['F', 'rt_bbc.call'].addr, 0x8000)
        self.assertEqual(m['F', 'rt_bbc.call'].size + m['F', 'rt_bbc.back'].size, 136)  # zero page
        stubs = [e for (kind, name), e in m.items() if kind == 'T']
        self.assertEqual((len(stubs), {e.size for e in stubs}), (7, {6}))

    def test_bankdata(self):
        m = self.run_case('bankdata', BANKDATA)
        self.assertEqual((m['D', 'libbkd.squares'].addr, m['D', 'libbkd.squares'].bank), (0x8000, 3))
        # A variable of the bank is at its top, below the 32 bytes of the latch's addresses: the
        # developer's module is RAM.
        self.assertEqual((m['V', 'libbkd.calls'].addr, m['V', 'libbkd.calls'].bank), (0xBFDF, 3))

    def test_regions(self):
        m = self.run_case('regions', REGIONS)
        self.assertEqual(m['V', 'libreg.table'].bank, 32)
        self.assertEqual(m['D', 'libreg.steps'].bank, 33)

    def test_a_missing_bank_file_is_status_255(self):
        env = bank_env(os.path.join(self.dir, 'fc.env'), FARCALL, ports=0)
        image = os.path.join(self.dir, 'fc.bin')
        build.build(os.path.join(CASES, 'farcall.lth'), image, env, keep=os.path.join(self.dir, 'work'))
        os.unlink(os.path.join(self.dir, 'FCBANK2.BIN'))
        disk = os.path.join(self.dir, 'disk')
        os.makedirs(disk)
        self.assertEqual(build.run_program(image, env, disk=disk)[:2], (255, b''))

    def test_the_switch_is_the_far_call_modules(self):
        """`switch WIN bank farcall` names no register; a register after it is a bad entry."""
        self.assertIn('switch    WIN bank farcall\n', read(BANK_ENV, 'r'))
        env = bank_env(os.path.join(self.dir, 'bad.env'), FARCALL, ports=0)
        with open(env) as f:
            text = f.read().replace('switch    WIN bank farcall', 'switch    WIN bank farcall $1F')
        with open(env, 'w') as f:
            f.write(text)
        with self.assertRaises(build.BuildError) as caught:
            build.build(os.path.join(CASES, 'farcall.lth'), os.path.join(self.dir, 'x.bin'), env,
                        keep=os.path.join(self.dir, 'work'))
        self.assertIn('link error 3: ', str(caught.exception))


# ---- Two sideways slots, blocks from two banks, a far call inside a block, files ------------

PROGRAM = {
    'bkptr': '''module bkptr
pub type RecFn = recursive func(n: byte): word
pub var two: RecFn              ; bktwo.down
''',
    # Fixed: every function with a `with` block.
    'bkdat': '''module bkdat
import libfco
import host
import bkptr

var a: [64]byte in ra           ; slot 12
var b: [64]byte in rb           ; slot 13: the same addresses as a

pub func fill()
  var i: byte
  with ra do
    for i = 0 to 63 do
      a[i] = i
    end
    with rb do
      for i = 0 to 63 do
        b[i] = 200 - i
      end
    end
    a[0] = 99
  end
end

; Both tables, one element of each in turn: a block of rb inside a block of ra, 64 times.
pub func sum(): word
  var i: byte
  var s: word
  s = 0
  with ra do
    for i = 0 to 63 do
      s += word(a[i])
      with rb do
        s += word(b[i])
      end
    end
  end
  return s
end

; bktwo.tag's stub, which bkmain.aim writes in asm: no call the linker follows, so that tag stays
; in bank 2 and far() makes a far call from inside the block of across(), as an interrupt
; handler would. With the slot alone put back at the block's end, across() would return into
; bank 2, not bank 1, which called it.
pub var raw: word

asm func far(): word in ax
  JMP (raw)
end

; A far call made inside a block, through far(), which is fixed, into bank 2.
pub func across(): word
  var s: word
  with ra do
    s = word(a[5]) + far()
    s += word(a[6])
  end
  return s
end

pub func get(i: byte): byte
  with ra do
    return a[i]
  end
end

; The first 8 bytes of INPUT read into a while ra is mapped, and a name the filing system
; refuses (Bad name, which bbc.lth catches) opened before they are read back.
pub func files(): word
  var h: byte
  var c: byte
  var i: byte
  var s: word
  with ra do
    h = host.open("INPUT")
    i = 0
    while i < 8 do
      if host.read(h) -> c then
        break
      end
      a[i + 32] = c
      i += 1
    end
    host.close(h)
    if host.open("A/B") != 0 then
      libfco.text("opened ")
    end
    s = 0
    for i = 32 to 39 do
      s += word(a[i])
    end
  end
  return s
end
''',
    # Bank 1.
    'bkone': '''module bkone
import libfco
import host
import bkptr
import bkdat

const SIG: [1]byte = [$A1]

pub func mark(): byte
  return SIG[0]
end

; INPUT copied to OUTPUT through the MOS from this bank, and a name refused: the count.
pub func copy(): byte
  var h: byte
  var o: byte
  var c: byte
  var n: byte
  h = host.open("INPUT")
  o = host.open_out("OUTPUT")
  n = 0
  loop
    if host.read(h) -> c then
      break
    end
    host.write(c, o)
    n += 1
  end
  host.close(h)
  host.close(o)
  if host.open("A/B") != 0 then
    libfco.text("opened ")
  end
  return n
end

; Levels n, n - 1, ... 1 alternate between this bank and bank 2, and each enters a block of
; bkdat (fixed) from its own bank.
pub recursive func down(n: byte): word
  if n == 0 then
    return 0
  end
  return word(bkdat.get(n)) + word(SIG[0]) + bkptr.two(n - 1)
end

pub func run()
  libfco.word4(bkdat.sum())
  libfco.word4(bkdat.across())
  libfco.hex(copy())
  libfco.put(' ')
  libfco.hex(mark())
  libfco.put(10)
  libfco.word4(bkdat.files())
  libfco.word4(down(20))
  libfco.hex(mark())
  libfco.put(10)
end
''',
    # Bank 2.
    'bktwo': '''module bktwo
import bkdat
import bkone

const SIG: [1]byte = [$B2]

pub func tag(): word
  return word(SIG[0]) * 3
end

pub recursive func down(n: byte): word
  if n == 0 then
    return 0
  end
  return word(bkdat.get(n)) + word(SIG[0]) + bkone.down(n - 1)
end
''',
    'bkmain': '''module bkmain
import libfco
import bkptr
import bkdat
import bkone
import bktwo

asm func aim()
  LDA #<bktwo.tag
  STA bkdat.raw
  LDA #>bktwo.tag
  STA bkdat.raw+1
end

pub func main()
  aim()
  bkptr.two = @bktwo.down
  bkdat.fill()
  bkone.run()
  libfco.text("done")
  libfco.put(10)
end
''',
}
PROGRAM_BANKS = ['bank      WIN 1 $81 BKONE.BIN', 'bank      WIN 2 $82 BKTWO.BIN',
                 'bank      WIN 32 $0C', 'bank      WIN 33 $0D',
                 'place     bkone WIN 1', 'place     bktwo WIN 2',
                 'region    ra WIN 32', 'region    rb WIN 33']
INPUT = b'hello, BBC\r\n'
# sum: a is 99, 1, 2, ... 63 and b 200, 199, ... 137: 2,115 + 10,784. across: a[5] + 3 * $B2 +
# a[6]. copy: 12 bytes, and bank 1's mark. files: the bytes of "hello, B". down(20): 1 + ... + 20
# and ten levels of each bank's mark.
PROGRAM_OUT = (b'3263\n' + b'%04X\n' % (5 + 3 * 0xB2 + 6) + b'0C A1\n'
               + b'%04X\n' % sum(INPUT[:8]) + b'%04X\n' % (210 + 10 * 0xA1 + 10 * 0xB2)
               + b'A1\ndone\n')


def write_program(d, modules):
    for name, text in modules.items():
        with open(os.path.join(d, name + '.lth'), 'w') as f:
            f.write(text)
    shutil.copy(os.path.join(CASES, 'libfco.lth'), d)


@unittest.skipUnless(HAVE_TOOLS, 'compiler or emulator missing')
class Program(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lathe-bbc-bank-')
        self.addCleanup(shutil.rmtree, self.dir, True)
        write_program(self.dir, PROGRAM)

    def run_with(self, env, tag):
        return build_and_run(os.path.join(self.dir, 'bkmain.lth'), env, os.path.join(self.dir, tag),
                             files={'INPUT': INPUT})

    def test_banked(self):
        env = bank_env(os.path.join(self.dir, 'bank.env'), PROGRAM_BANKS, ports=0)
        status, out, err, disk, entries = self.run_with(env, 'bank')
        self.assertEqual(out, PROGRAM_OUT)
        self.assertEqual((status, err), (0, b''))
        self.assertEqual(read(os.path.join(disk, 'OUTPUT')), INPUT)
        m = {(e.kind, e.name): e for e in entries}
        self.assertEqual((m['V', 'bkdat.a'].addr, m['V', 'bkdat.a'].bank), (m['V', 'bkdat.b'].addr, 32))
        self.assertEqual(m['V', 'bkdat.b'].bank, 33)
        self.assertEqual({m['F', 'bkone.run'].bank, m['F', 'bktwo.down'].bank}, {1, 2})
        self.assertIsNone(m['F', 'bkdat.across'].bank)
        self.assertEqual(m['F', 'bktwo.tag'].bank, 2)       # not kept: the call inside is a far call
        self.assertNotEqual(m['V', 'bkdat.raw'].addr & 0xFF, 0xFF)    # JMP (raw) on an NMOS 6502

    def test_all_in_one(self):
        env = bank_env(os.path.join(self.dir, 'flat.env'), [], base=FLAT_ENV, ports=0)
        status, out, err, disk, entries = self.run_with(env, 'flat')
        self.assertEqual((status, out, err), (0, PROGRAM_OUT, b''))


def sixteen():
    """Sixteen modules, s00 to s15, each placed in its bank of the module: chain() of each adds
    its mark to the next one's, through a far call into the next bank, and marks() writes its
    second mark and then the next one's."""
    modules = {}
    for n in range(16):
        nxt = 's%02d' % (n + 1)
        last = n == 15
        modules['s%02d' % n] = ('module s%02d\nimport libfco\n' % n + ('' if last else 'import %s\n' % nxt)
                                + 'const SIG: [2]byte = [%d, $%02X]\n' % (n + 1, 0xF0 + n)
                                + 'pub func chain(): word\n'
                                + ('  return word(SIG[0])\n' if last else
                                   '  return word(SIG[0]) + %s.chain()\n' % nxt)
                                + 'end\npub func marks()\n  libfco.hex(SIG[1])\n'
                                + ('' if last else '  %s.marks()\n' % nxt) + 'end\n')
    modules['sixteen'] = ('module sixteen\nimport libfco\nimport s00\n'
                          'pub func main()\n  libfco.word4(s00.chain())\n  s00.marks()\n'
                          '  libfco.put(10)\nend\n')
    lines = ['bank      WIN %d $%02X S%02d.BIN' % (n or 16, 0x80 + n, n) for n in range(16)]
    lines += ['place     s%02d WIN %d' % (n, n or 16) for n in range(16)]
    return modules, lines


@unittest.skipUnless(HAVE_TOOLS, 'compiler or emulator missing')
class SixteenBanks(unittest.TestCase):
    def test_every_bank_of_the_module(self):
        with tempfile.TemporaryDirectory(prefix='lathe-bbc-bank-') as d:
            modules, lines = sixteen()
            write_program(d, modules)
            env = bank_env(os.path.join(d, 'sixteen.env'), lines, ports=0)
            status, out, err, disk, entries = build_and_run(os.path.join(d, 'sixteen.lth'), env,
                                                            os.path.join(d, 'run'))
        self.assertEqual(out, b'0088\n' + b''.join(b'%02X' % (0xF0 + n) for n in range(16)) + b'\n')
        self.assertEqual((status, err), (0, b''))
        banks = sorted(e.number for e in entries if e.kind == 'W')
        self.assertEqual(banks, list(range(1, 17)))


# ---- What it costs ------------------------------------------------------------------------

TIMING = '''module fctime
import libfca
import libfcb
import libfcc
pub func main()
  var i: byte
  var w: word
  for i = 1 to LOOPS do
    w = libfcc.leaf(5)
  end
end
'''
LIBS = ('libfcc.lth', 'libfco.lth', 'libfca.lth', 'libfcb.lth', 'libfct.lth')

# The same calls made from bank 2 (fcloop, placed with libfcb) into bank 1.
LOOP_MAIN = '''module fctime
import fcloop
pub func main()
  fcloop.run()
end
'''
LOOP = '''module fcloop
import libfca
import libfcb
import libfcc
pub func run()
  var i: byte
  var w: word
  for i = 1 to LOOPS do
    w = libfcc.leaf(5)
  end
end
'''

WITH_TIMING = '''module wtime
import libwt
pub func main()
  var i: byte
  for i = 1 to LOOPS do
    libwt.get(i & 15)
  end
end
'''
# The same blocks entered from code in bank 1 (wloop).
WITH_LOOP_MAIN = '''module wtime
import wloop
pub func main()
  wloop.run()
end
'''
WITH_LOOP = '''module wloop
import libwt
pub func run()
  var i: byte
  for i = 1 to LOOPS do
    libwt.get(i & 15)
  end
end
'''
WITH_LIB = '''module libwt
var last: byte
#if BLOCK
var table: [16]byte in work
#else
var table: [16]byte
#end
; The block is the function's last statement, as for Wendy 2's measurement.
pub func get(i: byte)
#if BLOCK
  with work do
    last = table[i]
  end
#else
  last = table[i]
#end
end
'''


@unittest.skipUnless(HAVE_TOOLS, 'compiler or emulator missing')
class Costs(unittest.TestCase):
    """Cycles of one call: two runs, 110 and 10 calls, so that the start-up drops out."""

    def per_call(self, files, main, lines, base, defines=()):
        found = []
        for loops in (110, 10):
            with tempfile.TemporaryDirectory(prefix='lathe-bbc-cost-') as d:
                for name in files:
                    shutil.copy(os.path.join(CASES, name), d)
                for name, text in main.items():
                    with open(os.path.join(d, name + '.lth'), 'w') as f:
                        f.write(text)
                env = bank_env(os.path.join(d, 'x.env'), lines, base=base, ports=0)
                found.append(cycles(os.path.join(d, list(main)[-1] + '.lth'), env, d,
                                    ['LOOPS=%d' % loops] + list(defines)))
        return (found[0] - found[1]) / 100

    def test_a_far_call(self):
        """From fixed code into bank 1, as test_farcall.py measures Wendy 2's 182."""
        banked = self.per_call(LIBS, {'fctime': TIMING}, FARCALL, BANK_ENV)
        flat = self.per_call(LIBS, {'fctime': TIMING}, [], FLAT_ENV)
        self.assertEqual(banked - flat, FAR_CALL)

    def test_a_far_call_between_banks(self):
        modules = {'fcloop': LOOP, 'fctime': LOOP_MAIN}
        banked = self.per_call(LIBS, modules, FARCALL + ['place     fcloop WIN 2'], BANK_ENV)
        flat = self.per_call(LIBS, modules, [], FLAT_ENV)
        self.assertEqual(banked - flat, FAR_CALL_BETWEEN_BANKS)

    def test_a_with_block(self):
        """The cycles of a block, as the function's last statement, entered from fixed code and
        from code in a bank of the module: banked (the region in slot 12), and all in one."""
        region = ['bank      WIN 32 $0C', 'region    work WIN 32']
        found = []
        for modules, placed in (({'libwt': WITH_LIB, 'wtime': WITH_TIMING}, []),
                                ({'libwt': WITH_LIB, 'wloop': WITH_LOOP, 'wtime': WITH_LOOP_MAIN},
                                 ['bank      WIN 1 $81 WLOOP.BIN', 'place     wloop WIN 1'])):
            banked = self.per_call((), modules, region + placed, BANK_ENV, ['BLOCK=1'])
            flat = self.per_call((), modules, [], FLAT_ENV, ['BLOCK=1'])
            bare = self.per_call((), modules, [], FLAT_ENV, ['BLOCK=0'])
            found.append((banked - bare, flat - bare))
        self.assertEqual(found, [WITH_BLOCK, WITH_BLOCK_FROM_A_BANK])


# Measured (2026-11-14; 2026-11-15 with the module's slot in a variable, rt_bbc.mslot, which the
# ROM form sets at run time: a cycle more for each switch to a bank of the module, where it was
# 186, 195 and 78). Wendy 2's: 182 a far call, 90 a block banked and 24 all in one
# (configurations.md).
FAR_CALL = 187
FAR_CALL_BETWEEN_BANKS = 197
# 2026-11-18: 3 more each, the store of get's parameter on entry, which the block needs (it
# reads `i` after rt_with.map) and the version without a block no longer makes (nothing reads
# the slot there: code-model.md, "Stores that nothing reads").
WITH_BLOCK = (67, 27)               # (banked, all in one)
WITH_BLOCK_FROM_A_BANK = (82, 27)


if __name__ == '__main__':
    unittest.main()
