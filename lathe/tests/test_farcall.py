"""Stage 11: far calls through the stubs and tables the linker writes, with the run-time modules
lathe/rt/rt_bank.lth and rt_ovl.lth (lathe/docs/configurations.md, "The far-call run-time
modules").

The program is spike L5's three-module demonstration written in Lathe,
lathe/tests/cases/e2e-config/farcall.lth with its modules libfca, libfcb and libfcc, which
test_cases.py runs in every configuration. Here: what the far calls cost, against the same
objects linked all in one; the sizes of the routine and the stubs; and a missing bank file.
The timing program calls libfcc.leaf LOOPS times; two runs with different LOOPS give the cycles
of one call, so that the start-up (loading the banks) drops out. It imports libfca and libfcb,
which the environment places, but does not call them.
"""
import os
import re
import shutil
import subprocess
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
WENDY_CYCLES = re.compile(r'cpu_cycles=(\d+)')
HOST_CYCLES = re.compile(rb'[Ee]xecuted (\d+) cycles')


def env(name):
    return os.path.join(CASES, name)


def wendy_cycles(image, disk):
    """Runs a Wendy 2 program on the files of disk. Returns its CPU cycles."""
    described = mapenv.read_env(env('farcall_flat.env'))
    report = boards.emulate(boards.BOARDS['wendy2disk'], image, described, disk)
    return int(WENDY_CYCLES.search(report).group(1))


def host_cycles(image):
    """Runs a program on the default machine in the directory of its image, where its overlay
    files are. Returns its CPU cycles."""
    with tempfile.TemporaryDirectory(prefix='lathe-load-') as d:
        r = subprocess.run(build.image_command(image, None, d) + ['--output', '-', '--no-dump'],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=os.path.dirname(image))
    return int(HOST_CYCLES.search(r.stderr).group(1))


def copy_program(d, main_name, main_text):
    """The modules of farcall.lth and a main module, in directory d. Returns its path."""
    for name in LIBS:
        shutil.copy(os.path.join(CASES, name), d)
    source = os.path.join(d, main_name + '.lth')
    with open(source, 'w') as f:
        f.write(main_text)
    return source


def timed(environment, loops):
    """CPU cycles of the timing program, on Wendy 2 or the default machine, built with an
    environment of CASES."""
    with tempfile.TemporaryDirectory(prefix='fctime_') as d:
        source = copy_program(d, 'fctime', TIMING)
        image = os.path.join(d, 'fctime.bin')
        build.build(source, image, env(environment), keep=os.path.join(d, 'work'),
                    defines=['LOOPS=%d' % loops])
        if boards.board_for(env(environment)) is None:
            return host_cycles(image)
        disk = os.path.join(d, 'disk')
        os.makedirs(disk)
        build.window_files(mapenv.read_env(env(environment)), d, disk)
        return wendy_cycles(image, disk)


def per_call(environment):
    return (timed(environment, 110) - timed(environment, 10)) / 100


@unittest.skipUnless(os.path.isfile(build.EMULATOR) and os.path.isfile(build.COMPILER),
                     'emulator or compiler missing')
class Banks(unittest.TestCase):
    def test_a_far_call_costs_182_cycles_more_than_a_call(self):
        # The spike's measurement (spikes.md, "Result of L5"), now with the linker's stubs.
        self.assertEqual(per_call('farcall_banks.env') - per_call('farcall_flat.env'), 182)

    def test_sizes(self):
        with tempfile.TemporaryDirectory(prefix='fcsize_') as d:
            build.build(os.path.join(CASES, 'farcall.lth'), os.path.join(d, 'fc.bin'),
                        env('farcall_banks.env'), keep=os.path.join(d, 'work'))
            entries = mapenv.read_map(os.path.join(d, 'work', 'farcall.map'))
        size = {e.name: e.size for e in entries if e.kind in ('F', 'D')}
        self.assertEqual(size['rt_bank.call'] + size['rt_bank.back'], 101)
        stubs = [e for e in entries if e.kind == 'T']
        self.assertEqual(len(stubs), 7)
        self.assertTrue(all(e.size == 6 for e in stubs))
        # The table: the window, the number of banks, three bytes a bank and the names.
        self.assertEqual(size['$banks'], 3 + 2 * 3 + 2 * len('FCBANK1.BIN\0'))

    def test_a_missing_bank_file_is_status_255(self):
        with tempfile.TemporaryDirectory(prefix='fcmiss_') as d:
            image = os.path.join(d, 'fc.bin')
            build.build(os.path.join(CASES, 'farcall.lth'), image, env('farcall_banks.env'),
                        keep=os.path.join(d, 'work'))
            os.unlink(os.path.join(d, 'FCBANK2.BIN'))
            disk = os.path.join(d, 'disk')
            os.makedirs(disk)
            status, out, err = build.run_program(image, env('farcall_banks.env'), disk=disk)
            self.assertEqual((status, out), (255, b''))       # stopped before main



