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
    r = subprocess.run([build.EMULATOR, image, '--output', '-', '--no-dump'], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, cwd=os.path.dirname(image))
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

    def test_the_marks_of_spike_l5_are_in_their_banks(self):
        m = mapped('farcall.lth', 'farcall_banks.env')
        self.assertEqual(m['D', 'libfcc.sig'].bank, 1)
        self.assertEqual(m['D', 'libfcb.sig'].bank, 2)


if __name__ == '__main__':
    unittest.main()
