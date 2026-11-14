"""Calls that shape storage: a call made while another call's arguments are pending, and
recursion (lathe/docs/code-model.md, "Calls inside arguments" and "Recursion").
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_lk_support import (Obj, link, routine, NEVER, MUST, EITHER, LOCAL, PARAM,  # noqa: E402
                             RECURSIVE, SAVES)

ENV = 'cpu 6502\nzeropage $00 $FF\ncode $0200 $BFFF\ndata $C000 $EFFF\nexit return\n'


def one(size, zp_class=NEVER):
    return [(size, zp_class, 0, LOCAL, 's')]


def base(r, name):
    return r.addr('S', name, 0)


class PendingArguments(unittest.TestCase):
    """main does g(a, h(b)): h runs while g's first argument is already in g's slot."""

    def program(self, outer):
        o = Obj('t')
        routine(o, 'main', one(1), [('h', 0, outer), 'g'])
        routine(o, 'g', one(2))
        routine(o, 'h', one(3))
        return o

    def test_without_the_record_the_two_callees_share(self):
        r = link([self.program(None)], ENV)
        self.assertEqual([base(r, n) for n in ('t.main', 't.g', 't.h')], [0xC000, 0xC001, 0xC001])

    def test_the_inner_callee_is_placed_above_the_outer(self):
        r = link([self.program('g')], ENV)
        self.assertEqual([base(r, n) for n in ('t.main', 't.g', 't.h')], [0xC000, 0xC001, 0xC003])

    def test_and_so_is_everything_the_inner_callee_calls(self):
        o = Obj('t')
        routine(o, 'main', one(1, MUST), [('h', 0, 'g'), 'g'])
        routine(o, 'g', one(2, MUST), ['k'])
        routine(o, 'h', one(3, MUST), ['k'])
        routine(o, 'k', one(1, MUST))
        r = link([o], ENV)
        self.assertEqual([base(r, n) for n in ('t.main', 't.g', 't.h', 't.k')], [0, 1, 3, 6])

    def test_an_inner_callee_that_can_reach_the_outer_is_a_cycle(self):
        o = Obj('t')
        routine(o, 'main', one(1), [('h', 0, 'g'), 'g'])
        routine(o, 'g', one(2))
        routine(o, 'h', one(3), ['k'])
        routine(o, 'k', one(1), ['g'])
        self.assertEqual(link([o], ENV).errors,
                         'link error 21: recursion through a call or function not marked recursive: '
                         't.g -> t.h -> t.k -> t.g\n')

    def test_the_record_keeps_nothing_alive(self):
        o = Obj('t')
        routine(o, 'main', one(1))
        routine(o, 'unused', one(1), [('h', 0, 'g'), 'g'])
        routine(o, 'g', one(2))
        routine(o, 'h', one(3))
        r = link([o], ENV)
        self.assertEqual(r.map_text, 'F 0200 0005 $start\nF 0205 0001 t.main\nS C000 0001 t.main 0 s\n')

    def test_arguments_of_the_caller_itself_add_nothing(self):
        # f(n, g(n)) inside recursive f: the call of g is already an edge from f, and the
        # record must not turn that saving call into a plain one.
        o = Obj('t')
        routine(o, 'main', one(1), ['f'])
        routine(o, 'f', one(2), [('g', SAVES, 'f'), ('f', SAVES, None)], flags=RECURSIVE)
        routine(o, 'g', one(3), [('f', SAVES, None)], flags=RECURSIVE)
        self.assertEqual(link([o], ENV).status, 0)


class Recursion(unittest.TestCase):
    def error(self, o):
        r = link([o], ENV)
        self.assertEqual(r.status, 1)
        prefix = 'link error 21: recursion through a call or function not marked recursive: '
        self.assertTrue(r.errors.startswith(prefix), r.errors)
        return r.errors[len(prefix):].strip()

    def test_a_marked_function_may_call_itself(self):
        o = Obj('t')
        routine(o, 'main', one(1), ['f'])
        routine(o, 'f', one(2), [('f', SAVES, None), 'leaf'], flags=RECURSIVE)
        routine(o, 'leaf', one(1))
        r = link([o], ENV)
        self.assertEqual([base(r, n) for n in ('t.main', 't.f', 't.leaf')], [0xC000, 0xC001, 0xC003])

    def test_an_unmarked_function_may_not(self):
        o = Obj('t')
        routine(o, 'main', one(1), ['f'])
        routine(o, 'f', one(2), ['f'])
        self.assertEqual(self.error(o), 't.f -> t.f')

    def test_marked_but_the_call_does_not_save(self):
        o = Obj('t')
        routine(o, 'main', one(1), ['f'])
        routine(o, 'f', one(2), ['f'], flags=RECURSIVE)
        self.assertEqual(self.error(o), 't.f -> t.f')

    def test_the_call_saves_but_the_function_is_not_marked(self):
        o = Obj('t')
        routine(o, 'main', one(1), ['f'])
        routine(o, 'f', one(2), [('f', SAVES, None)])
        self.assertEqual(self.error(o), 't.f -> t.f')

    def test_a_cycle_through_an_unmarked_function_names_the_cycle(self):
        o = Obj('t')
        routine(o, 'main', one(1), ['a'])
        routine(o, 'a', one(1), [('b', SAVES, None)], flags=RECURSIVE)
        routine(o, 'b', one(1), [('c', SAVES, None)], flags=RECURSIVE)
        routine(o, 'c', one(1), ['a'])
        cycle = self.error(o).split(' -> ')
        self.assertEqual(cycle[0], cycle[-1])
        self.assertEqual(sorted(cycle[:-1]), ['t.a', 't.b', 't.c'])
        # in call order: a calls b calls c calls a
        doubled = cycle[:-1] + cycle[:-1]
        at = doubled.index('t.a')
        self.assertEqual(doubled[at:at + 3], ['t.a', 't.b', 't.c'])

    def test_one_plain_call_among_saving_ones_spoils_the_edge(self):
        o = Obj('t')
        routine(o, 'main', one(1), ['a'])
        routine(o, 'a', one(1), [('b', SAVES, None), 'b'], flags=RECURSIVE)
        routine(o, 'b', one(1), [('a', SAVES, None)], flags=RECURSIVE)
        self.assertEqual(self.error(o), 't.a -> t.b -> t.a')

    def test_functions_that_recurse_through_each_other_do_not_share(self):
        # main -> a <-> b; a -> c; b -> d. Without the cycle b's frame could start where c's
        # does; with it a and b lie side by side and c and d above both.
        o = Obj('t')
        routine(o, 'main', one(1), ['a'])
        routine(o, 'a', one(2), [('b', SAVES, None), 'c'], flags=RECURSIVE)
        routine(o, 'b', one(3), [('a', SAVES, None), 'd'], flags=RECURSIVE)
        routine(o, 'c', one(1))
        routine(o, 'd', one(1))
        r = link([o], ENV)
        a, b = base(r, 't.a'), base(r, 't.b')
        self.assertEqual(sorted([(a, 2), (b, 3)])[0][0], 0xC001)
        self.assertTrue(a + 2 == b or b + 3 == a, (a, b))
        self.assertEqual((base(r, 't.c'), base(r, 't.d')), (0xC006, 0xC006))

    def test_the_whole_set_is_above_every_caller_of_any_member(self):
        # main -> p (6 bytes) -> b; main -> a; a <-> b.
        o = Obj('t')
        routine(o, 'main', one(1, MUST), ['p', 'a'])
        routine(o, 'p', one(6, MUST), ['b'])
        routine(o, 'a', one(2, MUST), [('b', SAVES, None)], flags=RECURSIVE)
        routine(o, 'b', one(3, MUST), [('a', SAVES, None)], flags=RECURSIVE)
        r = link([o], ENV)
        self.assertEqual(min(base(r, 't.a'), base(r, 't.b')), 7)
        self.assertEqual(max(base(r, 't.a') + 2, base(r, 't.b') + 3), 12)

    def test_promotion_counts_a_set_as_one_piece(self):
        # a <-> b each have a one-byte "either" slot; zero page has room for one of them only
        # if the two shared, which they must not.
        o = Obj('t')
        routine(o, 'main', (), ['a'])
        routine(o, 'a', [(1, EITHER, 5, LOCAL, 's')], [('b', SAVES, None)], flags=RECURSIVE)
        routine(o, 'b', [(1, EITHER, 5, LOCAL, 's')], [('a', SAVES, None)], flags=RECURSIVE)
        r = link([o], ENV.replace('$00 $FF', '$40 $40'))
        self.assertEqual(sorted([base(r, 't.a'), base(r, 't.b')]), [0x40, 0xC000])
        r = link([o], ENV.replace('$00 $FF', '$40 $41'))
        self.assertEqual(sorted([base(r, 't.a'), base(r, 't.b')]), [0x40, 0x41])

    def test_zero_page_error_names_the_whole_set(self):
        o = Obj('t')
        routine(o, 'main', one(1, MUST), ['a'])
        routine(o, 'a', one(2, MUST), [('b', SAVES, None)], flags=RECURSIVE)
        routine(o, 'b', one(2, MUST), [('a', SAVES, None)], flags=RECURSIVE)
        r = link([o], ENV.replace('$00 $FF', '$00 $03'))
        self.assertIn(r.errors, ('link error 25: zero page is full: t.main -> t.a -> t.b\n',
                                 'link error 25: zero page is full: t.main -> t.b -> t.a\n'))


if __name__ == '__main__':
    unittest.main()
