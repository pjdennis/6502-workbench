"""The linker's storage allocation in one context: sharing frames, zero page classes, promotion
of "either" slots, module-level variables (lathe/docs/code-model.md, "Storage").

Addresses are read from the map file and were worked out by hand.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_lk_support import (Obj, link, routine, MUST, EITHER, NEVER, PARAM, LOCAL, TEMP, NOBODY,  # noqa: E402
                             POINTER, INTERRUPT, RECURSIVE, SAVES)


def env(zeropage='$00 $FF', data='$C000 $EFFF', cpu='6502'):
    return 'cpu %s\nzeropage %s\ncode $0200 $BFFF\ndata %s\nexit return\n' % (cpu, zeropage, data)


def func(o, name, slots=(), callees=(), flags=0, uses=()):
    """A function that reads each variable in `uses` (so that they are kept), calls each callee
    in turn and returns."""
    c = o.code()
    calls = []
    for v in uses:
        c.abs(0xAD, o.v(v))
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
        func(o, 'main', [(1, MUST, 0, LOCAL, 'm'), (1, NEVER, 0, LOCAL, 'n')], uses=['p', 'big', 'q'])
        o.var('q', 1, MUST)
        r = link([o], env('$30 $3F'))
        self.assertEqual([r.addr('V', n) for n in ('t.p', 't.big', 't.q')], [0x30, 0xC000, 0x32])
        self.assertEqual(slots(r, 't.main', 2), [0x33, 0xC12C])

    def test_a_heavier_variable_wins_the_last_byte(self):
        o = Obj('t')
        o.var('count', 1, EITHER, 30)
        func(o, 'main', [(1, EITHER, 20, LOCAL, 'm')], uses=['count'])
        r = link([o], env('$80 $80'))
        self.assertEqual((r.addr('V', 't.count'), r.addr('S', 't.main', 0)), (0x80, 0xC000))

    def test_a_heavier_slot_wins_the_last_byte(self):
        o = Obj('t')
        o.var('count', 1, EITHER, 20)
        func(o, 'main', [(1, EITHER, 30, LOCAL, 'm')], uses=['count'])
        r = link([o], env('$80 $80'))
        self.assertEqual((r.addr('V', 't.count'), r.addr('S', 't.main', 0)), (0xC000, 0x80))

    def test_at_equal_weight_a_slot_is_tried_before_a_variable(self):
        o = Obj('t')
        o.var('count', 1, EITHER, 20)
        func(o, 'main', [(1, EITHER, 20, LOCAL, 'm')], uses=['count'])
        r = link([o], env('$80 $80'))
        self.assertEqual((r.addr('V', 't.count'), r.addr('S', 't.main', 0)), (0xC000, 0x80))

    def test_variables_keep_definition_order_in_each_pool(self):
        a = Obj('a')
        a.v('b.late')                      # referred to before it is defined
        a.var('x', 1, NEVER)
        func(a, 'main', uses=['x', 'b.y', 'b.late'])
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


def user(o, name, names, callees=(), flags=0):
    """A function that reads each variable or constant named, calls each callee and returns.
    A name starting with `$` is constant data."""
    c = o.code()
    calls = []
    for n in names:
        target = o.d(n) if n.split('.')[-1].startswith('$') else o.v(n)
        c.abs(0xAD, target)
    for callee in callees:
        c.abs(0x20, o.f(callee))
        calls.append((o.f(callee), 0, NOBODY))
    c.raw(0x60)
    o.func(name, c, calls=calls, flags=flags)


class Unused(unittest.TestCase):
    """Variables and constant data that nothing kept refers to are dropped: no address and no
    map line (object-format.md, "What the linker keeps")."""

    def kinds(self, r, letter):
        return [m[3] for m in r.map if m[0] == letter]

    def test_a_variable_nothing_uses_is_dropped(self):
        o = Obj('t')
        o.var('used', 1, MUST)
        o.var('unused', 2, MUST)
        o.var('big', 300, NEVER)
        user(o, 'main', ['used'])
        r = link([o], env('$80 $80'))
        self.assertEqual(self.kinds(r, 'V'), ['t.used'])
        self.assertEqual(r.addr('V', 't.used'), 0x80)

    def test_what_only_dropped_code_uses_is_dropped(self):
        o = Obj('t')
        o.var('a', 1, EITHER, 5)
        o.data('$1', b'abc')
        user(o, 'main', [])
        user(o, 'unused', ['a', '$1'])
        r = link([o], env())
        self.assertEqual((self.kinds(r, 'V'), self.kinds(r, 'D')), ([], []))
        self.assertEqual(self.kinds(r, 'F'), ['$start', 't.main'])

    def test_constant_data_nothing_uses_takes_no_code_space(self):
        o = Obj('t')
        o.data('$1', bytes(7))
        o.data('$2', b'xy')
        user(o, 'main', ['$2'])
        r = link([o], env())
        self.assertEqual(self.kinds(r, 'D'), ['t.$2'])
        # $1 would have come first, straight after $start.
        self.assertEqual(r.addr('D', 't.$2'), r.addr('F', '$start') + r.size('F', '$start'))
        self.assertEqual(r.addr('F', 't.main'), r.addr('D', 't.$2') + 2)
        self.assertEqual(r.at(r.addr('D', 't.$2'), 2), b'xy')

    def test_a_kept_table_keeps_what_it_points_to(self):
        o = Obj('t')
        v = o.var('v', 1, NEVER)
        inner = o.data('$inner', b'\x01\x02')
        o.data('$outer', bytes(4), fixes=[(0, 1, inner, 0xFF, 0), (2, 1, v, 0xFF, 0)])
        o.data('$other', bytes(2), fixes=[(0, 1, o.v('w'), 0xFF, 0)])
        o.var('w', 1, NEVER)
        user(o, 'main', ['$outer'])
        r = link([o], env())
        self.assertEqual(self.kinds(r, 'D'), ['t.$inner', 't.$outer'])
        self.assertEqual(self.kinds(r, 'V'), ['t.v'])
        inner_at = r.addr('D', 't.$inner')
        self.assertEqual(r.at(r.addr('D', 't.$outer'), 4), bytes((inner_at & 0xFF, inner_at >> 8, 0x00, 0xC0)))

    def test_a_dropped_table_keeps_none_of_its_functions(self):
        o = Obj('t')
        user(o, 'main', ['$kept'])
        user(o, 'a', [])
        user(o, 'b', [])
        o.data('$kept', bytes(2), fixes=[(0, 1, o.f('a'), 0xFF, 0)])
        o.data('$lost', bytes(2), fixes=[(0, 1, o.f('b'), 0xFF, 0)])
        r = link([o], env())
        self.assertEqual(self.kinds(r, 'F'), ['$start', 't.main', 't.a'])
        self.assertEqual(self.kinds(r, 'D'), ['t.$kept'])

    def test_a_function_kept_for_its_address_keeps_what_it_uses(self):
        o = Obj('t')
        o.var('n', 1, NEVER)
        user(o, 'main', ['$tab'])
        user(o, 'h', ['n'])
        o.data('$tab', bytes(2), fixes=[(0, 1, o.f('h'), 0xFF, 0)])
        r = link([o], env())
        self.assertEqual(self.kinds(r, 'V'), ['t.n'])

    def test_a_variable_used_by_an_interrupt_function_is_kept(self):
        o = Obj('t')
        o.var('n', 1, NEVER)
        user(o, 'main', [])
        user(o, 'irq', ['n'], flags=INTERRUPT)
        r = link([o], env())
        self.assertEqual(self.kinds(r, 'V'), ['t.n'])

    def test_a_variable_given_an_initial_value_is_kept(self):
        # module.$init is always kept, and it writes the variable.
        o = Obj('t')
        o.var('n', 1, NEVER)
        user(o, 'main', [])
        user(o, '$init', ['n'])
        r = link([o], env())
        self.assertEqual(self.kinds(r, 'V'), ['t.n'])

    def test_a_dropped_variable_leaves_zero_page_to_slots(self):
        o = Obj('t')
        o.var('unused', 1, EITHER, 50)
        func(o, 'main', [(1, EITHER, 1, LOCAL, 'm')])
        r = link([o], env('$80 $80'))
        self.assertEqual(r.addr('S', 't.main', 0), 0x80)

    def test_a_dropped_must_variable_larger_than_zero_page_is_no_error(self):
        o = Obj('t')
        o.var('huge', 300, MUST)
        func(o, 'main')
        self.assertEqual(link([o], env()).status, 0)

    def test_undefined_symbols_that_only_dropped_code_and_data_name(self):
        o = Obj('t')
        user(o, 'main', [])
        user(o, 'unused', ['lib.var', 'lib.$tab'], ['lib.func'])
        o.data('$lost', bytes(2), fixes=[(0, 1, o.f('lib.other'), 0xFF, 0)])
        o.v('lib.never_named')
        r = link([o], env())
        self.assertEqual((r.status, r.errors), (0, ''))
        self.assertEqual(self.kinds(r, 'F'), ['$start', 't.main'])

    def test_undefined_symbols_that_kept_code_and_data_name(self):
        for names, callees, missing in ((['lib.var'], [], 'lib.var'), (['lib.$tab'], [], 'lib.$tab'),
                                        ([], ['lib.func'], 'lib.func')):
            o = Obj('t')
            user(o, 'main', names, callees)
            self.assertEqual(link([o], env()).errors, 'link error 18: undefined symbol: %s\n' % missing)
        o = Obj('t')
        user(o, 'main', ['$tab'])
        o.data('$tab', bytes(2), fixes=[(0, 1, o.f('lib.other'), 0xFF, 0)])
        self.assertEqual(link([o], env()).errors, 'link error 18: undefined symbol: lib.other\n')


class EndOfZeroPage(unittest.TestCase):
    """Every item in zero page lies wholly inside the environment's range, whether the range
    ends at $FF or lower; an "either" item that does not fit stays in main memory, and a
    "must" item that does not fit is error 25. Nothing at the last address but a byte."""

    RANGES = (('$00 $FF', 0x00, 0xFF), ('$10 $8F', 0x10, 0x8F))

    def zp_items(self, r):
        return [(int(m[1], 16), int(m[2], 16)) for m in r.map if m[0] in 'VSC' and int(m[1], 16) < 0x100]

    def check_inside(self, r, lo, hi):
        self.assertEqual((r.status, r.errors), (0, ''))
        for addr, size in self.zp_items(r):
            self.assertTrue(lo <= addr and addr + size - 1 <= hi, (hex(addr), size, r.map_text))

    def test_a_word_variable_with_one_byte_left_stays_out(self):
        for text, lo, hi in self.RANGES:
            o = Obj('t')
            o.var('fill', hi - lo, MUST)
            o.var('p', 2, EITHER, 9)
            func(o, 'main', uses=['fill', 'p'])
            r = link([o], env(text))
            self.check_inside(r, lo, hi)
            self.assertEqual(r.addr('V', 't.p'), 0xC000)

    def test_a_byte_takes_the_last_address(self):
        for text, lo, hi in self.RANGES:
            o = Obj('t')
            o.var('fill', hi - lo, MUST)
            o.var('p', 2, EITHER, 9)
            o.var('b', 1, EITHER, 1)
            func(o, 'main', uses=['fill', 'p', 'b'])
            r = link([o], env(text))
            self.check_inside(r, lo, hi)
            self.assertEqual((r.addr('V', 't.p'), r.addr('V', 't.b')), (0xC000, hi))

    def test_a_word_fills_the_last_two_addresses(self):
        for text, lo, hi in self.RANGES:
            o = Obj('t')
            o.var('fill', hi - lo - 1, MUST)
            func(o, 'main', [(2, EITHER, 9, LOCAL, 'p')], uses=['fill'])
            r = link([o], env(text))
            self.check_inside(r, lo, hi)
            self.assertEqual(r.addr('S', 't.main', 0), hi - 1)

    def test_a_must_word_with_one_byte_left_is_an_error(self):
        for text, lo, hi in self.RANGES:
            o = Obj('t')
            o.var('fill', hi - lo, MUST)
            func(o, 'main', [(2, MUST, 0, LOCAL, 'p')], uses=['fill'])
            r = link([o], env(text))
            self.assertEqual(r.errors, 'link error 25: zero page is full, 1 byte over: t.main\n')

    def test_slots_of_every_size_at_the_end_of_a_chain(self):
        # main -> f; the chain has three bytes left and f's slots are tried heaviest first.
        for text, lo, hi in self.RANGES:
            for sizes in ((2, 2), (3, 1), (1, 3), (4, 1), (2, 1)):
                o = Obj('t')
                o.var('fill', hi - lo - 2, MUST)
                func(o, 'main', [(1, EITHER, 1, LOCAL, 'm')], ['f'], uses=['fill'])
                func(o, 'f', [(sizes[0], EITHER, 9, LOCAL, 'a'), (sizes[1], EITHER, 8, LOCAL, 'b')])
                r = link([o], env(text))
                self.check_inside(r, lo, hi)
                used = sum(size for addr, size in self.zp_items(r))
                self.assertLessEqual(used, hi - lo + 1)

    def test_a_class_block_at_the_end(self):
        # The block (a byte and a word); with two bytes left the heavier word takes them.
        for text, lo, hi in self.RANGES:
            o = Obj('t')
            o.clas('h', [1, 2])
            o.var('fill', hi - lo - 1, MUST)
            routine(o, 'main', [], [('h', POINTER, None), 'vars'])
            func(o, 'vars', uses=['fill'])
            routine(o, 'm', [(1, EITHER, 5, PARAM, 'a'), (2, EITHER, 9, PARAM, 'b')])
            o.memb('h', 'm')
            r = link([o], env(text))
            self.check_inside(r, lo, hi)
            self.assertEqual((r.addr("C", "t.h", 0), r.addr("C", "t.h", 1)), (0xC000, hi - 1))

    def test_an_interrupt_context_at_the_end(self):
        for text, lo, hi in self.RANGES:
            o = Obj('t')
            o.var('fill', hi - lo - 1, MUST)
            routine(o, 'main', [(1, MUST, 0, LOCAL, 'm')], ['vars'])
            func(o, 'vars', uses=['fill'])
            routine(o, 'irq', [(2, EITHER, 9, LOCAL, 'p'), (1, EITHER, 3, LOCAL, 'q')], flags=INTERRUPT)
            r = link([o], env(text))
            self.check_inside(r, lo, hi)
            self.assertEqual((r.addr('S', 't.irq', 0), r.addr('S', 't.irq', 1)), (0xC000, hi))

    def test_a_recursive_set_at_the_end(self):
        for text, lo, hi in self.RANGES:
            o = Obj('t')
            o.var('fill', hi - lo - 2, MUST)
            routine(o, 'main', [], ['a', 'vars'])
            func(o, 'vars', uses=['fill'])
            routine(o, 'a', [(2, EITHER, 9, LOCAL, 'x')], [('b', SAVES, None)], flags=RECURSIVE)
            routine(o, 'b', [(2, EITHER, 8, LOCAL, 'y')], [('a', SAVES, None)], flags=RECURSIVE)
            r = link([o], env(text))
            self.check_inside(r, lo, hi)
            # The set is one piece: a's slot fits, then b's would make it four bytes.
            self.assertEqual((r.addr('S', 't.a', 0), r.addr('S', 't.b', 0)), (hi - 2, 0xC000))


class EndOfData(unittest.TestCase):
    def program(self, var_size, size=2):
        o = Obj('t')
        o.var('fill', var_size, NEVER)
        o.var('p', size, NEVER)
        func(o, 'main', uses=['fill', 'p'])
        return o

    def test_an_item_can_end_on_the_last_address(self):
        for data, top in (('$C000 $C0FF', 0xC0FF), ('$FF00 $FFFF', 0xFFFF), ('$C000 $C07F', 0xC07F)):
            lo = int(data[1:5], 16)
            r = link([self.program(top - lo - 1)], env(data=data, cpu='65c02'))
            self.assertEqual(r.addr('V', 't.p'), top - 1, data)

    def test_one_byte_over(self):
        r = link([self.program(0x7F)], env(data='$C000 $C07F'))
        self.assertEqual(r.errors, 'link error 26: variables do not fit in the data range, 1 byte over\n')

    def test_a_word_on_the_last_address_of_a_page_end(self):
        # On an NMOS 6502 the word would straddle $C0FF/$C100, so it moves past the range.
        r = link([self.program(0xFF)], env(data='$C000 $C0FF'))
        self.assertEqual(r.errors, 'link error 26: variables do not fit in the data range, 2 bytes over\n')
        r = link([self.program(0xFF)], env(data='$C000 $C101'))
        self.assertEqual(r.addr('V', 't.p'), 0xC100)
        r = link([self.program(0xFE)], env(data='$FF00 $FFFF'))
        self.assertEqual(r.addr('V', 't.p'), 0xFFFE)

    def test_a_word_at_the_top_of_memory_on_nmos(self):
        r = link([self.program(0xFF)], env(data='$FF00 $FFFF'))
        self.assertEqual(r.errors, 'link error 26: variables do not fit in the data range, 2 bytes over\n')


class PageBoundary(unittest.TestCase):
    """On an NMOS 6502 a two-byte item is never placed across a page boundary: JMP (pointer)
    would read the wrong high byte (code-model.md, "Functions called through a pointer")."""

    def program(self):
        o = Obj('t')
        o.var('a', 1, NEVER)
        o.var('p', 2, NEVER)
        func(o, 'main', [(1, NEVER, 0, LOCAL, 'b'), (2, NEVER, 0, LOCAL, 'q')], ['f'], uses=['a', 'p'])
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


class LargeSlots(unittest.TestCase):
    def test_slots_of_255_bytes_and_more(self):
        # The linker keeps a slot's size in a byte, and those of 255 bytes or more aside.
        o = Obj('t')
        o.func('main', b'\x60', slots=[(300, NEVER, 0, LOCAL, 'big'), (255, NEVER, 0, LOCAL, 'mid'),
                                        (1, NEVER, 0, LOCAL, 'one')])
        r = link([o])
        self.assertEqual(r.errors, '')
        base = r.addr('S', 't.main', 0)
        self.assertEqual((r.size('S', 't.main', 0), r.size('S', 't.main', 1)), (300, 255))
        self.assertEqual((r.addr('S', 't.main', 1), r.addr('S', 't.main', 2)), (base + 300, base + 555))

    def test_slots_either_side_of_15_bytes(self):
        # A slot's size is kept in four bits beside its class; those of 15 bytes or more aside.
        sizes = [14, 15, 16, 1, 254, 15]
        o = Obj('t')
        o.func('main', b'\x60', slots=[(n, NEVER, 0, LOCAL, 's%d' % i) for i, n in enumerate(sizes)])
        r = link([o])
        self.assertEqual(r.errors, '')
        base = r.addr('S', 't.main', 0)
        at = [base + sum(sizes[:i]) for i in range(len(sizes))]
        self.assertEqual([r.addr('S', 't.main', i) for i in range(len(sizes))], at)
        self.assertEqual([r.size('S', 't.main', i) for i in range(len(sizes))], sizes)


if __name__ == '__main__':
    unittest.main()
