"""Interrupt contexts: every interrupt function is a root with storage of its own above the
main program's, and a function reached from two contexts is linked once for each
(lathe/docs/code-model.md, "Interrupts").

A function's first copy has the function's name in the map, followed by its context if that is
not 0; a further copy, for context N, is `name@N`.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_lk_support import (Obj, link, routine, NEVER, MUST, EITHER, LOCAL, INTERRUPT, NOBODY)  # noqa: E402

ENV = 'cpu 6502\nzeropage $00 $FF\ncode $0200 $BFFF\ndata $C000 $EFFF\nexit return\n'


def one(size, zp_class=MUST, weight=0):
    return [(size, zp_class, weight, LOCAL, 's')]


def shared(zp_class=MUST):
    """main -> f, and an interrupt function irq -> f."""
    o = Obj('t')
    routine(o, 'main', one(1, zp_class), ['f'])
    routine(o, 'f', one(2, zp_class))
    routine(o, 'irq', one(1, zp_class), ['f'], flags=INTERRUPT)
    return o


class TwoContexts(unittest.TestCase):
    def test_a_function_used_by_both_is_linked_twice_side_by_side(self):
        r = link([shared()], ENV)
        self.assertEqual(r.map_text.splitlines()[:5],
                         ['F 0200 0005 $start', 'F 0205 0004 t.main', 'F 0209 0001 t.f',
                          'F 020A 0001 t.f@1', 'F 020B 0004 t.irq 1'])

    def test_each_caller_calls_the_copy_of_its_own_context(self):
        r = link([shared()], ENV)
        self.assertEqual(r.code('t.main'), bytes.fromhex('200902 60'))
        self.assertEqual(r.code('t.irq'), bytes.fromhex('200A02 60'))

    def test_the_interrupt_context_is_above_everything_main_uses(self):
        r = link([shared()], ENV)
        self.assertEqual(r.map_text.splitlines()[5:],
                         ['S 0000 0001 t.main 0 s', 'S 0001 0002 t.f 0 s', 'S 0004 0002 t.f@1 0 s',
                          'S 0003 0001 t.irq 0 s'])

    def test_in_main_memory_too(self):
        r = link([shared(NEVER)], ENV)
        self.assertEqual([r.addr('S', n, 0) for n in ('t.main', 't.f', 't.irq', 't.f@1')],
                         [0xC000, 0xC001, 0xC003, 0xC004])

    def test_variables_are_below_both_contexts(self):
        o = shared()
        o.var('v', 2, MUST)
        r = link([o], ENV.replace('$00 $FF', '$20 $2F'))
        self.assertEqual((r.addr('V', 't.v'), r.addr('S', 't.main', 0), r.addr('S', 't.irq', 0)),
                         (0x20, 0x22, 0x25))

    def test_an_interrupt_function_is_kept_though_nothing_calls_it(self):
        o = Obj('t')
        routine(o, 'main')
        routine(o, 'unused', one(1), ['helper'])
        routine(o, 'tick', one(1), ['helper'], flags=INTERRUPT)
        routine(o, 'helper', one(1))
        r = link([o], ENV)
        self.assertEqual([m[3] for m in r.map if m[0] == 'F'], ['$start', 't.main', 't.tick', 't.helper'])

    def test_a_function_only_the_handler_uses_has_one_copy_under_its_own_name(self):
        o = Obj('t')
        routine(o, 'main', one(3), ['a'])
        routine(o, 'a', one(2))
        routine(o, 'tick', one(1), ['helper'], flags=INTERRUPT)
        routine(o, 'helper', one(1))
        r = link([o], ENV)
        self.assertEqual((r.addr('S', 't.tick', 0), r.addr('S', 't.helper', 0)), (5, 6))

    def test_each_interrupt_function_has_its_own_context(self):
        o = Obj('t')
        routine(o, 'main', one(1), ['f'])
        routine(o, 'f', one(1))
        routine(o, 'irq', one(1), ['f', 'g'], flags=INTERRUPT)
        routine(o, 'nmi', one(1), ['g', 'f'], flags=INTERRUPT)
        routine(o, 'g', one(4))
        r = link([o], ENV)
        self.assertEqual([m[3] for m in r.map if m[0] == 'F'],
                         ['$start', 't.main', 't.f', 't.f@1', 't.f@2', 't.irq', 't.nmi', 't.g', 't.g@2'])
        # main 0, f 1 | irq 2, f@1 and g 3..6 | nmi 7, g@2 and f@2 at 8
        self.assertEqual([r.addr('S', n, 0) for n in ('t.irq', 't.f@1', 't.g', 't.nmi', 't.g@2', 't.f@2')],
                         [2, 3, 3, 7, 8, 8])
        self.assertEqual(r.code('t.nmi'), r.at(r.addr('F', 't.nmi'), 7))
        self.assertEqual(r.code('t.nmi')[1:3], r.addr('F', 't.g@2').to_bytes(2, 'little'))
        self.assertEqual(r.code('t.nmi')[4:6], r.addr('F', 't.f@2').to_bytes(2, 'little'))


class Copies(unittest.TestCase):
    def worker(self, o):
        """f: a loop over its own slots, with a branch, a label and a constant after it."""
        f = o.f('f')
        c = o.code()
        c.abs(0xEE, f, slot=0)              #  0 INC s
        c.branch(0xD0, 11)                  #  3 BNE 11
        c.abs(0xEE, f, slot=1, add=1)       #  5 INC w+1
        c.abs(0xAD, f, slot=0)              #  8 LDA s
        c.abs(0x4C, f, add=0)               # 11 JMP 0
        o.func('f', c, slots=[(1, EITHER, 9, LOCAL, 's'), (2, NEVER, 0, LOCAL, 'w')])
        o.data('$1', b'\0\0', fixes=[(0, 1, f, 0xFF, 0)])

    def program(self):
        o = Obj('t')
        routine(o, 'main', one(1), ['f'])
        self.worker(o)
        routine(o, 'irq', one(1), ['f'], flags=INTERRUPT)
        routine(o, 'nmi', (), ['f'], flags=INTERRUPT)
        return o

    def test_every_copy_has_its_own_slots_branches_and_labels(self):
        r = link([self.program()], ENV)
        # zero page: main 0, f.s 1 | irq 2, f@1.s 3 | f@2.s 4; main memory: w at C000, C002, C004
        self.assertEqual(r.addr('F', 't.f'), 0x0209)
        self.assertEqual(r.code('t.f'), bytes.fromhex('E601 D005 EE01C0 A501 4C0902'))
        self.assertEqual(r.code('t.f@1'), bytes.fromhex('E603 D005 EE03C0 A503 4C1502'))
        self.assertEqual(r.code('t.f@2'), bytes.fromhex('E604 D005 EE05C0 A504 4C2102'))

    def test_what_follows_the_copies_is_still_read_in_order(self):
        r = link([self.program()], ENV)
        self.assertEqual(r.addr('D', 't.$1'), 0x022D)
        self.assertEqual(r.at(0x022D, 2), b'\x09\x02')         # the address of f: the first copy
        self.assertEqual(r.code('t.irq'), bytes.fromhex('201502 60'))
        self.assertEqual(r.code('t.nmi'), bytes.fromhex('202102 60'))

    def test_promotion_pays_for_a_slot_in_every_context_that_has_it(self):
        # f's slot costs a byte in each of three contexts. With main's and irq's class 0 bytes
        # that needs five; with four it stays in main memory.
        r = link([self.program()], ENV.replace('$00 $FF', '$00 $03'))
        self.assertEqual(r.addr('S', 't.f', 0), 0xC000)
        self.assertEqual(r.code('t.f'), bytes.fromhex('EE00C0 D006 EE02C0 AD00C0 4C0902'))
        self.assertEqual(r.code('t.f@2'), bytes.fromhex('EE06C0 D006 EE08C0 AD06C0 4C2502'))
        r = link([self.program()], ENV.replace('$00 $FF', '$00 $04'))
        self.assertEqual([r.addr('S', n, 0) for n in ('t.f', 't.f@1', 't.f@2')], [1, 3, 4])

    def test_recursion_is_checked_in_each_context(self):
        o = Obj('t')
        routine(o, 'main')
        routine(o, 'irq', (), ['a'], flags=INTERRUPT)
        routine(o, 'a', (), ['b'])
        routine(o, 'b', (), ['a'])
        self.assertEqual(link([o], ENV).errors,
                         'link error 21: recursion through a call or function not marked recursive: '
                         't.a -> t.b -> t.a\n')

    def test_zero_page_full_names_the_deepest_context(self):
        o = Obj('t')
        routine(o, 'main', one(1), ['f'])
        routine(o, 'f', one(1))
        routine(o, 'irq', one(1), ['g'], flags=INTERRUPT)
        routine(o, 'g', one(1), ['f'])
        r = link([o], ENV.replace('$00 $FF', '$00 $03'))
        self.assertEqual(r.errors, 'link error 25: zero page is full: t.irq -> t.g -> t.f@1\n')


if __name__ == '__main__':
    unittest.main()
