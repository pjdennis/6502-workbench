"""The rules of storage, checked on random programs.

For call graphs made at random (no recursion; two interrupt functions; slots of every class and
weight; a random amount of zero page) the map must show that

- a class 0 slot is in zero page and a class 2 slot is not, and everything is inside the
  environment's ranges;
- in each pool a callee's slots lie above its caller's, so nothing a chain of calls has active
  is overwritten;
- an interrupt context's storage lies above everything the contexts before it use;
- module-level variables overlap nothing.

Single-context programs are also built by the assembler path and the images compared.
"""
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_lk_support import (Obj, link, routine, MUST, EITHER, NEVER, LOCAL, INTERRUPT)  # noqa: E402


def random_program(rng, handlers):
    """Returns (object, calls: name -> callee names, roots, slot classes: name -> list)."""
    o = Obj('t')
    count = rng.randint(4, 24)
    names = ['main'] + ['f%d' % i for i in range(1, count)] + ['irq%d' % i for i in range(handlers)]
    calls = {}
    classes = {}
    for i, name in enumerate(names):
        if name.startswith('irq'):
            callees = rng.sample(names[1:count], rng.randint(1, min(3, count - 1)))
        else:
            later = names[i + 1:count]
            callees = rng.sample(later, min(len(later), rng.randint(0, 3)))
        slots = [(rng.choice((1, 1, 2, 3)), rng.choice((MUST, EITHER, EITHER, EITHER, NEVER)),
                  rng.randint(0, 9), LOCAL, 's%d' % k) for k in range(rng.randint(0, 4))]
        calls[name] = callees
        classes[name] = [s[1] for s in slots]
        routine(o, name, slots, callees, flags=INTERRUPT if name.startswith('irq') else 0)
    for i in range(rng.randint(0, 4)):
        o.var('v%d' % i, rng.choice((1, 2, 5)), rng.choice((MUST, EITHER, NEVER)), rng.randint(0, 9))
    return o, calls, ['main'] + names[count:], classes


def reach(calls, root):
    seen, todo = {root}, [root]
    while todo:
        for callee in calls[todo.pop()]:
            if callee not in seen:
                seen.add(callee)
                todo.append(callee)
    return seen


class RandomPrograms(unittest.TestCase):
    def check(self, seed):
        rng = random.Random(seed)
        handlers = rng.choice((0, 0, 2))
        o, calls, roots, classes = random_program(rng, handlers)
        zp_lo = rng.choice((0x00, 0x40))
        zp_hi = zp_lo + rng.randint(40, 90)
        environment = ('cpu 6502\nzeropage $%02X $%02X\ncode $0200 $BFFF\ndata $C000 $EFFF\nexit return\n'
                       % (zp_lo, zp_hi))
        r = link([o], environment, asm=(handlers == 0))
        self.assertEqual((r.status, r.errors), (0, ''), 'seed %d' % seed)
        if handlers == 0:
            self.assertTrue(r.image == r.asm_image, 'seed %d: images differ' % seed)

        # Which map name the copy of a function for a context has.
        contexts = [reach(calls, root) for root in roots]
        first = {}
        for c, members in enumerate(contexts):
            for name in members:
                first.setdefault(name, c)

        def copy(name, c):
            return 't.' + name if first[name] == c else 't.%s@%d' % (name, c)

        def spans(name, c, zero_page):
            """(start, end) of each slot of a copy that is in the given pool."""
            out = []
            for i, zp_class in enumerate(classes[name]):
                line = r.line('S', copy(name, c), i)
                addr, size = int(line[1], 16), int(line[2], 16)
                in_zp = addr < 0x100
                if in_zp:
                    self.assertTrue(zp_lo <= addr and addr + size - 1 <= zp_hi, line)
                    self.assertNotEqual(zp_class, NEVER, line)
                else:
                    self.assertTrue(0xC000 <= addr and addr + size - 1 <= 0xEFFF, line)
                    self.assertNotEqual(zp_class, MUST, line)
                if in_zp == zero_page:
                    out.append((addr, addr + size))
            return out

        for zero_page in (True, False):
            below = 0                   # where the storage of the contexts so far ends
            for c, members in enumerate(contexts):
                top = below
                for name in sorted(members):
                    mine = spans(name, c, zero_page)
                    for start, end in mine:
                        self.assertGreaterEqual(start, below, 'seed %d: %s in context %d' % (seed, name, c))
                        top = max(top, end)
                    for callee in calls[name]:
                        for start, _ in spans(callee, c, zero_page):
                            for _, end in mine:
                                self.assertGreaterEqual(start, end, 'seed %d: %s calls %s' % (seed, name, callee))
                below = top
            for line in (m for m in r.map if m[0] == 'V'):
                addr, size = int(line[1], 16), int(line[2], 16)
                if (addr < 0x100) == zero_page:
                    for slot in (m for m in r.map if m[0] == 'S'):
                        s_addr, s_size = int(slot[1], 16), int(slot[2], 16)
                        self.assertTrue(addr + size <= s_addr or s_addr + s_size <= addr, (line, slot))

    def test_storage_rules_hold(self):
        for seed in range(40):
            self.check(seed)


if __name__ == '__main__':
    unittest.main()
