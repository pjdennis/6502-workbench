"""Spike L5: far calls three ways (lathe/docs/spikes.md, "Result of L5").

The same three hand-written modules (lathe/tests/spike_l5/) are placed all in fixed memory,
in banks of Wendy 2 (two forms of stub), and in overlays loaded through the host file
services of the emulator's default machine. Each build runs on the emulator; the program
prints what each kind of far call gave back, and the timing loops give the cycles that
spikes.md records. The numbers are exact, because the emulator counts cycles exactly: a
change to any of them is a change to the measurements in spikes.md.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'spike_l5'))

import l5build  # noqa: E402

# What every configuration prints: A, X and carry after each kind of far call.
COMMON = ('nest 06 A1 1\n'      # M -> A -> B -> A: n + 1, A's mark, carry set
          'rec 00D2\n'          # 20 levels of recursion between A and B: 0 + 1 + ... + 20
          'ptr1 42 B2 0\n'      # M through a pointer to B: 2x, B's mark, carry clear
          'ptr2 44 B2 0\n'      # A through a pointer to B
          'ptr3 31 A1 1\n')     # A through a pointer to A (its stub)
WENDY2 = 'irq ok\nport ok\n'    # timer interrupts making far calls; port B bits 5-7 kept


@unittest.skipUnless(os.path.isfile(l5build.EMULATOR), 'emulator not built: run make')
class Output(unittest.TestCase):

    def check(self, config, expected):
        _, text, _ = l5build.run_config(config)
        self.assertEqual(text, expected)

    def test_fixed_host(self):
        self.check('fixed-host', COMMON)

    def test_overlays_host(self):
        # 49 loads: overlays are loaded again on every return into the other one.
        self.check('ovl-host', COMMON + 'loads 0031\n')

    def test_fixed_wendy2(self):
        self.check('fixed-wendy2', COMMON + WENDY2)

    def test_banks_wendy2(self):
        self.check('bank-wendy2', COMMON + WENDY2)

    def test_banks_fast_stubs_wendy2(self):
        self.check('bankfast-wendy2', COMMON + WENDY2)


@unittest.skipUnless(os.path.isfile(l5build.EMULATOR), 'emulator not built: run make')
class Measurements(unittest.TestCase):
    """Cycles of the loops without the loop's own cost: M_LEAF is LDA #5 / JSR a_leaf and
    a_leaf's body, 24 cycles with a plain JSR; the far-call overhead is the rest."""

    @classmethod
    def setUpClass(cls):
        cls.m = {c: l5build.measure(c) for c in l5build.CONFIGS}

    def test_all_fixed_is_a_plain_call(self):
        for c in ('fixed-host', 'fixed-wendy2'):
            self.assertEqual(self.m[c]['leaf'], 24)
            self.assertEqual(self.m[c]['mid'], 44)
            self.assertNotIn('stub', self.m[c])

    def test_banks(self):
        m = self.m['bank-wendy2']
        self.assertEqual((m['stub'], m['routine']), (6, 101))
        self.assertEqual(m['leaf'] - 24, 182)              # one far call and its return
        self.assertEqual(m['mid'] - 44, 2 * 182)           # two, nested

    def test_banks_fast_stubs(self):
        m = self.m['bankfast-wendy2']
        self.assertEqual((m['stub'], m['routine']), (12, 62))
        self.assertEqual(m['leaf'] - 24, 130)
        self.assertEqual(m['mid'] - 44, 2 * 130)

    def test_bank_loading(self):
        # Loading a bank at start-up through the file ports: 21 cycles a byte.
        self.assertAlmostEqual(self.m['bank-wendy2']['per_byte'], 21, delta=0.1)

    def test_overlays(self):
        m = self.m['ovl-host']
        self.assertEqual((m['stub'], m['routine'], m['loader']), (6, 107, 30))
        self.assertEqual(m['leaf'] - 24, 82)               # the overlay is in the window
        self.assertAlmostEqual(m['per_byte'], 43, delta=0.1)
        # M -> B -> A with A and B in turn: two loads an iteration, about 2,100 cycles each
        # for 45 bytes, most of it the bytes.
        self.assertGreater(m['mid'], 4000)
        self.assertLess(m['mid'], 4500)


if __name__ == '__main__':
    unittest.main()