@unittest.skipUnless(os.path.isfile(build.EMULATOR) and os.path.isfile(build.COMPILER),
                     'emulator or compiler missing')
class Overlays(unittest.TestCase):
    def test_a_call_into_the_overlay_in_the_window_costs_82_cycles_more(self):
        self.assertEqual(per_call('farcall_ovl.env') - per_call('farcall_host.env'), 82)

    def test_the_number_of_loads(self):
        # As spike L5's: 5 for the nested calls (in, in, in, and two loads on the way back),
        # 40 for 20 levels of recursion that each cross and come back, 1 for ptr1, 3 for ptr2,
        # none for ptr3, whose overlay is in the window.
        with open(os.path.join(CASES, 'farcall.lth')) as f:
            text = f.read()
        text = text.replace('import libfco\n', 'import libfco\nimport rt_ovl\n')
        text = text.rstrip('\n')
        self.assertTrue(text.endswith('\nend'))
        text = text[:-3] + '  libfco.text("loads ")\n  libfco.word4(rt_ovl.loads())\nend\n'
        with tempfile.TemporaryDirectory(prefix='fcload_') as d:
            source = copy_program(d, 'farcall', text)
            image = os.path.join(d, 'farcall.bin')
            build.build(source, image, env('farcall_ovl.env'), keep=os.path.join(d, 'work'))
            status, out, _ = build.run_program(image, env('farcall_ovl.env'))
        with open(os.path.join(CASES, 'farcall.expected.out'), 'rb') as f:
            self.assertEqual(out, f.read() + b'loads 0031\n')

    def test_sizes(self):
        with tempfile.TemporaryDirectory(prefix='fcsize_') as d:
            build.build(os.path.join(CASES, 'farcall.lth'), os.path.join(d, 'fc.bin'),
                        env('farcall_ovl.env'), keep=os.path.join(d, 'work'))
            entries = mapenv.read_map(os.path.join(d, 'work', 'farcall.map'))
        size = {e.name: e.size for e in entries if e.kind in ('F', 'D')}
        self.assertEqual(size['rt_ovl.call'] + size['rt_ovl.back'], 107)
        self.assertEqual(size['$overlays'], 3 + 2 * 2 + 2 * len('FCOVL1.BIN\0'))
        windows = [(e.number, e.name) for e in entries if e.kind == 'W']
        self.assertEqual(windows, [(1, 'FCOVL1.BIN'), (2, 'FCOVL2.BIN')])

    def test_a_missing_overlay_file_is_status_255(self):
        with tempfile.TemporaryDirectory(prefix='fcmiss_') as d:
            image = os.path.join(d, 'fc.bin')
            build.build(os.path.join(CASES, 'farcall.lth'), image, env('farcall_ovl.env'),
                        keep=os.path.join(d, 'work'))
            os.unlink(os.path.join(d, 'FCOVL2.BIN'))
            status, out, err = build.run_program(image, env('farcall_ovl.env'))
            self.assertEqual((status, out), (255, b'nest '))   # at the first call into overlay 2



# What a `with` block costs: a function that reads a variable of the region CELL inside a block,
# against one that reads a fixed variable, called LOOPS times (lathe/docs/configurations.md,
# "What a block of a fixed region costs").
WITH_LIB = '''module libwt
var cell: byte in CELL
var plain: byte
pub func get(): byte
#if BLOCK
  with CELL do
    return cell
  end
#else
  return plain
#end
end
'''
WITH_TIMING = '''module wtime
import libwt
pub func main()
  var i: byte
  var b: byte
  for i = 1 to LOOPS do
    b = libwt.get()
  end
end
'''
WITH_BANKED = '''window    WIN $8000 $EFFF
switch    WIN bank $F000 $1F
bank      WIN 1 $11
region    CELL WIN 1
farcall   rt_bank
'''


