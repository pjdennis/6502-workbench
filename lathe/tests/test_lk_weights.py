"""Weights for the slots of functions not read yet, whatever their number (lathe/docs/bbc.md,
"The order of the object files").

A module's WGT record weights the parameters of functions it calls in other modules; for a
function whose FUNC record the linker has not read yet the weight waits (lk_scan.MAX_PENDING of
them: 64 at full capacities, 16 in the 32K build). More than that was link error 41, so that the
same objects linked or not by the order they were named in. Now the waiting weights that do not
fit are not held: the WGT records of the files that gave them are read again once every file is
read, and every weight that waited is added then. A weight is a saturating sum, the same in any
order, so the output is that of a linker that held them all.

Each link here is compared with one whose table holds every waiting weight (WHOLE), at full
capacities, the small build's and the 32K build's.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_lk_support import Obj, link, NOBODY, EITHER, PARAM  # noqa: E402
from test_lk_fixup_runs import link_at  # noqa: E402

# One byte of zero page: the two slots of each function of b compete for it, so that every weight
# shows in the output.
ENV = 'cpu 6502\nzeropage $10 $10\ncode $0200 $BFFF\ndata $C000 $EFFF\nexit return\n'
# A table that holds every waiting weight: the work area large enough for it (lk_name.MARKS above
# the four columns of 4,000 entries).
WHOLE = {'lk_scan': {'MAX_PENDING': 4000}, 'lk_name': {'MARKS': 16000}, 'lk_tab': {'MAX_NODES': 2000}}
LEVELS = {'full': {}, 'small build': True, '32K build': 2}


def program(callers, callees, slots=2, bad=False, others=0):
    """Module a, read first, whose main calls `callees` functions of module b (read after it),
    each with `slots` parameters of class EITHER, and weights them from `callers` places: so the
    weights wait for b. With `bad`, one weight names a slot b.f0 does not have. With `others`,
    a defines that many variables and functions of its own first, so that the rows of b's
    functions are not the rows of their symbols."""
    a = Obj('a')
    for i in range(others):
        a.var('v%d' % i, 1, weight=1)
        a.func('g%d' % i, b'\x60')
    c = a.code()
    calls = []
    for i in range(callees):
        c.abs(0x20, a.f('b.f%d' % i))
        calls.append((a.f('b.f%d' % i), 0, NOBODY))
    c.raw(0x60)
    a.func('main', c, calls=calls)
    for k in range(callers):
        for i in range(callees):
            a.wgt((a.f('b.f%d' % i), (i + k) % slots, 1 + (i * 7 + k) % 40))
    if bad:
        a.wgt((a.f('b.f0'), slots, 3))
    b = Obj('b')
    for i in range(callees):
        b.func('f%d' % i, b'\x60', slots=[(1, EITHER, 1, PARAM, 'p%d' % j) for j in range(slots)])
    return [a, b]


class Weights(unittest.TestCase):
    def test_more_weights_waiting_than_the_table_holds_link_as_if_it_held_them_all(self):
        for callers, callees, others in ((1, 20, 0), (3, 40, 0), (2, 120, 0), (2, 120, 7)):
            objects = program(callers, callees, others=others)
            whole = link_at(objects, WHOLE, ENV)
            self.assertEqual(whole[:2], (0, ''))
            for name, level in LEVELS.items():
                with self.subTest(waiting=callers * callees, others=others, capacities=name):
                    self.assertEqual(link_at(objects, level, ENV), whole)

    def test_weights_for_functions_nothing_defines_are_dropped(self):
        a = Obj('a')
        a.func('main', b'\x60')
        for i in range(257):
            a.wgt((a.f('f%d' % i), 0, 1))
        r = link([a], ENV)
        self.assertEqual((r.status, r.errors), (0, ''))

    def test_a_weight_for_a_slot_its_function_lacks_is_still_found(self):
        for callees in (4, 120):
            with self.subTest(waiting=callees + 1):
                status, said, files = link_at(program(1, callees, bad=True), {}, ENV)
                self.assertEqual(status, 1)
                self.assertTrue(said.startswith('link error 6: object file is damaged'), said)
                self.assertIn('m0.lo', said)


if __name__ == '__main__':
    unittest.main()
