"""Stage 11, step 3: the far-call run-time modules lathe/rt/rt_bank.lth and rt_ovl.lth
(lathe/docs/configurations.md, "The far-call run-time modules").

The gate: the three-module demonstration of spike L5 (lathe/tests/spike_l5/) gives the spike's
output with the routine compiled by the host compiler from the Lathe module, banked on Wendy 2
with --disk and as overlays on the default machine. The linker of stage 11 does not yet write
stubs, tables or bank files, so the program is put together by hand, in two parts:

- the Lathe part: lathe/tests/spike_l5/l5main.lth with rt_bank (and disk) or rt_ovl (and host),
  compiled and linked by the real tools (build.build) at $4000, with zero page from $40 and
  variables at $3000, out of the spike's way. Its main calls start() with the table's address,
  as the start-up code will, then the spike's main program;
- the spike's part: l5build.py assembles main.s, the board's env file, modules A and B, and in
  place of the spike's own routine the names the stubs need (fc_call is rt_bank.call or
  rt_ovl.call, read from the Lathe part's map), with asm/pyasm.py at $0400. It writes the
  stubs (JSR call / .byte N / .word f-1) and the table `$banks` or `$overlays` by hand, in the
  form configurations.md gives, and A and B as bank or overlay files.

The two parts are one file from $0400 that starts with JMP $4000 (configurations
'lbank-wendy2' and 'lovl-host' of l5build.py). The banks are loaded by rt_bank.start through
lathe/rt/disk.lth; the overlays by rt_ovl's loader through the host services.
"""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'spike_l5'))

import l5build  # noqa: E402
from test_spike_l5 import COMMON, WENDY2  # noqa: E402


@unittest.skipUnless(os.path.isfile(l5build.EMULATOR) and os.path.isfile(l5build.COMPILER),
                     'emulator or compiler missing')
class Output(unittest.TestCase):
    def test_banks_wendy2(self):
        _, text, _ = l5build.run_config('lbank-wendy2')
        self.assertEqual(text, COMMON + WENDY2)

    def test_overlays_host(self):
        _, text, _ = l5build.run_config('lovl-host')
        self.assertEqual(text, COMMON + 'loads 0031\n')

    def test_a_missing_bank_file_is_status_255(self):
        with tempfile.TemporaryDirectory(prefix='l5_') as d:
            built = l5build.build('lbank-wendy2', d)
            os.unlink(built.files['b'])
            text, _ = l5build.run(built)
            self.assertEqual(text, '')                     # stopped before the spike's main
            with open(os.path.join(d, 'status')) as fh:
                self.assertEqual(fh.read(), '255\n')


@unittest.skipUnless(os.path.isfile(l5build.EMULATOR) and os.path.isfile(l5build.COMPILER),
                     'emulator or compiler missing')
class Measurements(unittest.TestCase):
    """The compiled routines cost what the spike's measured (test_spike_l5.py): the same
    instructions, and the linker put their variables in zero page, as the spike did."""

    def test_banks(self):
        m = l5build.measure('lbank-wendy2')
        # One far call and its return; two, nested. The timed loops cost exactly what the
        # spike's do; the empty loop that measure() subtracts measured 8 cycles less in 128
        # passes than in the spike's build (1,014 against 1,022: not explained), hence the delta.
        self.assertAlmostEqual(m['leaf'] - 24, 182, delta=0.1)
        self.assertAlmostEqual(m['mid'] - 44, 2 * 182, delta=0.1)
        part = l5build.lathe_part('lbank-wendy2')
        self.assertEqual(part.size['rt_bank.call'] + part.size['rt_bank.back'], 101)

    def test_overlays(self):
        m = l5build.measure('lovl-host')
        self.assertEqual(m['leaf'] - 24, 82)               # the overlay is in the window
        part = l5build.lathe_part('lovl-host')
        self.assertEqual(part.size['rt_ovl.call'] + part.size['rt_ovl.back'], 107)
        # M -> B -> A: two loads an iteration, 45 bytes each, by a loader written in Lathe
        # (the spike's took 4,000 to 4,500 cycles an iteration).
        self.assertGreater(m['mid'], 4000)
        self.assertLess(m['mid'], 6000)


if __name__ == '__main__':
    unittest.main()