def with_timed(d, environment, block, loops, region):
    """CPU cycles of WITH_TIMING built with farcall_flat.env (Wendy 2) and, unless `region` is
    None, the window entries with CELL banked ('banked') or fixed ('fixed'); with
    farcall_host.env when `environment` is 'host' (all in one, rt_with)."""
    work = os.path.join(d, '%s-%s-%d-%d' % (environment, region, block, loops))
    os.makedirs(work)
    with open(os.path.join(work, 'libwt.lth'), 'w') as f:
        f.write(WITH_LIB)
    source = os.path.join(work, 'wtime.lth')
    with open(source, 'w') as f:
        f.write(WITH_TIMING)
    with open(env('farcall_%s.env' % environment)) as f:
        text = f.read()
    if region is not None:
        banked = WITH_BANKED
        if region == 'fixed':
            banked = banked.replace('region    CELL WIN 1', 'region    CELL fixed')
        text = text.replace('code      $4000 $EFFF', 'code      $4000 $7FFF') + banked
    environment_file = os.path.join(work, 'wtime.env')
    with open(environment_file, 'w') as f:
        f.write(text)
    image = os.path.join(work, 'wtime.bin')
    build.build(source, image, environment_file, keep=os.path.join(work, 'work'),
                defines=['LOOPS=%d' % loops, 'BLOCK=%d' % block])
    if environment == 'host':
        return host_cycles(image)
    disk = os.path.join(work, 'disk')
    os.makedirs(disk)
    return wendy_cycles(image, disk)


def block_cost(environment, region):
    """Cycles a `with` block adds to a call, per call."""
    with tempfile.TemporaryDirectory(prefix='wtime_') as d:
        cost = [(with_timed(d, environment, block, 110, region)
                 - with_timed(d, environment, block, 10, region)) / 100 for block in (0, 1)]
    return cost[1] - cost[0]


@unittest.skipUnless(os.path.isfile(build.EMULATOR) and os.path.isfile(build.COMPILER),
                     'emulator or compiler missing')
class WithBlocks(unittest.TestCase):
    def test_a_block_of_a_banked_region(self):
        self.assertEqual(block_cost('flat', 'banked'), 94)

    def test_a_block_of_a_fixed_region_maps_nothing(self):
        # rt_bank.map(0), a region in fixed memory, touches no port, and unmap() of what it
        # gave returns at once.
        self.assertEqual(block_cost('flat', 'fixed'), 32)

    def test_a_block_all_in_one(self):
        # rt_with: a lone RTS each.
        self.assertEqual(block_cost('host', None), 24)


def mapped(source, environment):
    """The map of a program of CASES built with an environment of CASES, by name and kind."""
    with tempfile.TemporaryDirectory(prefix='fcmap_') as d:
        name = os.path.splitext(os.path.basename(source))[0]
        build.build(os.path.join(CASES, source), os.path.join(d, 'x.bin'), env(environment),
                    keep=os.path.join(d, 'work'))
        return {(e.kind, e.name): e for e in mapenv.read_map(os.path.join(d, 'work', name + '.map'))}


