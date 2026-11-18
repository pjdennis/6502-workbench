"""A function of any number of fix-ups links (lathe/docs/architecture.md, "Memory in the linker"):
the image pass holds a function's fix-ups in runs of what the work area has room for
(lk_tab.MAX_FIXES), reading its FIX record again for the next run, and works out how much the
code shrinks before an offset outside the run it holds from the record itself.

The functions here are made by hand (test_lk_support), with more fix-ups than a run holds at
every capacity: instructions that shrink and some that do not, one-byte fix-ups, branches back
and forward across the ends of runs, jumps to labels of the function far behind and far ahead,
calls, its own slots in zero page, and a second copy for an interrupt context, whose slots are
elsewhere. Each is linked by the host linker at full capacities, where the assembler path must
give the same image (an independent reckoning of every shrink, branch and label), and at the
small and the 32K build's capacities and with runs of only 16 fix-ups, which must write every
file as a link that holds the whole function at once.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_lk_support import Obj, link, word, MUST, EITHER, NEVER, LOCAL, NOBODY, INTERRUPT  # noqa: E402
import lk_small  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ENV = 'cpu 6502\nzeropage $00 $FF\ncode $0200 $BFFF\ndata $C000 $EFFF\nexit return\n'


def big_function(o, name, units, own_slots=True):
    """Add to Obj o function `name`, of about 5 fix-ups a unit. Returns its fix-up count."""
    c = o.code()
    me = o.f(name)
    near = o.v('near')          # in zero page: its instructions shrink
    far = o.v('far')            # never in zero page
    helper = o.f('helper')
    labels = []
    forward = []                # (index in c.fixes, unit it jumps to)
    starts = {}
    for i in range(units):
        starts[i] = c.here()
        labels.append(c.here())
        c.abs(0xAD, near)                       # LDA near: kind 5, shrinks
        c.abs(0xAD, far)                        # LDA far: kind 5, does not
        c.byte(0xA9, 2, far)                    # LDA #<far
        if own_slots:
            c.abs(0x8D, me, slot=i % 3)         # STA a slot of its own: shrinks where it is in zero page
        if i % 3 == 0:
            c.abs(0x20, helper)                 # JSR helper
        if i % 5 == 4:
            c.raw(0xD0)                         # BNE back to the start of the unit before
            c.raw((starts[i - 1] - (c.here() + 1)) & 0xFF)
        if i % 7 == 6 and i >= 40:
            c.abs(0x4C, me, add=labels[i - 40], kind=1)    # JMP to a label far behind
        if i % 11 == 0 and i + 37 < units:
            forward.append((len(c.fixes), i + 37))
            c.abs(0x4C, me, add=0, kind=1)                 # JMP to a label far ahead
        if i % 13 == 12:
            c.raw(0xF0, 0x03, 0xEA, 0xEA, 0xEA)            # BEQ over three bytes
    c.raw(0x60)
    for k, unit in forward:
        at, kind, sym, slot, add = c.fixes[k]
        c.fixes[k] = (at, kind, sym, slot, labels[unit])
    slots = [(1, EITHER, 50, LOCAL, 'a'), (1, EITHER, 40, LOCAL, 'b'), (2, NEVER, 0, LOCAL, 'c')] if own_slots else []
    o.func(name, c, slots=slots, calls=[(helper, 0, NOBODY)])
    return len(c.fixes)


def program(units, irq=True):
    """A module whose main calls `big`, as an interrupt function does too if irq."""
    o = Obj('t')
    o.var('near', 1, MUST)
    o.var('far', 2, NEVER)
    hc = o.code()
    hc.raw(0x60)
    o.func('helper', hc, slots=[(1, EITHER, 5, LOCAL, 'h')])
    n = big_function(o, 'big', units)
    m = o.code()
    m.abs(0x20, o.f('big'))
    m.raw(0x60)
    o.func('main', m, calls=[(o.f('big'), 0, NOBODY)])
    if irq:
        q = o.code()
        q.abs(0x20, o.f('big'))
        q.raw(0x40)
        o.func('irq', q, calls=[(o.f('big'), 0, NOBODY)], flags=INTERRUPT)
    return o, n


def link_at(objects, values, env=ENV):
    """The host linker with the capacities `values` ({module: {NAME: value}}), or a level of
    lk_small (True, 2): (status, error output, {file: bytes} written)."""
    with tempfile.TemporaryDirectory() as tmp:
        env_path = os.path.join(tmp, 'test.env')
        with open(env_path, 'w') as f:
            f.write(env)
        paths = []
        for i, obj in enumerate(objects):
            paths.append(os.path.join(tmp, 'm%d.lo' % i))
            with open(paths[-1], 'wb') as f:
                f.write(obj.to_bytes())
        code = ('import json, sys, lk_small\n'
                'lk_small.load_values(json.loads(sys.argv[1]))\n'
                'import env, link\n'
                'env.start(sys.argv[2:])\n'
                'link.main()\n')
        if not isinstance(values, dict):
            values = lk_small.capacities(values)
        r = subprocess.run([sys.executable, '-c', code, json.dumps(values), env_path, objects[0].name,
                            os.path.join(tmp, 'out.bin'), os.path.join(tmp, 'out.map')] + paths,
                           cwd=HERE, capture_output=True)
        files = {}
        for name in ('out.bin', 'out.map'):
            p = os.path.join(tmp, name)
            if os.path.exists(p):
                with open(p, 'rb') as f:
                    files[name] = f.read()
        return r.returncode, r.stderr.decode('latin-1'), files


# A link that holds every function's fix-ups at once (work area large enough for that).
WHOLE = {'lk_tab': {'MAX_FIXES': 1500, 'MAX_NODES': 1530}}
RUNS = {'small build': True, '32K build': 2, 'runs of 16': {'lk_tab': {'MAX_FIXES': 16}}}


class Runs(unittest.TestCase):
    def test_more_fix_ups_than_full_capacity_link_as_the_assembler_path_reckons(self):
        for units in (220, 500):
            with self.subTest(units=units):
                o, n = program(units)
                self.assertGreater(n, 512)
                r = link([o], ENV, asm=True)
                self.assertEqual(r.status, 0, r.errors)
                self.assertEqual(r.image, r.asm_image)

    def test_every_capacity_writes_what_a_link_that_holds_all_of_it_writes(self):
        for units in (60, 220):
            o, n = program(units)
            whole = link_at([o], WHOLE)
            self.assertEqual(whole[:2], (0, ''))
            full = link([o], ENV)
            self.assertEqual(full.status, 0, full.errors)
            self.assertEqual(full.image, whole[2]['out.bin'])
            for name, values in RUNS.items():
                with self.subTest(units=units, fix_ups=n, capacities=name):
                    self.assertEqual(link_at([o], values), whole)

    def test_a_function_with_no_slots_and_one_context(self):
        o = Obj('t')
        o.var('near', 1, MUST)
        o.var('far', 2, NEVER)
        hc = o.code()
        hc.raw(0x60)
        o.func('helper', hc)
        big_function(o, 'main', 120, own_slots=False)
        whole = link_at([o], WHOLE)
        self.assertEqual(whole[:2], (0, ''))
        self.assertEqual(link_at([o], RUNS['runs of 16']), whole)

    def test_a_table_of_more_addresses_than_a_run_is_still_refused(self):
        """Constant data is held whole: the compiler writes at most 256 addresses in a table
        (out.MAX_TABLE_FIXES), fewer than any build of the linker holds."""
        o = Obj('t')
        v = o.var('z', 1, NEVER)
        o.data('$1', bytes(40), fixes=[(i, 2, v, 0xFF, 0) for i in range(40)])
        c = o.code()
        c.abs(0xAD, o.d('$1'))
        c.raw(0x60)
        o.func('main', c)
        status, said, files = link_at([o], RUNS['runs of 16'])
        self.assertEqual((status, said), (1, 'link error 28: too many fix-ups in one table\n'))
        self.assertGreaterEqual(min(lk_small.capacities(level)['lk_tab']['MAX_FIXES'] for level in (True, 2)), 256)


if __name__ == '__main__':
    unittest.main()
