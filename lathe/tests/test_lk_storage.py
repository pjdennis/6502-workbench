"""The linker's storage allocation in one context: sharing frames, zero page classes, promotion
of "either" slots, module-level variables (lathe/docs/code-model.md, "Storage").

Addresses are read from the map file and were worked out by hand.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_lk_support import (Obj, link, MUST, EITHER, NEVER, PARAM, LOCAL, TEMP, NOBODY)  # noqa: E402


def env(zeropage='$00 $FF', data='$C000 $EFFF', cpu='6502'):
    return 'cpu %s\nzeropage %s\ncode $0200 $BFFF\ndata %s\nexit return\n' % (cpu, zeropage, data)


def func(o, name, slots=(), callees=(), flags=0):
    """A function that calls each callee in turn and returns."""
    c = o.code()
    calls = []
    for callee in callees:
        c.abs(0x20, o.f(callee))
        calls.append((o.f(callee), 0, NOBODY))
    c.raw(0x60)
    o.func(name, c, slots=slots, calls=calls, flags=flags)


def slots(r, name, count):
    return [r.addr('S', name, i) for i in range(count)]


class Sharing(unittest.TestCase):
    def program(self, zp_class):
        """main -> a -> b and main -> c."""
        o = Obj('t')
        func(o, 'main', [(2, zp_class, 0, LOCAL, 'm')], ['a', 'c'])
        func(o, 'a', [(3, zp_class, 0, LOCAL, 'x')], ['b'])
        func(o, 'b', [(1, zp_class, 0, LOCAL, 'y')])
        func(o, 'c', [(4, zp_class, 0, LOCAL, 'z')])
        return link([o], env('$20 $3F'))

    def test_main_memory(self):
        r = self.program(NEVER)
        self.assertEqual([r.addr('S', n, 0) for n in ('t.main', 't.a', 't.b', 't.c')],
                         [0xC000, 0xC002, 0xC005, 0xC002])

    def test_zero_page(self):
        r = self.program(MUST)
        self.assertEqual([r.addr('S', n, 0) for n in ('t.main', 't.a', 't.b', 't.c')],
                         [0x20, 0x22, 0x25, 0x22])

    def test_slot_lines_give_size_number_and_name(self):
        r = self.program(NEVER)
        self.assertIn('S C002 0003 t.a 0 x', r.map_text.splitlines())

    def test_a_frame_starts_above_the_largest_caller(self):
        # main -> a -> c and main -> b -> c: c is above a, the larger of its callers.
        o = Obj('t')
        func(o, 'main', [(1, NEVER, 0, LOCAL, 'm')], ['a', 'b'])
        func(o, 'a', [(5, NEVER, 0, LOCAL, 'x')], ['c'])
        func(o, 'b', [(1, NEVER, 0, LOCAL, 'y')], ['c'])
        func(o, 'c', [(1, NEVER, 0, LOCAL, 'z')])
        r = link([o], env())
        self.assertEqual([r.addr('S', n, 0) for n in ('t.main', 't.a', 't.b', 't.c')],
                         [0xC000, 0xC001, 0xC001, 0xC006])

    def test_each_pool_has_its_own_block(self):
        o = Obj('t')
        func(o, 'main', [(1, MUST, 0, PARAM, 'a'), (2, NEVER, 0, LOCAL, 'b'), (1, MUST, 0, TEMP, 'c'),
                         (3, NEVER, 0, TEMP, 'd')], ['f'])
        func(o, 'f', [(1, NEVER, 0, LOCAL, 'x'), (1, MUST, 0, LOCAL, 'y')])
        r = link([o], env('$80 $8F'))
        self.assertEqual(slots(r, 't.main', 4), [0x80, 0xC000, 0x81, 0xC002])
        self.assertEqual(slots(r, 't.f', 2), [0xC005, 0x82])

    def test_dropped_functions_take_no_storage(self):
        o = Obj('t')
        func(o, 'unused', [(9, MUST, 0, LOCAL, 'u')], ['f'])
        func(o, 'main', [(1, MUST, 0, LOCAL, 'm')], ['f'])
        func(o, 'f', [(1, MUST, 0, LOCAL, 'x')])
        r = link([o], env('$00 $01'))
        self.assertEqual((r.addr('S', 't.main', 0), r.addr('S', 't.f', 0)), (0, 1))
        self.assertFalse(r.has('S', 't.unused'))

    def test_storage_is_shared_across_modules(self):
        a = Obj('a')
        func(a, 'main', [(1, NEVER, 0, LOCAL, 'm')], ['b.f', 'b.g'])
        b = Obj('b')
        func(b, 'f', [(2, NEVER, 0, LOCAL, 'x')])
        func(b, 'g', [(2, NEVER, 0, LOCAL, 'y')])
        r = link([a, b], env())
        self.assertEqual((r.addr('S', 'b.f', 0), r.addr('S', 'b.g', 0)), (0xC001, 0xC001))


class Promotion(unittest.TestCase):
    def test_heaviest_first_and_a_lighter_slot_takes_what_a_heavier_cannot(self):
        o = Obj('t')
        func(o, 'main', [(2, EITHER, 10, LOCAL, 'a'), (2, EITHER, 20, LOCAL, 'b'), (1, EITHER, 5, LOCAL, 'c')])
        r = link([o], env('$80 $82'))
        self.assertEqual(slots(r, 't.main', 3), [0xC000, 0x80, 0x82])

    def test_everything_goes_in_when_there_is_room(self):
        o = Obj('t')
        func(o, 'main', [(2, EITHER, 10, LOCAL, 'a'), (2, EITHER, 20, LOCAL, 'b'), (1, EITHER, 5, LOCAL, 'c')])
        r = link([o], env('$80 $8F'))
        self.assertEqual(slots(r, 't.main', 3), [0x80, 0x82, 0x84])

    def test_weight_0_and_class_never_stay_out(self):
        o = Obj('t')
        func(o, 'main', [(1, EITHER, 0, LOCAL, 'a'), (1, NEVER, 200, LOCAL, 'b'), (1, EITHER, 1, LOCAL, 'c')])
        r = link([o], env())
        self.assertEqual(slots(r, 't.main', 3), [0xC000, 0xC001, 0x00])

    def test_what_counts_is_the_deepest_chain_not_the_sum(self):
        # One byte of zero page serves a and b, which are never active together; main's own
        # lighter slot would make every chain two bytes deep.
        o = Obj('t')
        func(o, 'main', [(1, EITHER, 3, LOCAL, 'm')], ['a', 'b'])
        func(o, 'a', [(1, EITHER, 9, LOCAL, 'x')])
        func(o, 'b', [(1, EITHER, 9, LOCAL, 'y')])
        r = link([o], env('$80 $80'))
        self.assertEqual([r.addr('S', n, 0) for n in ('t.main', 't.a', 't.b')], [0xC000, 0x80, 0x80])

    def test_equal_weights_are_taken_in_order_until_the_chain_is_full(self):
        # main -> a -> b, one byte each of the same weight, two bytes of zero page.
        o = Obj('t')
        func(o, 'main', [(1, EITHER, 7, LOCAL, 'm')], ['a'])
        func(o, 'a', [(1, EITHER, 7, LOCAL, 'x')], ['b'])
        func(o, 'b', [(1, EITHER, 7, LOCAL, 'y')])
        r = link([o], env('$80 $81'))
        self.assertEqual([r.addr('S', n, 0) for n in ('t.main', 't.a', 't.b')], [0x80, 0x81, 0xC000])

    def test_a_slot_off_the_deepest_chain_costs_nothing(self):
        # main -> a -> b fills zero page with class 0 slots; c, called by main only, still
        # gets its heavy "either" slot in, on top of main's.
        o = Obj('t')
        func(o, 'main', [(1, MUST, 0, LOCAL, 'm')], ['a', 'c'])
        func(o, 'a', [(1, MUST, 0, LOCAL, 'x'), (1, EITHER, 50, LOCAL, 'x2')], ['b'])
        func(o, 'b', [(2, MUST, 0, LOCAL, 'y')])
        func(o, 'c', [(2, EITHER, 4, LOCAL, 'z'), (2, EITHER, 3, LOCAL, 'z2')])
        r = link([o], env('$10 $13'))
        self.assertEqual(slots(r, 't.a', 2), [0x11, 0xC000])
        self.assertEqual(slots(r, 't.c', 2), [0x11, 0xC000])
        self.assertEqual(r.addr('S', 't.b', 0), 0x12)

    def test_must_slots_come_before_promoted_ones_only_by_slot_number(self):
        o = Obj('t')
        func(o, 'main', [(1, EITHER, 9, LOCAL, 'a'), (1, MUST, 0, LOCAL, 'b')])
        r = link([o], env('$40 $4F'))
        self.assertEqual(slots(r, 't.main', 2), [0x40, 0x41])


class Variables(unittest.TestCase):
    def test_variables_are_below_the_frames_and_never_shared(self):
        o = Obj('t')
        o.var('p', 2, MUST)
        o.var('big', 300, NEVER)
        func(o, 'main', [(1, MUST, 0, LOCAL, 'm'), (1, NEVER, 0, LOCAL, 'n')])
        o.var('q', 1, MUST)
        r = link([o], env('$30 $3F'))
        self.assertEqual([r.addr('V', n) for n in ('t.p', 't.big', 't.q')], [0x30, 0xC000, 0x32])
        self.assertEqual(slots(r, 't.main', 2), [0x33, 0xC12C])

    def test_a_heavier_variable_wins_the_last_byte(self):
        o = Obj('t')
        o.var('count', 1, EITHER, 30)
        func(o, 'main', [(1, EITHER, 20, LOCAL, 'm')])
        r = link([o], env('$80 $80'))
        self.assertEqual((r.addr('V', 't.count'), r.addr('S', 't.main', 0)), (0x80, 0xC000))

    def test_a_heavier_slot_wins_the_last_byte(self):
        o = Obj('t')
        o.var('count', 1, EITHER, 20)
        func(o, 'main', [(1, EITHER, 30, LOCAL, 'm')])
        r = link([o], env('$80 $80'))
        self.assertEqual((r.addr('V', 't.count'), r.addr('S', 't.main', 0)), (0xC000, 0x80))

    def test_at_equal_weight_a_slot_is_tried_before_a_variable(self):
        o = Obj('t')
        o.var('count', 1, EITHER, 20)
        func(o, 'main', [(1, EITHER, 20, LOCAL, 'm')])
        r = link([o], env('$80 $80'))
        self.assertEqual((r.addr('V', 't.count'), r.addr('S', 't.main', 0)), (0xC000, 0x80))

    def test_variables_keep_definition_order_in_each_pool(self):
        a = Obj('a')
        a.v('b.late')                      # referred to before it is defined
        a.var('x', 1, NEVER)
        func(a, 'main')
        b = Obj('b')
        b.var('y', 2, NEVER)
        b.var('late', 1, NEVER)
        r = link([a, b], env())
        self.assertEqual(r.map_text.splitlines()[2:],
                         ['V C000 0001 a.x', 'V C001 0002 b.y', 'V C003 0001 b.late'])

    def test_a_variable_in_zero_page_shrinks_the_code_that_uses_it(self):
        o = Obj('t')
        v = o.var('n', 1, EITHER, 3)
        o.func('main', o.code().abs(0xEE, v).raw(0x60))
        r = link([o], env('$50 $5F'))
        self.assertEqual(r.code('t.main'), bytes.fromhex('E650 60'))


class PageBoundary(unittest.TestCase):
    """On an NMOS 6502 a two-byte item is never placed across a page boundary: JMP (pointer)
    would read the wrong high byte (code-model.md, "Functions called through a pointer")."""

    def program(self):
        o = Obj('t')
        o.var('a', 1, NEVER)
        o.var('p', 2, NEVER)
        func(o, 'main', [(1, NEVER, 0, LOCAL, 'b'), (2, NEVER, 0, LOCAL, 'q')], ['f'])
        func(o, 'f', [(2, NEVER, 0, LOCAL, 'x')])
        return o

    def test_nmos_skips_a_byte(self):
        r = link([self.program()], env(data='$C0FE $CFFF'))
        self.assertEqual((r.addr('V', 't.a'), r.addr('V', 't.p')), (0xC0FE, 0xC100))

    def test_65c02_does_not(self):
        r = link([self.program()], env(data='$C0FE $CFFF', cpu='65c02'))
        self.assertEqual((r.addr('V', 't.a'), r.addr('V', 't.p')), (0xC0FE, 0xC0FF))

    def test_slots_too_and_the_frame_above_follows(self):
        r = link([self.program()], env(data='$C0FB $CFFF'))
        # a $C0FB, p $C0FC-$C0FD; main: b $C0FE, q would be $C0FF -> $C100; f above at $C102.
        self.assertEqual(slots(r, 't.main', 2), [0xC0FE, 0xC100])
        self.assertEqual(r.addr('S', 't.f', 0), 0xC102)

    def test_a_frame_starting_on_the_boundary(self):
        r = link([self.program()], env(data='$C0FA $CFFF'))
        # main: b $C0FD, q $C0FE-$C0FF; f's x would start at $C100.
        self.assertEqual(slots(r, 't.main', 2), [0xC0FD, 0xC0FE])
        self.assertEqual(r.addr('S', 't.f', 0), 0xC100)


if __name__ == '__main__':
    unittest.main()