@unittest.skipUnless(os.path.isfile(build.COMPILER), 'compiler missing')
class Data(unittest.TestCase):
    """Constants and variables of a module in a window (step 8): cases/e2e-config/bankdata.lth
    runs in every configuration (test_cases.py); here is where each went."""

    def test_banks(self):
        m = mapped('bankdata.lth', 'bankdata_banks.env')
        self.assertEqual((m['D', 'libbkd.squares'].addr, m['D', 'libbkd.squares'].bank), (0x8000, 3))
        self.assertEqual((m['V', 'libbkd.calls'].addr, m['V', 'libbkd.calls'].bank), (0xEFFF, 3))
        self.assertLess(m['D', 'libbkd.$1'].addr, 0x8000)       # "squares ": its address is passed
        self.assertIsNone(m['D', 'libbkd.$1'].bank)
        self.assertEqual(m['F', 'libbkd.$init'].bank, 3)        # called by $init through its stub
        self.assertIn(('T', 'libbkd.$init'), m)

    def test_overlays(self):
        m = mapped('bankdata.lth', 'bankdata_ovl.env')
        self.assertEqual((m['D', 'libbkd.squares'].addr, m['D', 'libbkd.squares'].bank), (0x8000, 1))
        self.assertGreaterEqual(m['V', 'libbkd.calls'].addr, 0xC000)     # an overlay is loaded again
        self.assertIsNone(m['V', 'libbkd.calls'].bank)

    def test_kept_functions_and_a_read_only_bank(self):
        """cases/e2e-config/kept.lth: what has a `with` block or runs inside one is kept in
        fixed memory (k=N), what they call outside a block stays in the bank; bank 2 is
        read-only, so libkrom's variables are fixed and $banks loads only bank 3."""
        m = mapped('kept.lth', 'kept_banks.env')
        for name, bank in (('libkept.fill', 3), ('libkept.get', 3), ('libkept.sum', 3),
                           ('libkept.next', 3), ('libkept.step', 3), ('libkept.tally', 3),
                           ('libkept.add8', 3), ('libkrom.twice', 2)):
            self.assertEqual((m['F', name].kept, m['F', name].bank), (bank, None), name)
            self.assertLess(m['F', name].addr, 0x8000, name)
            self.assertNotIn(('T', name), m)
        for name, bank in (('libkept.begin', 3), ('libkept.show', 3), ('libkrom.report', 2),
                           ('libkrom.reset', 2)):
            self.assertEqual((m['F', name].kept, m['F', name].bank), (None, bank), name)
        self.assertIn(('T', 'libkept.begin'), m)                    # fill() calls it, from fixed code
        self.assertEqual(m['D', 'libkept.head'].bank, 3)           # only show() names it
        self.assertEqual(m['V', 'libkept.runs'].bank, 3)
        for name in ('libkept.count', 'libkept.total'):             # kept functions name them
            self.assertIsNone(m['V', name].bank, name)
        self.assertIsNone(m['D', 'libkept.steps'].bank)
        self.assertEqual(m['V', 'libkept.table'].bank, 4)          # its region's
        self.assertEqual(m['D', 'libkrom.label'].bank, 2)          # a constant: in the ROM
        for name in ('libkrom.calls', 'libkrom.last'):             # variables: never in it
            self.assertIsNone(m['V', name].bank, name)
            self.assertLess(m['V', name].addr, 0x4000, name)
        self.assertTrue(m['W', 'KROM2.BIN'].rom)
        self.assertFalse(m['W', 'KEPT3.BIN'].rom)
        self.assertEqual(m['D', '$banks'].size, 3 + 3 + len('KEPT3.BIN\0'))
        m = mapped('kept.lth', 'kept_ovl.env')
        self.assertEqual(m['F', 'libkept.fill'].kept, 1)
        self.assertEqual(m['F', 'libkept.step'].kept, 1)
        self.assertEqual(m['F', 'libkept.begin'].bank, 1)

    def test_blocks_of_a_region_the_compiler_is_told_is_fixed_keep_nothing(self):
        """cases/e2e-config/fixedblk.lth: with the region in a bank, libfixb's functions with a
        block and add8, called inside one, are kept in fixed memory; with the region fixed and
        FIXED_REGIONS (-ffwork), every function stays in bank 3 and nothing calls rt_bank.map."""
        functions = ('libfixb.fill', 'libfixb.sum', 'libfixb.get', 'libfixb.add8')
        m = mapped('fixedblk.lth', 'fixedblk_banks.env')
        for name in functions:
            self.assertEqual((m['F', name].kept, m['F', name].bank), (3, None), name)
        self.assertEqual(m['V', 'libfixb.table'].bank, 4)
        m = mapped('fixedblk.lth', 'fixedblk_fixed.env')
        for name in functions:
            self.assertEqual((m['F', name].kept, m['F', name].bank), (None, 3), name)
        self.assertIsNone(m['V', 'libfixb.table'].bank)
        self.assertLess(m['V', 'libfixb.table'].addr, 0x4000)

    def test_the_marks_of_spike_l5_are_in_their_banks(self):
        m = mapped('farcall.lth', 'farcall_banks.env')
        self.assertEqual(m['D', 'libfcc.sig'].bank, 1)
        self.assertEqual(m['D', 'libfcb.sig'].bank, 2)


if __name__ == '__main__':
    unittest.main()
